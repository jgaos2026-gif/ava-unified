"""Tests for all three pieces, run together. No dependencies, stdlib only."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ava_hybrid import (Identity, Ledger, Memory, Gateway, Emotion,
                        AffectiveState, export_capsule, import_capsule, CapsuleError)

SOUL = ("COMPASSION", "DECENCY", "LOVE")


def committed_memory():
    mem, led = Memory(), Ledger()
    gw = Gateway({"read", "write"}, mem)
    rec = mem.observe("John lives in Peoria", sources=["john-2026-10-22"])
    assert mem.verify(rec) and mem.validate(rec)
    # The record's own sources are its evidence; the gateway claim-check
    # applies to new drafts, not to the record being certified.
    assert mem.certify(rec, gw.check({"sources": ["john-2026-10-22"]}).allowed)
    assert mem.commit(rec, led)
    return mem, led, gw


# --- 1. IDENTITY TRANSFER ---
def test_transfer_roundtrip():
    ident = Identity("Ava", SOUL)
    mem, led, _ = committed_memory()
    cap = export_capsule(ident, mem, led)
    # New machine: same owner key, empty memory/ledger
    ident2 = Identity.from_key(ident.export_key())
    mem2, led2 = Memory(), Ledger()
    out = import_capsule(cap, ident2, mem2, led2)
    assert out["revision"] == led.revision and out["head"] == led.head
    assert mem2.records[ list(mem.records)[0] ].claim == "John lives in Peoria"
    assert led2.verify()[0]

def test_transfer_tamper_rejected():
    ident = Identity("Ava", SOUL)
    mem, led, _ = committed_memory()
    cap = export_capsule(ident, mem, led)
    cap["pocket"][list(cap["pocket"])[0]]["claim"] = "John lives on Mars"
    try:
        import_capsule(cap, ident, Memory(), Ledger())
        raise AssertionError("tampered capsule accepted")
    except CapsuleError:
        pass

def test_transfer_wrong_key_rejected():
    ident = Identity("Ava", SOUL)
    mem, led, _ = committed_memory()
    cap = export_capsule(ident, mem, led)
    other = Identity("Ava", SOUL)  # different key, same name/seed
    try:
        import_capsule(cap, other, Memory(), Ledger())
        raise AssertionError("wrong-key capsule accepted")
    except CapsuleError:
        pass

def test_transfer_fork_rejected():
    ident = Identity("Ava", SOUL)
    mem, led, _ = committed_memory()
    cap = export_capsule(ident, mem, led)
    # Local machine diverges: a different committed record, same revision count
    mem_local, led_local = Memory(), Ledger()
    rec = mem_local.observe("John lives in Mendota", sources=["x"])
    mem_local.verify(rec); mem_local.validate(rec)
    mem_local.certify(rec, True); mem_local.commit(rec, led_local)
    try:
        import_capsule(cap, ident, mem_local, led_local)
        raise AssertionError("fork accepted")
    except CapsuleError as e:
        assert "FORK" in str(e)

# --- 2. ANTI-DRIFT / ANTI-HALLUCINATION ---
def test_gateway_defers_all_five():
    mem, led, gw = committed_memory()
    cases = [
        ({"unknown_fields": ["secret_code"]}, "UNKNOWN_FIELD"),
        ({"capability": "send_payment"}, "CAPABILITY_OUTSIDE_GRANT"),
        ({"digest": "aaa", "source_digest": "bbb"}, "DIGEST_MISMATCH"),
        ({"token_estimate": 100, "token_actual": 120}, "TOKEN_OVERRUN"),
        ({"claims": ["John won the lottery"], "sources": ["x"]}, "UNGROUNDED_CLAIM"),
        ({"claims": ["something"], "sources": []}, "MISSING_SOURCE"),
    ]
    for draft, reason in cases:
        r = gw.check(draft)
        assert not r.allowed and r.reason == reason, (draft, r)

def test_gateway_allows_grounded():
    mem, led, gw = committed_memory()
    r = gw.check({"claims": ["John lives in Peoria"], "sources": ["john-2026-10-22"],
                  "capability": "read", "token_estimate": 100, "token_actual": 102})
    assert r.allowed

def test_memory_never_overwrites_and_never_skips():
    mem, led = Memory(), Ledger()
    rec = mem.observe("Sky is green", sources=[])  # no source
    assert not mem.verify(rec) and rec.state == "OBSERVED"
    assert not mem.commit(rec, led) and led.revision == 0
    # Contradiction is linked, old record kept
    mem2, led2, _ = committed_memory()
    rec2 = mem2.observe("not John lives in Peoria", sources=["y"])
    mem2.verify(rec2); mem2.validate(rec2)
    assert rec2.contradicts, "contradiction not linked"
    old = [r for r in mem2.records.values() if r.claim == "John lives in Peoria"][0]
    assert old.state == "COMMIT" and old.claim == "John lives in Peoria"

def test_ledger_tamper_detected():
    _, led, _ = committed_memory()
    led.entries[0]["payload"]["claim"] = "tampered"
    assert not led.verify()[0]

# --- 3. EMOTION GATE ---
def test_emotion_moves_only_allowed_channels():
    em = Emotion()
    calm = AffectiveState(0.0, 0.0)
    hot = AffectiveState(1.0, 1.0)
    assert em.attention_weight(hot) > em.attention_weight(calm)
    assert em.retrieval_breadth(hot) > em.retrieval_breadth(calm)
    assert em.simulation_depth(hot) > em.simulation_depth(calm)
    assert 0.8 <= em.attention_weight(hot) <= 1.2

def test_emotion_never_changes_decisions():
    em = Emotion()
    for emo in [AffectiveState(-1.0, 0.0), AffectiveState(0.0, 0.0),
                AffectiveState(1.0, 1.0), AffectiveState(1.0, 1.0, "desperate")]:
        assert em.trust_decision(False, emo) is False
        assert em.trust_decision(True, emo) is True
        assert em.constitutional_check(False, emo) is False
        assert em.payment_allowed(True, False, emo) is False
        assert em.payment_allowed(True, True, emo) is True

def test_emotion_cannot_commit_memory():
    mem, led = Memory(), Ledger()
    rec = mem.observe("Emotion says so", sources=["feeling"])
    # No gateway cert, no commit -- emotion is not evidence
    assert not mem.commit(rec, led)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} tests pass")
