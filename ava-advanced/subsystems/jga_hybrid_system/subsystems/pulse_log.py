"""Scratch prototype: pulse log format + verification.

Implements Step 1 of ~/workspace/your_files/pulse-spec-v1.md EXACTLY.
This file is scratch-only test code. It never touches a live haven.

Entry shape (exact, no extra fields):
    {seq, prev_hash, ts_display, verify_ok, head_hash, pocket_spotcheck,
     entry_hash, sig}

Rules (from the spec):
- `seq` is monotonic and is the ORDERING key. A missed pulse is a
  sequence gap, not a wall-time gap. Clock drift is irrelevant to
  detection because ordering comes from seq plus hashes, never time.
- `ts_display` is DISPLAY-ONLY. It is stamped so a human can read when
  a beat was recorded. It is never ordering evidence and never proves
  freshness ordering. (A watcher may use wall time as its own liveness
  timeout -- "should a beat have arrived by now" -- which is a timeout,
  not ordering evidence. See watcher_check.py.)
- `prev_hash` chains entries: prev_hash of entry N == entry_hash of
  entry N-1. Entry 0 uses GENESIS = 64 zeros.
- `entry_hash` is computed over the LENGTH-PREFIXED canonical encoding
  of the other six fields (the sidecar lesson -- no boundary ambiguity):
  for each field value in the fixed order
      [seq, prev_hash, ts_display, verify_ok, head_hash, pocket_spotcheck]
  take canon(field) bytes, prefix with the byte length as an 8-byte
  big-endian unsigned integer, and concatenate. entry_hash is the
  sha256 hex digest of that byte string.
  canon(x) = json.dumps(x, sort_keys=True, separators=(",", ":"),
  ensure_ascii=True, allow_nan=False).encode("ascii").
- `sig` is an Ed25519 signature over the RAW 32-byte entry_hash digest,
  under the pulse key. The pulse key here is a FRESH SCRATCH key
  generated inside the prototype directory. It is NOT any haven bridge
  key, and the pulse code never loads, holds, or uses a bridge key.
- Failure records use the SAME 8-field shape with verify_ok=false.
  A failure entry's head_hash is the last-known-GOOD head (the last
  head a healthy beat verified), never an unverified claim. The reason
  for the failure is carried in pocket_spotcheck.note as
  "skipped: <reason>", because on a failure beat no pocket check is
  stamped as healthy. Failure entries are chained and signed exactly
  like healthy ones, and they consume seq like any entry.

Torn tail: a final line without a trailing newline is an incomplete
write, not an entry. The verifier reports it (torn_tail=true) and
verifies only complete lines. The loop REFUSES to append over a torn
tail (fail-closed): it exits non-zero and leaves the bytes for an
operator, rather than silently rewriting history.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os

GENESIS = "0" * 64
FIELD_ORDER = ["seq", "prev_hash", "ts_display", "verify_ok", "head_hash", "pocket_spotcheck"]


def canon(o) -> bytes:
    """Deterministic JSON. Rejects NaN/Inf and non-JSON types."""
    return json.dumps(o, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def b64d(s: str) -> bytes:
    return base64.b64decode(s, validate=True)


def length_prefixed(entry_fields: dict) -> bytes:
    """Length-prefixed canonical encoding of the six hash-covered fields."""
    out = b""
    for name in FIELD_ORDER:
        blob = canon(entry_fields[name])
        out += len(blob).to_bytes(8, "big") + blob
    return out


def compute_entry_hash(entry_fields: dict) -> str:
    return sha(length_prefixed(entry_fields))


# ---------------------------------------------------------------- keys (scratch only)
def load_pulse_private(key_path: str):
    """Load a scratch pulse private key (b64 raw 32 bytes, mode 600)."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    with open(key_path) as f:
        return Ed25519PrivateKey.from_private_bytes(b64d(f.read().strip()))


def pulse_public_b64(priv) -> str:
    from cryptography.hazmat.primitives import serialization as S
    return b64e(priv.public_key().public_bytes(S.Encoding.Raw, S.PublicFormat.Raw))


def sign_entry_hash(priv, entry_hash: str) -> str:
    return b64e(priv.sign(bytes.fromhex(entry_hash)))


def verify_entry_signature(pub_b64: str, entry_hash: str, sig_b64: str) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        Ed25519PublicKey.from_public_bytes(b64d(pub_b64)).verify(
            b64d(sig_b64), bytes.fromhex(entry_hash))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


