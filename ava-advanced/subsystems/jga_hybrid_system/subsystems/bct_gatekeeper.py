#!/usr/bin/env python3
"""
BCT Gatekeeper -- Option 2 (Precedence Gatekeeper, AVA / Clip Brick Layer).

Sits between recv_exact() and MicroSpine.append(). Every inbound frame
must pass four sequential stages; any failure aborts immediately, the
spine file is NOT touched, the sequence counter is NOT advanced, and
the caller gets a rejection code. Nothing that fails ever generates a
spine hash or advances the spine head.

Wire envelope (fixed 106-byte header, big-endian, as specified):
  4B  magic            b"BCT\\x02"
  2B  payload_type     0x0001 = Heartbeat, 0x000A = 11-Vault Transaction
  8B  sequence         monotonic per node, strictly increasing, >= 1
  8B  timestamp_ms     client wall-clock time, ms
  16B node_id          registry key (16 bytes; human name lives in the
                       registry file, NOT in the frame)
  64B signature        Ed25519 over signed_bytes (below)
  4B  body_length      N
  NB  body

  signed_bytes = magic || payload_type || sequence || timestamp_ms
                 || node_id || body_length || body
  (signature field itself is excluded, as it must be.)

Stage 1 -- Envelope & schema:
  magic, known type, body_length matches the actual frame, body fits
  the spine (body <= MAX_PAYLOAD - 106), sequence > last accepted
  sequence for that node, timestamp within +/-120 s of server time.
Stage 2 -- Peer key & signature:
  node_id must be in the authorized registry; Ed25519 signature over
  signed_bytes must verify with that node's public key.
Stage 3 -- Domain Clip Brick:
  validate(envelope, body) -> (bool, str). Implemented bricks:
    * 0x0001 Heartbeat: schema only (body empty or b"HEARTBEAT").
    * 0x000A 11-Vault: body is JSON with job_id, payment_stage,
      cleared_amount_cents, vaults (exactly the 11 vault keys), and
      banking_execution == "NONE_LEDGER_RECEIPT_ONLY". The vault
      amounts must equal, to the cent, the internal-reserve allocation
      computed from cleared_amount_cents (cent-round per vault, penny
      delta plugged into V7), so sum == cleared and zero rounding
      leaks. See the honesty note below -- this is arithmetic, not law.
Stage 4 -- Sealed Pocket Commitment:
  pocket_hash = SHA-256(signed_bytes || signature) -- the canonical
  frame digest. Only then is the whole frame (header + body) appended
  to the spine as one record. The spine's own HMAC head is separate
  from the pocket hash; both are returned to the caller.

HONESTY NOTE -- Stage 3, read before quoting it:
  The 11-Vault brick enforces INTERNAL RESERVE ARITHMETIC ONLY.
  It does NOT verify Illinois S-Corp statutory tax, Pass-Through
  Entity Tax, IL-1120-ST, or any Bluevine threshold, and it does NOT
  move bank funds or open sub-accounts. Those names appear in the
  original Option 2 spec as domain examples; they are NOT enforced
  claims here, and must not be repeated as such. A passing frame
  proves: a registered node signed it, it is not a replay (within
  the persisted sequence state), and its vault split balances to
  the cleared amount under the stated internal policy. Nothing more.

Replay state: last accepted sequence per node is persisted to a JSON
sidecar (state_path) atomically (temp file + rename) after a
successful spine append. If state_path is None, replay protection is
IN-MEMORY ONLY and resets on restart -- pass a state_path for any
real deployment, and say so when reporting results.

This module is stdlib-only except for the local ed25519.py and
micro_spine.py in the same directory. The Ed25519 implementation is
pure Python and NOT constant-time hardened; see ed25519.py.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import socket
import struct
import sys
import time
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

try:
    from micro_spine import MAX_PAYLOAD, MicroSpine, recv_exact
except ImportError:  # running as a script from another cwd
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from micro_spine import MAX_PAYLOAD, MicroSpine, recv_exact

import ed25519

MAGIC = b"BCT\x02"
HEADER_STRUCT = struct.Struct(">4sHQ Q 16s 64s I".replace(" ", ""))
# struct above: 4s + H + Q + Q + 16s + 64s + I = 106 bytes
HEADER_SIZE = HEADER_STRUCT.size
assert HEADER_SIZE == 106, HEADER_SIZE

TYPE_HEARTBEAT = 0x0001
TYPE_VAULT_TX = 0x000A
KNOWN_TYPES = {TYPE_HEARTBEAT, TYPE_VAULT_TX}
TIMESTAMP_WINDOW_MS = 120_000  # +/-120 s, per spec
MAX_BODY = MAX_PAYLOAD - HEADER_SIZE

# Internal reserve policy, identical to jga_auto/allocator_11vt.py.
# These are reserve TARGETS, not statutory tax rates.
VAULT_RATES = {
    "V1_FED_TAX_RESERVE": Decimal("0.150"),
    "V2_STATE_TAX_RESERVE": Decimal("0.075"),
    "V3_GATEWAY_FEES": Decimal("0.035"),
    "V4_CHARGEBACK_BUFFER": Decimal("0.050"),
    "V5_STATUTORY_RESERVE": Decimal("0.020"),
    "V6_COGS_PRODUCTION": Decimal("0.150"),
    "V7_DAILY_OPEX": Decimal("0.120"),
    "V8_OWNER_W2_RESERVE": Decimal("0.200"),
    "V9_RD_COMPUTE": Decimal("0.100"),
    "V10_CAPITAL_RESERVE": Decimal("0.080"),
    "V11_CIVIC_RESERVE": Decimal("0.020"),
}
ALLOWED_STAGES = ("DEPOSIT_CLEARED_35", "FINAL_PAID_65")


def _cent(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def expected_vault_amounts(cleared_cents: int) -> dict[str, int]:
    """Exact internal-reserve split for a cleared amount (cents)."""
    total = Decimal(cleared_cents) / Decimal(100)
    out: dict[str, int] = {}
    allocated = Decimal("0.00")
    for key, rate in VAULT_RATES.items():
        cut = _cent(total * rate)
        out[key] = int(cut * 100)
        allocated += cut
    delta = total - allocated
    if delta != 0:
        out["V7_DAILY_OPEX"] += int(delta * 100)
    return out


@dataclass
class Envelope:
    payload_type: int
    sequence: int
    timestamp_ms: int
    node_id: bytes
    signature: bytes
    body_length: int

    def signed_bytes(self, body: bytes) -> bytes:
        return (MAGIC
                + struct.pack(">H", self.payload_type)
                + struct.pack(">Q", self.sequence)
                + struct.pack(">Q", self.timestamp_ms)
                + self.node_id
                + struct.pack(">I", len(body))
                + body)


@dataclass
class GateResult:
    ok: bool
    code: str
    detail: str = ""
    pocket_hash: str | None = None
    spine_head: str | None = None


class FrameError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


def build_frame(secret_key: bytes, node_id: bytes, payload_type: int,
                sequence: int, body: bytes,
                timestamp_ms: int | None = None) -> bytes:
    """Sign and frame a body. Used by clients and tests; the
    gatekeeper never signs -- it only verifies."""
    if len(node_id) != 16:
        raise ValueError("node_id must be 16 bytes")
    if len(body) > MAX_BODY:
        raise ValueError("body exceeds MAX_BODY")
    ts = timestamp_ms if timestamp_ms is not None else int(time.time() * 1000)
    env = Envelope(payload_type, sequence, ts, node_id, b"\x00" * 64, len(body))
    sig = ed25519.sign(secret_key, env.signed_bytes(body))
    header = HEADER_STRUCT.pack(MAGIC, payload_type, sequence, ts,
                                node_id, sig, len(body))
    return header + body


def parse_frame(data: bytes) -> tuple[Envelope, bytes]:
    if len(data) < HEADER_SIZE:
        raise FrameError("STAGE1_BAD_LENGTH", "frame shorter than header")
    magic, ptype, seq, ts, node_id, sig, blen = HEADER_STRUCT.unpack_from(data, 0)
    if magic != MAGIC:
        raise FrameError("STAGE1_BAD_MAGIC", f"magic {magic!r} != {MAGIC!r}")
    if ptype not in KNOWN_TYPES:
        raise FrameError("STAGE1_UNKNOWN_TYPE", f"type 0x{ptype:04x}")
    if blen > MAX_BODY:
        raise FrameError("STAGE1_BAD_LENGTH", f"body {blen} exceeds MAX_BODY")
    if len(data) != HEADER_SIZE + blen:
        raise FrameError("STAGE1_BAD_LENGTH",
                         f"frame {len(data)} != header + body {HEADER_SIZE + blen}")
    body = data[HEADER_SIZE:]
    return Envelope(ptype, seq, ts, node_id, sig, blen), body


# --- Stage 3 bricks: validate(envelope, body) -> (bool, str) ---

def _brick_heartbeat(_env: Envelope, body: bytes) -> tuple[bool, str]:
    if body in (b"", b"HEARTBEAT"):
        return True, ""
    return False, "heartbeat body must be empty or b'HEARTBEAT'"


def _brick_vault_tx(_env: Envelope, body: bytes) -> tuple[bool, str]:
    try:
        obj = json.loads(body.decode("utf-8"))
    except Exception as exc:
        return False, f"vault body is not valid JSON: {exc}"
    if not isinstance(obj, dict):
        return False, "vault body must be a JSON object"
    if obj.get("banking_execution") != "NONE_LEDGER_RECEIPT_ONLY":
        return False, ("banking_execution must be NONE_LEDGER_RECEIPT_ONLY; "
                        "gatekeeper never records a bank movement claim")
    job_id = obj.get("job_id")
    if not isinstance(job_id, str) or not job_id or len(job_id) > 128:
        return False, "job_id must be a non-empty string (<=128 chars)"
    stage = obj.get("payment_stage")
    if stage not in ALLOWED_STAGES:
        return False, f"payment_stage must be one of {ALLOWED_STAGES}"
    cleared = obj.get("cleared_amount_cents")
    if not isinstance(cleared, int) or isinstance(cleared, bool) or cleared <= 0:
        return False, "cleared_amount_cents must be a positive integer"
    vaults = obj.get("vaults")
    if not isinstance(vaults, dict) or set(vaults) != set(VAULT_RATES):
        return False, "vaults must contain exactly the 11 vault keys"
    for key, val in vaults.items():
        if not isinstance(val, int) or isinstance(val, bool) or val < 0:
            return False, f"vault {key} amount must be a non-negative integer"
    expected = expected_vault_amounts(cleared)
    if vaults != expected:
        return False, ("vault split does not equal the internal-reserve "
                       f"allocation for {cleared} cents (sum or rates differ)")
    if sum(vaults.values()) != cleared:
        return False, "vault sum != cleared_amount_cents (rounding leak)"
    return True, ""


BRICKS = {TYPE_HEARTBEAT: _brick_heartbeat, TYPE_VAULT_TX: _brick_vault_tx}


def load_authorized_keys(path: Path) -> dict[bytes, bytes]:
    """JSON file: {node_id_hex (32 chars): public_key_hex (64 chars)}.
    Public keys only -- never put private keys in this file."""
    obj = json.loads(Path(path).read_text())
    out: dict[bytes, bytes] = {}
    for node_hex, pub_hex in obj.items():
        node_id = bytes.fromhex(node_hex)
        pub = bytes.fromhex(pub_hex)
        if len(node_id) != 16 or len(pub) != 32:
            raise ValueError(f"bad key entry: {node_hex}")
        out[node_id] = pub
    return out


class Gatekeeper:
    def __init__(self, spine: MicroSpine,
                 authorized_keys: dict[bytes, bytes],
                 state_path: Path | None = None):
        self.spine = spine
        self.authorized_keys = authorized_keys
        self.state_path = Path(state_path) if state_path else None
        self.last_seq: dict[bytes, int] = {}
        if self.state_path and self.state_path.exists():
            raw = json.loads(self.state_path.read_text())
            self.last_seq = {bytes.fromhex(k): int(v)
                             for k, v in raw.items()}

    def _save_state(self) -> None:
        if not self.state_path:
            return
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({k.hex(): v for k, v in self.last_seq.items()},
                                  sort_keys=True))
        tmp.replace(self.state_path)

    def process(self, data: bytes) -> GateResult:
        """Run all four stages. On any failure, return a rejection
        with the spine and sequence state untouched."""
        # Stage 1
        try:
            env, body = parse_frame(data)
        except FrameError as exc:
            return GateResult(False, exc.code, exc.detail)
        now_ms = int(time.time() * 1000)
        if abs(env.timestamp_ms - now_ms) > TIMESTAMP_WINDOW_MS:
            return GateResult(False, "STAGE1_TIMESTAMP_OUT_OF_WINDOW",
                              f"client {env.timestamp_ms} vs server {now_ms}")
        last = self.last_seq.get(env.node_id, 0)
        if env.sequence <= last:
            return GateResult(False, "STAGE1_REPLAY_SEQUENCE",
                              f"seq {env.sequence} <= last accepted {last}")
        # Stage 2
        pub = self.authorized_keys.get(env.node_id)
        if pub is None:
            return GateResult(False, "STAGE2_UNKNOWN_NODE",
                              f"node {env.node_id.hex()} not in registry")
        if not ed25519.verify(pub, env.signed_bytes(body), env.signature):
            return GateResult(False, "STAGE2_BAD_SIGNATURE",
                              "Ed25519 verification failed")
        # Stage 3
        brick = BRICKS[env.payload_type]
        ok, detail = brick(env, body)
        if not ok:
            return GateResult(False, "STAGE3_VALIDATION_FAILED", detail)
        # Stage 4
        pocket_hash = hashlib.sha256(
            env.signed_bytes(body) + env.signature).hexdigest()
        ok, spine_result = self.spine.append(data)
        if not ok:
            return GateResult(False, "STAGE4_SPINE_FAILED", spine_result)
        # Only now, after a durable append, advance the sequence.
        self.last_seq[env.node_id] = env.sequence
        self._save_state()
        return GateResult(True, "OK", "", pocket_hash, spine_result)


def run_gatekeeper_server(spine: MicroSpine, gatekeeper: Gatekeeper,
                          socket_file: Path) -> None:
    """Transport: 4-byte length prefix + frame. The gatekeeper, not
    the socket, decides what reaches the spine."""
    if socket_file.exists():
        socket_file.unlink()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_file))
    server.listen(128)
    print(f"[*] Gatekeeper listening on: {socket_file}")
    try:
        while True:
            conn, _ = server.accept()
            with conn:
                try:
                    raw_len = recv_exact(conn, 4)
                    (msg_len,) = struct.unpack(">I", raw_len)
                    frame = recv_exact(conn, msg_len)
                except (ValueError, ConnectionError) as exc:
                    try:
                        conn.sendall(f"FAIL:{exc}".encode("ascii")[:128])
                    except OSError:
                        pass
                    continue
                result = gatekeeper.process(frame)
                if result.ok:
                    conn.sendall(
                        f"OK:{result.pocket_hash}:{result.spine_head}"
                        .encode("ascii"))
                else:
                    conn.sendall(f"FAIL:{result.code}:{result.detail}"
                                 .encode("ascii")[:512])
    except KeyboardInterrupt:
        pass
    finally:
        if socket_file.exists():
            socket_file.unlink()


def main(argv=None) -> int:
    import argparse
    from micro_spine import load_secret
    parser = argparse.ArgumentParser(description="BCT Gatekeeper (Option 2)")
    parser.add_argument("--root", default=None)
    parser.add_argument("--keys", required=True,
                        help="JSON registry of authorized node public keys")
    parser.add_argument("--state", default=None,
                        help="sequence state file (recommended; replay "
                             "protection is in-memory only without it)")
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--selftest", action="store_true",
                        help="isolated temp-dir test; never touches the "
                             "persistent spine")
    args = parser.parse_args(argv)
    if args.selftest:
        import tempfile
        secret = os.urandom(32)
        # Use a fresh secret via env-free path: build spine directly.
        with tempfile.TemporaryDirectory() as td:
            spine = MicroSpine(Path(td) / "spine.bin", secret)
            sk, pk = ed25519.generate_keypair()
            node = b"OASIS-PAVILION-0"  # 16 bytes
            gk = Gatekeeper(spine, {node: pk})
            frame = build_frame(sk, node, TYPE_HEARTBEAT, 1, b"HEARTBEAT")
            res = gk.process(frame)
            print(f"selftest valid frame: ok={res.ok} code={res.code}")
            return 0 if res.ok else 1
    try:
        secret = load_secret()
    except Exception as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    base = Path(args.root or os.environ.get("BCT_ROOT", "./bct_runtime"))
    try:
        spine = MicroSpine(base / "spine.bin", secret)
        keys = load_authorized_keys(Path(args.keys))
    except Exception as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 3
    gk = Gatekeeper(spine, keys,
                    Path(args.state) if args.state else base / "gatekeeper_state.json")
    print(f"[+] Gatekeeper mounted. Spine records: {spine.record_count}, "
          f"authorized nodes: {len(keys)}")
    if args.daemon:
        run_gatekeeper_server(spine, gk, base / "bct_ipc.sock")
    return 0


if __name__ == "__main__":
    sys.exit(main())
