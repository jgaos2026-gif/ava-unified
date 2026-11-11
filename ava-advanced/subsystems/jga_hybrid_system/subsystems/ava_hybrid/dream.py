"""Dream-state consolidation: idle-time synthesis, with guardrails.

What it DOES: while idle, it reads COMMITTED episodic records, groups
them by shared words, and synthesises NEW semantic records that
summarise a cluster. Each synthesis record carries:
  - state = "SYNTHESIS" (never COMMIT, never fact)
  - sources = the episode record ids it summarises
  - links back to every episode, so the synthesis is auditable

What it NEVER does (these are the guardrails, tested):
  - never edits, deletes, or prunes an original record
  - never overwrites a committed record
  - never promotes a synthesis to COMMIT on its own -- promotion
    still needs the normal OBSERVED->VERIFY->VALIDATE->CERTIFY->COMMIT
    pipeline and the owner's gateway
  - never invents a claim with no source episodes

Pruning in the paste's sense is therefore NOT implemented. Redundant
episodes stay. What shrinks is retrieval work: one synthesis can be
read first, then its sources on demand.
"""
from collections import defaultdict
import re
from .memory import MemoryRecord


def _words(claim: str) -> set:
    return {w for w in re.findall(r"[a-z]{4,}", claim.lower())}


class DreamConsolidator:
    def consolidate(self, memory) -> dict:
        committed = [r for r in memory.records.values() if r.state == "COMMIT"]
        clusters = defaultdict(list)
        for rec in committed:
            for w in _words(rec.claim):
                clusters[w].append(rec)
        syntheses = []
        seen = set()
        for word, recs in sorted(clusters.items()):
            if len(recs) < 2:
                continue
            key = tuple(sorted(r.id for r in recs))
            if key in seen:
                continue
            seen.add(key)
            syn = MemoryRecord(
                claim=f"Pattern around '{word}': {len(recs)} related episodes",
                sources=[r.id for r in recs],
                tier="WARM", state="SYNTHESIS",
                contradicts=[],
            )
            syntheses.append(syn)
        return {
            "episodes_read": len(committed),
            "episodes_deleted": 0,
            "episodes_edited": 0,
            "syntheses": syntheses,
        }
