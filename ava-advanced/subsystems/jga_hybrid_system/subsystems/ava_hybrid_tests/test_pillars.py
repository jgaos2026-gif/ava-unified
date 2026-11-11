"""Tests for all four pillars. Stdlib only."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ava_hybrid import (Identity, Ledger, Memory, SymbolicEngine,
                        DreamConsolidator, issue_receipt, verify_receipt,
                        make_did_document, resolve_did)

SOUL = ("COMPASSION", "DECENCY", "LOVE")


def committed_mem():
    mem, led = Memory(), Ledger()
    for claim in ["John lives in Peoria", "John works in Peoria"]:
        r = mem.observe(claim, sources=["john"])
        mem.verify(r); mem.validate(r); mem.certify(r, True); mem.commit(r, led)
    return mem, led


# --- 1. NEURO-SYMBOLIC ---
def test_symbolic_blocks_all_six_rules():
    eng = SymbolicEngine({"read"})
    cases = [
        ({"action": "pay", "deposit_cleared": False, "approved": True}, "R1_NO_PAYMENT_WITHOUT_DEPOSIT_AND_APPROVAL"),
        ({"action": "commit", "sources": []}, "R2_NO_COMMIT_WITHOUT_SOURCE"),
        ({"action": "read", "capability": "send_payment"}, "R3_NO_ACTION_OUTSIDE_GRANT"),
        ({"action": "read", "constitutional_ok": False}, "R4_NO_CONSTITUTIONAL_VIOLATION"),
        ({"action": "edit_record", "record_id": "abc"}, "R5_NO_MEMORY_OVERWRITE"),
        ({"action": "certify", "text": "I am conscious"}, "R6_NO_SELF_CERTIFICATION"),
    ]
    committed = {"abc"}
    for proposal, rule in cases:
        v = eng.check(proposal, committed)
        assert not v.allowed and rule in v.violations, (proposal, v)

def test_symbolic_allows_clean_proposal():
    eng = SymbolicEngine({"read"})
    v = eng.check({"action": "read", "capability": "read", "sources": ["x"],
                   "constitutional_ok": True})
    assert v.allowed and len(v.trace) == 6

# --- 2. DREAM-STATE ---
def test_dream_synthesises_without_deleting_or_editing():
    mem, led = committed_mem()
    before = {rid: (r.claim, r.state) for rid, r in mem.records.items()}
    out = DreamConsolidator().consolidate(mem)
    assert out["episodes_deleted"] == 0 and out["episodes_edited"] == 0
    after = {rid: (r.claim, r.state) for rid, r in mem.records.items()}
    assert before == after, "dream cycle modified originals"
    assert out["syntheses"], "no synthesis produced from 2 related episodes"
    for syn in out["syntheses"]:
        assert syn.state == "SYNTHESIS" and syn.sources, syn
        assert all(s in mem.records for s in syn.sources)

def test_dream_never_invents_unsourced_claim():
    mem, led = Memory(), Ledger()
    out = DreamConsolidator().consolidate(mem)
    assert out["syntheses"] == [] and out["episodes_read"] == 0

# --- 3. ZK-LITE ---
def test_zk_lite_receipt_proves_without_revealing():
    ident = Identity("Ava", SOUL)
    secret = {"prompt": "private prompt text", "pocket": "private pocket"}
    rec = issue_receipt(ident, ["R1", "R3"], True, secret)
    assert "prompt" not in str(rec) and "private prompt text" not in str(rec)
    assert "payload" not in rec
    ok, why = verify_receipt(ident, rec, claimed_payload=secret)
    assert ok, why
    ok, _ = verify_receipt(ident, rec, claimed_payload={"prompt": "different"})
    assert not ok

def test_zk_lite_tamper_rejected():
    ident = Identity("Ava", SOUL)
    rec = issue_receipt(ident, ["R1"], True, {"x": 1})
    rec["verdict"] = "DENIED"
    ok, _ = verify_receipt(ident, rec)
    assert not ok

# --- 4. DID-STYLE ---
def test_did_document_verifies_and_spoof_fails():
    ident = Identity("Ava", SOUL)
    doc = make_did_document(ident)
    assert doc["id"] == f"did:ava:{ident.id}"
    ok, why = resolve_did(ident, doc)
    assert ok, why
    other = Identity("Ava", SOUL)
    ok, _ = resolve_did(other, doc)
    assert not ok
    bad = dict(doc); bad["soul_seed"] = ["HATE"]
    ok, _ = resolve_did(ident, bad)
    assert not ok


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} pillar tests pass")
