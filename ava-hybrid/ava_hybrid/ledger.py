"""Append-only hash-chained ledger. Tamper is detectable, history is never rewritten."""
import hashlib
import json


def _hash(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class Ledger:
    def __init__(self):
        self.entries = []

    @property
    def head(self) -> str | None:
        return self.entries[-1]["entry_hash"] if self.entries else None

    @property
    def revision(self) -> int:
        return len(self.entries)

    def append(self, kind: str, payload: dict) -> dict:
        prev = self.head or ("0" * 64)
        entry = {
            "seq": len(self.entries),
            "kind": kind,
            "payload": payload,
            "payload_hash": _hash(payload),
            "prev_hash": prev,
        }
        entry["entry_hash"] = _hash(entry)
        self.entries.append(entry)
        return entry

    def verify(self) -> tuple[bool, str]:
        prev = "0" * 64
        for i, e in enumerate(self.entries):
            if e["seq"] != i or e["prev_hash"] != prev:
                return False, f"chain break at seq {i}"
            check = dict(e)
            h = check.pop("entry_hash")
            if _hash(check) != h or _hash(e["payload"]) != e["payload_hash"]:
                return False, f"tampered entry at seq {i}"
            prev = h
        return True, "ok"

    def to_list(self) -> list:
        return [dict(e) for e in self.entries]

    @classmethod
    def from_list(cls, entries: list) -> "Ledger":
        led = cls()
        led.entries = [dict(e) for e in entries]
        ok, why = led.verify()
        if not ok:
            raise ValueError(f"ledger rejected: {why}")
        return led