# ---------------------------------------------------------------- append
def build_entry(fields: dict, prev_hash: str, priv) -> dict:
    """Build a fully chained, hashed, signed entry. fields holds the six
    hash-covered fields (seq, ts_display, verify_ok, head_hash,
    pocket_spotcheck); prev_hash is supplied by the caller."""
    body = dict(fields)
    body["prev_hash"] = prev_hash
    entry = {name: body[name] for name in FIELD_ORDER}
    entry["entry_hash"] = compute_entry_hash(entry)
    entry["sig"] = sign_entry_hash(priv, entry["entry_hash"])
    return entry


def append_entry(log_path: str, fields: dict, prev_hash: str, priv) -> dict:
    entry = build_entry(fields, prev_hash, priv)
    line = json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n"
    with open(log_path, "a") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())
    return entry


# ---------------------------------------------------------------- verify
def verify_log(log_path: str, pub_b64: str) -> dict:
    """Verify a pulse log file. Returns a report dict:
    {ok, entries, head, last_seq, failures: [{line, kind, detail}],
     torn_tail}. Failure kinds: MALFORMED, SEQ_GAP, SEQ_ORDER,
     PREV_MISMATCH, HASH_MISMATCH, SIG_INVALID.
    ok is True only when every complete line verifies AND there is no
    torn tail confusion: a torn tail is reported separately (a log with
    a torn tail still verifies its complete lines, mirroring the v3
    ledger's verify_file semantics)."""
    failures = []
    entries = []
    if not os.path.exists(log_path):
        return {"ok": True, "entries": 0, "head": GENESIS, "last_seq": None,
                "failures": [], "torn_tail": False}
    with open(log_path, "rb") as f:
        data = f.read()
    torn_tail = False
    if data and not data.endswith(b"\n"):
        torn_tail = True
        data = data[:data.rfind(b"\n") + 1] if b"\n" in data else b""
    lines = data.split(b"\n")[:-1] if data else []
    prev = GENESIS
    for i, raw in enumerate(lines):
        try:
            e = json.loads(raw)
            if not isinstance(e, dict):
                raise ValueError("entry is not an object")
            for k in FIELD_ORDER + ["entry_hash", "sig"]:
                if k not in e:
                    raise ValueError(f"missing field {k}")
        except (ValueError, TypeError) as ex:
            failures.append({"line": i, "kind": "MALFORMED", "detail": str(ex)})
            break
        if e["seq"] != i:
            kind = "SEQ_GAP" if e["seq"] > i else "SEQ_ORDER"
            failures.append({"line": i, "kind": kind,
                             "detail": f"expected seq {i}, found {e['seq']}"})
        if e["prev_hash"] != prev:
            failures.append({"line": i, "kind": "PREV_MISMATCH",
                             "detail": f"prev_hash != entry_hash of line {i - 1}"})
        body = {name: e[name] for name in FIELD_ORDER}
        if compute_entry_hash(body) != e["entry_hash"]:
            failures.append({"line": i, "kind": "HASH_MISMATCH",
                             "detail": "recomputed entry_hash != stored entry_hash"})
        if not verify_entry_signature(pub_b64, e["entry_hash"], e["sig"]):
            failures.append({"line": i, "kind": "SIG_INVALID",
                             "detail": "signature does not verify under pulse key"})
        entries.append(e)
        prev = e["entry_hash"]
    ok = not failures
    return {"ok": ok, "entries": len(entries), "head": prev,
            "last_seq": entries[-1]["seq"] if entries else None,
            "failures": failures, "torn_tail": torn_tail}


class BrokenLog(Exception):
    pass


class TornTail(Exception):
    pass


def load_resume_state(log_path: str, pub_b64: str) -> dict:
    """State the loop needs to resume: last seq, last entry hash, last
    known-good head. Refuses (fail-closed) on a broken chain or a torn
    tail instead of appending on top of damage."""
    rep = verify_log(log_path, pub_b64)
    if rep["torn_tail"]:
        raise TornTail(f"{log_path}: torn final line; refusing to append")
    if not rep["ok"]:
        raise BrokenLog(f"{log_path}: chain broken: {rep['failures']}")
    if rep["entries"] == 0:
        return {"last_seq": -1, "last_hash": GENESIS, "last_good_head": GENESIS,
                "last_entry": None}
    last = None
    with open(log_path) as f:
        for line in f:
            last = json.loads(line)
    last_good = GENESIS
    for line in open(log_path):
        e = json.loads(line)
        if e["verify_ok"]:
            last_good = e["head_hash"]
    return {"last_seq": last["seq"], "last_hash": last["entry_hash"],
            "last_good_head": last_good, "last_entry": last}
