#!/usr/bin/env python3
"""
Hardened MicroSpine Core -- Option 1.

A small, stdlib-only, append-only binary ledger. This is deliberately
NOT an mmap ring buffer, NOT a zero-copy engine, and NOT a gatekeeper:
those are Options 3 and 2, still unbuilt. What this file does, and
nothing more:

  * Full-chain verification on mount. verify_integrity() recomputes
    every record hash from genesis to EOF. Any flipped bit, truncated
    record, or trailing garbage fails closed: the engine refuses to
    mount, and therefore refuses to append.
  * Strict secret sourcing. The secret comes from BCT_SECRET or from a
    keyfile named by BCT_SECRET_FILE. If neither is present, or the
    value is empty / too short, or the keyfile is not owner-only
    (POSIX mode 0600), the engine aborts. There is NO hardcoded
    fallback secret anywhere in this file.
  * Clean genesis. Genesis is written once, on first creation, and
    contains no payload. The self-test never touches the persistent
    file: it runs against an isolated temporary directory.
  * Robust socket server. Length prefix is read exactly, payloads are
    capped at MAX_PAYLOAD (64 KiB), and appends are serialised behind
    a lock (plus flock on POSIX, where available). The socket is the
    only writer path: clients never touch the spine file directly.

Record format (v1, breaking change from the unhardened paste):
  header: >QI32s  = 8-byte timestamp (ms, big-endian),
                    4-byte payload length, 32-byte record hash
  record hash = HMAC-SHA256(secret, prev_hash || timestamp_bytes
                            || length_bytes || payload)
  genesis record: length 0, hash = SHA-256(b"MICRO-SPINE-GENESIS-V1"),
    timestamp = creation time. Genesis is a fixed public anchor, not
    a secret-derived value, so a changed secret invalidates every
    later record (fail-closed) without making genesis itself secret.

Tamper-evidence, honestly stated: this file detects tampering of the
local spine file on mount. It does NOT make the file immutable, and
it does NOT survive an attacker who holds the secret (they can rewrite
the whole chain) or who deletes the file. An independent external
anchor / signature is still required for that claim. See README.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import socket
import stat
import struct
import sys
import tempfile
import threading
import time
from pathlib import Path

try:
    import fcntl  # POSIX only; absent on Windows by design
except ImportError:  # pragma: no cover - Windows path
    fcntl = None

HEADER_STRUCT = struct.Struct(">QI32s")
HEADER_SIZE = HEADER_STRUCT.size
GENESIS_HASH = hashlib.sha256(b"MICRO-SPINE-GENESIS-V1").digest()
MAX_PAYLOAD = 64 * 1024  # 64 KiB, per the Option 1 spec
MIN_SECRET_BYTES = 16


class IntegrityError(Exception):
    """Raised when a spine file fails full-chain verification."""


class SecretError(Exception):
    """Raised when no usable secret can be sourced."""


def load_secret() -> bytes:
    """Source the spine secret. No fallback, ever.

    Priority: BCT_SECRET env var, then BCT_SECRET_FILE env var
    naming a file whose POSIX mode is exactly 0600. Empty values,
    values under MIN_SECRET_BYTES, and keyfiles readable by group
    or others are all refused.
    """
    env = os.environ.get("BCT_SECRET", "")
    if env:
        secret = env.encode("utf-8")
        if len(secret) < MIN_SECRET_BYTES:
            raise SecretError(
                f"BCT_SECRET is too short ({len(secret)} bytes); "
                f"at least {MIN_SECRET_BYTES} bytes required")
        return secret
    keyfile = os.environ.get("BCT_SECRET_FILE", "")
    if keyfile:
        path = Path(keyfile)
        if not path.is_file():
            raise SecretError(f"BCT_SECRET_FILE does not exist: {keyfile}")
        if os.name == "posix":
            mode = stat.S_IMODE(path.stat().st_mode)
            if mode != 0o600:
                raise SecretError(
                    f"BCT_SECRET_FILE must be mode 0600, got {oct(mode)}: {keyfile}")
        raw = path.read_bytes().strip()
        if not raw:
            raise SecretError(f"BCT_SECRET_FILE is empty: {keyfile}")
        if len(raw) < MIN_SECRET_BYTES:
            raise SecretError(
                f"BCT_SECRET_FILE value too short ({len(raw)} bytes); "
                f"at least {MIN_SECRET_BYTES} bytes required")
        return raw
    raise SecretError(
        "No spine secret: set BCT_SECRET or BCT_SECRET_FILE. "
        "Refusing to start without one; there is no default secret.")


def _record_hash(secret: bytes, prev_hash: bytes, ts_ms: int,
                 payload: bytes) -> bytes:
    return hmac.new(
        secret,
        prev_hash
        + struct.pack(">Q", ts_ms)
        + struct.pack(">I", len(payload))
        + payload,
        hashlib.sha256).digest()


class MicroSpine:
    """Append-only ledger that verifies itself before it mounts."""

    def __init__(self, filepath: Path, secret: bytes):
        if not secret or len(secret) < MIN_SECRET_BYTES:
            raise SecretError(
                "Spine secret missing or too short; refusing to mount")
        self.filepath = Path(filepath)
        self.secret = secret
        self._lock = threading.Lock()
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        if not self.filepath.exists() or self.filepath.stat().st_size == 0:
            self._write_genesis()
        # Fail closed: a corrupt file never mounts, so it can never
        # be appended to and bury the corruption.
        self.last_hash, self.record_count = self.verify_integrity()

    def _write_genesis(self) -> None:
        ts_ms = int(time.time() * 1000)
        with open(self.filepath, "wb") as f:
            f.write(HEADER_STRUCT.pack(ts_ms, 0, GENESIS_HASH))
            f.flush()
            os.fsync(f.fileno())

    def verify_integrity(self):
        """Recompute the whole chain, genesis to EOF.

        Returns (head_hash, record_count) where record_count counts
        payload records only (genesis excluded). Raises IntegrityError
        on the first defect found: bad genesis, hash mismatch,
        truncated header/payload, or trailing garbage bytes.
        """
        data = self.filepath.read_bytes()
        if len(data) < HEADER_SIZE:
            raise IntegrityError(
                f"spine too short ({len(data)} bytes); no genesis record")
        ts_ms, length, stored = HEADER_STRUCT.unpack_from(data, 0)
        if length != 0 or stored != GENESIS_HASH:
            raise IntegrityError("genesis record mismatch")
        prev_hash = GENESIS_HASH
        offset = HEADER_SIZE
        count = 0
        while offset < len(data):
            if len(data) - offset < HEADER_SIZE:
                raise IntegrityError(
                    f"truncated header at offset {offset}")
            ts_ms, length, stored = HEADER_STRUCT.unpack_from(data, offset)
            offset += HEADER_SIZE
            if length > MAX_PAYLOAD:
                raise IntegrityError(
                    f"record at offset {offset} exceeds MAX_PAYLOAD")
            if len(data) - offset < length:
                raise IntegrityError(
                    f"truncated payload at offset {offset}")
            payload = data[offset:offset + length]
            expected = _record_hash(self.secret, prev_hash, ts_ms, payload)
            if not hmac.compare_digest(expected, stored):
                raise IntegrityError(
                    f"hash mismatch at record {count} (offset {offset})")
            prev_hash = stored
            offset += length
            count += 1
        if offset != len(data):
            raise IntegrityError("trailing bytes after last record")
        return prev_hash, count

    def append(self, payload: bytes) -> tuple[bool, str]:
        """Append one payload. Returns (ok, head_hash_hex or error)."""
        if not payload:
            return False, "ERR_EMPTY_PAYLOAD"
        if len(payload) > MAX_PAYLOAD:
            return False, "ERR_PAYLOAD_TOO_LARGE"
        ts_ms = int(time.time() * 1000)
        with self._lock:
            # Re-verify head under the lock: another writer through
            # this object cannot interleave, and a foreign change to
            # the file is caught before we build on it.
            head, _ = self.verify_integrity()
            current = _record_hash(self.secret, head, ts_ms, payload)
            entry = HEADER_STRUCT.pack(ts_ms, len(payload), current) + payload
            with open(self.filepath, "ab") as f:
                if fcntl is not None:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    f.write(entry)
                    f.flush()
                    os.fsync(f.fileno())
                finally:
                    if fcntl is not None:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            self.last_hash = current
            self.record_count += 1
        return True, current.hex()


def run_selftest() -> bool:
    """Self-test against an isolated temp directory only.

    Returns True on pass. Never opens, reads, or writes the
    persistent spine file, so startup can never mutate the chain.
    """
    secret = load_secret()
    with tempfile.TemporaryDirectory(prefix="micro-spine-test-") as td:
        spine = MicroSpine(Path(td) / "spine.bin", secret)
        assert spine.record_count == 0
        ok, head = spine.append(b"SELFTEST")
        assert ok, head
        assert spine.verify_integrity()[0].hex() == head
        assert spine.record_count == 1
    return True


def recv_exact(conn: socket.socket, n: int) -> bytes:
    """Read exactly n bytes, or raise on EOF / oversize."""
    if n > MAX_PAYLOAD:
        raise ValueError(f"payload length {n} exceeds MAX_PAYLOAD")
    buf = bytearray()
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("client closed connection mid-message")
        buf.extend(chunk)
    return bytes(buf)


def run_socket_server(spine: MicroSpine, socket_file: Path) -> None:
    """Sequential accept loop: the server is the sole writer, so
    appends are serialised by construction, plus the spine lock."""
    if socket_file.exists():
        socket_file.unlink()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_file))
    server.listen(128)
    print(f"[*] Listening on local domain socket: {socket_file}")
    try:
        while True:
            conn, _ = server.accept()
            with conn:
                try:
                    raw_len = recv_exact(conn, 4)
                    (msg_len,) = struct.unpack(">I", raw_len)
                    payload = recv_exact(conn, msg_len)
                except (ValueError, ConnectionError) as exc:
                    try:
                        conn.sendall(f"FAIL:{exc}".encode("ascii")[:128])
                    except OSError:
                        pass
                    continue
                ok, result = spine.append(payload)
                conn.sendall((b"OK:" if ok else b"FAIL:")
                             + result.encode("ascii"))
    except KeyboardInterrupt:
        pass
    finally:
        if socket_file.exists():
            socket_file.unlink()


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Hardened MicroSpine Core")
    parser.add_argument("--root", default=None,
                        help="storage directory (default: $BCT_ROOT or ./bct_runtime)")
    parser.add_argument("--selftest", action="store_true",
                        help="isolated self-test only; never touches the persistent spine")
    parser.add_argument("--daemon", action="store_true",
                        help="run the local socket server after verifying the chain")
    args = parser.parse_args(argv)
    try:
        secret = load_secret()
    except SecretError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    if args.selftest:
        try:
            run_selftest()
        except Exception as exc:  # self-test must never be silent
            print(f"SELF-TEST FAILED: {exc}", file=sys.stderr)
            return 1
        print("[*] Self-test passed (isolated temp file; persistent chain untouched).")
        return 0
    base = Path(args.root or os.environ.get("BCT_ROOT", "./bct_runtime"))
    ledger = base / "spine.bin"
    try:
        spine = MicroSpine(ledger, secret)
    except IntegrityError as exc:
        print(f"REFUSED TO MOUNT: {exc}", file=sys.stderr)
        return 3
    print(f"[+] MicroSpine mounted. Records: {spine.record_count}, "
          f"head: {spine.last_hash.hex()[:16]}...")
    if args.daemon:
        run_socket_server(spine, base / "bct_ipc.sock")
    return 0


if __name__ == "__main__":
    sys.exit(main())
