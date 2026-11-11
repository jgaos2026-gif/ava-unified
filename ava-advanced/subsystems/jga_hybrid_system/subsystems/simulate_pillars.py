"""Simulate all four pillars in one run. Run: python3 simulate_pillars.py"""
import sys
sys.path.insert(0, ".")
from ava_hybrid import (Identity, Ledger, Memory, SymbolicEngine,
                        DreamConsolidator, issue_receipt, verify_receipt,
                        make_did_document, resolve_did)

SOUL = ("COMPASSION", "DECENCY", "LOVE")
ava = Identity("Ava", SOUL)
mem, led = Memory(), Ledger()
for claim in ["John lives in Peoria", "John works in Peoria"]:
    r = mem.observe(claim, sources=["john"])
    mem.verify(r); mem.validate(r); mem.certify(r, True); mem.commit(r, led)

print("=== PILLAR 1: NEURO-SYMBOLIC ===")
eng = SymbolicEngine({"read"})
print(" neural proposes 'pay without deposit' ->",
      eng.check({"action": "pay", "deposit_cleared": False, "approved": True}).violations)
print(" neural proposes 'certify I am conscious' ->",
      eng.check({"action": "certify", "text": "I am conscious"}).violations)
print(" neural proposes clean read ->",
      eng.check({"action": "read", "capability": "read", "sources": ["x"], "constitutional_ok": True}).allowed)

print("\n=== PILLAR 2: DREAM-STATE (guardrailed) ===")
out = DreamConsolidator().consolidate(mem)
print(f" episodes read={out['episodes_read']} deleted={out['episodes_deleted']} edited={out['episodes_edited']}")
for s in out["syntheses"]:
    print(f" synthesis [{s.state}]: {s.claim} sources={s.sources}")
print(f" originals untouched: {[r.state for r in mem.records.values()]}")

print("\n=== PILLAR 3: ZK-LITE ===")
secret = {"prompt": "private prompt", "pocket": "private"}
rec = issue_receipt(ava, ["R1", "R3"], True, secret)
print(f" receipt: {rec}")
print(f" receipt contains prompt text? {'private prompt' in str(rec)}")
print(f" verify with claimed payload: {verify_receipt(ava, rec, secret)}")

print("\n=== PILLAR 4: DID-STYLE (local, not registered) ===")
doc = make_did_document(ava)
print(f" did: {doc['id']} service endpoints: {doc['service']}")
print(f" resolve: {resolve_did(ava, doc)}")
print(f" spoof by another key: {resolve_did(Identity('Ava', SOUL), doc)[0]}")
print("\nAll four pillars simulated. DID is local-format only; ZK is lite, not full ZK;")
print("dream deletes nothing; symbolic rules are code, not prompts.")
