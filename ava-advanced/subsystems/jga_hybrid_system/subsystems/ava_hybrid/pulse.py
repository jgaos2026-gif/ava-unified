"""Pulse master clock: John's ruling, 2026-10-26.

Everything is timed with the pulse. Pulse seq is the primary timing
reference; wall timestamps are display only, secondary, never ordering.
A pulse entry: {seq, prev_hash, head_hash, verify_ok, entry_hash}.
Rules:
  - seq is strictly +1, no gaps, no repeats, no second writer
  - a ledger append must carry the current pulse seq
  - a gap in seq, or a pulse entry whose head_hash does not match the
    ledger head at that seq, is a timing fault -> system halts to
    DEFER, it does not silently continue on wall time
  - kill-the-pulse test: if the pulse stops, no new commit is allowed
    (breathing != healthy: a pulse that ticks without verifying is
    still a fault)
This is why it is groundbreaking for Ava and not for a generic agent:
most agents trust wall time and silent timers. Ava trusts a verified,
hash-chained heartbeat, and stops when it breaks.
"""
import hashlib
import json


def _hash(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class Pulse:
    def __init__(self):
        self.entries = []
        self.alive = True

    @property
    def seq(self) -> int:
        return len(self.entries)

    def beat(self, head_hash: str | None, verify_ok: bool) -> dict:
        if not self.alive:
            raise RuntimeError("pulse killed -- no new commits allowed")
        entry = {
            "seq": len(self.entries),
            "prev_hash": self.entries[-1]["entry_hash"] if self.entries else "0" * 64,
            "head_hash": head_hash,
            "verify_ok": bool(verify_ok),
        }
        entry["entry_hash"] = _hash(entry)
        self.entries.append(entry)
        return entry

    def kill(self):
        self.alive = False

    def verify(self) -> tuple[bool, str]:
        prev = "0" * 64
        for i, e in enumerate(self.entries):
            if e["seq"] != i or e["prev_hash"] != prev:
                return False, f"pulse gap/break at seq {i}"
            check = dict(e)
            h = check.pop("entry_hash")
            if _hash(check) != h:
                return False, f"pulse tamper at seq {i}"
            if not e["verify_ok"]:
                return False, f"pulse beat {i} did not verify (breathing != healthy)"
            prev = h
        if not self.alive:
            return False, "pulse killed"
        return True, "ok"
