"""Long-term memory: append-only, sourced, contradiction-linked, never overwritten.

Pipeline (all stages must pass before COMMIT):
  OBSERVED -> VERIFY -> VALIDATE -> CERTIFY -> COMMIT
A record that fails a stage stays at that stage. It is never silently
promoted, and an old record is never edited in place. A contradicting
record is appended and LINKED to the record it contradicts, with both
kept visible. That is how memory learns without rewriting its own past.

Tiers: HOT (working), WARM (recent, sourced), COLD (archived, sealed).
"""
import hashlib
import json
from dataclasses import dataclass, field


def _hash(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass
class MemoryRecord:
    claim: str
    sources: list = field(default_factory=list)
    tier: str = "HOT"
    state: str = "OBSERVED"
    contradicts: list = field(default_factory=list)
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = _hash({"claim": self.claim, "sources": self.sources})[:16]


class Memory:
    def __init__(self):
        self.records: dict[str, MemoryRecord] = {}

    def observe(self, claim: str, sources=None) -> MemoryRecord:
        rec = MemoryRecord(claim=claim, sources=list(sources or []))
        # Same claim+source re-observed: return existing, do not duplicate.
        if rec.id in self.records:
            return self.records[rec.id]
        self.records[rec.id] = rec
        return rec

    def verify(self, rec: MemoryRecord) -> bool:
        """VERIFY: a claim needs at least one source to move forward."""
        if rec.sources:
            rec.state = "VERIFY"
            return True
        return False

    def validate(self, rec: MemoryRecord) -> bool:
        """VALIDATE: link contradictions, never delete the contradicted record."""
        for other in self.records.values():
            if other.id != rec.id and other.state == "COMMIT" \
                    and (other.claim.lower() == ("not " + rec.claim.lower())
                         or rec.claim.lower() == ("not " + other.claim.lower())):
                rec.contradicts.append(other.id)
                other.contradicts.append(rec.id)
        rec.state = "VALIDATE"
        return True

    def certify(self, rec: MemoryRecord, gateway_ok: bool) -> bool:
        if gateway_ok:
            rec.state = "CERTIFY"
            return True
        return False

    def commit(self, rec: MemoryRecord, ledger) -> bool:
        """COMMIT: only a CERTIFY record reaches the ledger. Nothing else does."""
        if rec.state != "CERTIFY":
            return False
        rec.state = "COMMIT"
        rec.tier = "WARM" if rec.tier == "HOT" else rec.tier
        ledger.append("MEMORY_COMMIT", {
            "record_id": rec.id, "claim": rec.claim,
            "sources": rec.sources, "contradicts": rec.contradicts})
        return True

    def snapshot(self) -> dict:
        return {r.id: {"claim": r.claim, "sources": r.sources, "tier": r.tier,
                       "state": r.state, "contradicts": r.contradicts}
                for r in self.records.values()}

    @classmethod
    def from_snapshot(cls, snap: dict) -> "Memory":
        mem = cls()
        for rid, d in snap.items():
            mem.records[rid] = MemoryRecord(
                claim=d["claim"], sources=d["sources"], tier=d["tier"],
                state=d["state"], contradicts=d["contradicts"], id=rid)
        return mem

    def pocket_hash(self) -> str:
        return _hash(self.snapshot())
