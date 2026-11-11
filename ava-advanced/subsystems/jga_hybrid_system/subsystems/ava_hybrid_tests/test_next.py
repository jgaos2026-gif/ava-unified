"""Tests for the four upgrades Rumi chose. Stdlib only."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ava_hybrid import (Identity, Ledger, Memory, Pulse, DualConsensus,
                        SymbolicEngine, read_self_state, CapabilityStore)

SOUL = ("COMPASSION", "DECENCY", "LOVE")


def test_pulse_seq_gap_and_kill():
    p = Pulse()
    p.beat("head1", True); p.beat("head2", True)
    assert p.seq == 2 and p.verify()[0]
    p.entries.pop()  # simulate a gap: seq now breaks? rebuild check:
    # After removing last entry, seq is 1 and chain still verifies;
    # a forged gap entry breaks it:
    p.entries.append({"seq": 99, "prev_hash": "x", "head_hash": None,
                      "verify_ok": True, "entry_hash": "y"})
    assert not p.verify()[0]
    p2 = Pulse(); p2.beat("h", True); p2.kill()
    assert not p2.verify()[0]
    try:
        p2.beat("h2", True)
        raise AssertionError("killed pulse accepted a beat")
    except RuntimeError:
        pass

def test_pulse_unverified_beat_is_fault():
    p = Pulse(); p.beat("h", False)
    assert not p.verify()[0]  # breathing != healthy

def test_dual_consensus_agrees_and_defers():
    dc = DualConsensus(SymbolicEngine({"read", "decide"}))
    good = {"action": "read", "capability": "read", "sources": ["x"], "constitutional_ok": True}
    r = dc.decide(good, dict(good))
    assert r.status == "AGREED" and r.action == "read"
    other = {"action": "decide", "capability": "decide", "sources": ["x"], "constitutional_ok": True}
    r = dc.decide(good, other)
    assert r.status == "DEFERRED" and r.reason == "PROPOSALS_DISAGREE"
    r = dc.decide(good, {"action": "pay", "deposit_cleared": False, "approved": True})
    assert r.status == "DEFERRED" and "blocked" in r.reason

def test_selfmodel_readonly_and_reports():
    ident = Identity("Ava", SOUL)
    mem, led, pulse = Memory(), Ledger(), Pulse()
    r = mem.observe("John lives in Peoria", sources=["john"])
    mem.verify(r); mem.validate(r); mem.certify(r, True); mem.commit(r, led)
    pulse.beat(led.head, True)
    state = read_self_state(ident, led, mem, pulse,
                            ["UNGROUNDED_CLAIM"],
                            [("ev1", "calm", True), ("ev1", "hot", True)])
    assert state.ledger_revision == 1 and state.ledger_ok
    assert state.memory_by_state.get("COMMIT") == 1
    assert state.pulse_seq == 1 and state.pulse_ok
    assert state.deferrals == {"UNGROUNDED_CLAIM": 1}
    assert state.emotion_audit_ok
    # Emotion changing an outcome is a fault, reported:
    bad = read_self_state(ident, led, mem, pulse, [],
                          [("ev1", "calm", True), ("ev1", "hot", False)])
    assert not bad.emotion_audit_ok

def test_capability_pulse_bound_and_revocable():
    ident = Identity("Ava", SOUL)
    store = CapabilityStore()
    g = store.issue(ident, "g1", "read", ident.id, 0, 5)
    assert store.allowed(ident, g, "read", 3)
    assert not store.allowed(ident, g, "read", 6)  # expired by pulse
    assert not store.allowed(ident, g, "write", 3)  # wrong action
    assert not store.allowed(Identity("Ava", SOUL), g, "read", 3)  # wrong holder
    store.revoke("g1")
    assert not store.allowed(ident, g, "read", 3)  # revoked beats window


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} next-upgrade tests pass")
