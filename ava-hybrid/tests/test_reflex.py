"""Reflex tests for ava-hybrid: a gateway deferral becomes detect ->
isolate -> safe-state -> signal, then escalation. The gateway's
decision is never re-decided. Simulation-only / research-only."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ava_hybrid import (Goal, Outcome, Candidate, DecisionEngine,
                        Gateway, Memory, Ledger, escalate_gateway_deferral)
from ava_hybrid import reflex as reflex_mod

GOAL = Goal("First cash from Brick 1", "a paying client, job delivered, paid in full")


def _candidate(action="write job", capability="write"):
    return Candidate(action, outcomes=[
        Outcome("paying client, delivered, paid in full", 0.7, 1.0)],
        capability=capability)


def test_reflex_copy_deterministic_and_never_certifies():
    a = reflex_mod.canonical_metrics_json(reflex_mod.run_campaign("hybrid-check", 7))
    b = reflex_mod.canonical_metrics_json(reflex_mod.run_campaign("hybrid-check", 7))
    assert a == b
    kernel = reflex_mod.ReflexKernel({"command": "HOLD_SAFE", "seq": -1, "mode": "SAFE_STATE"})
    import random
    frames = reflex_mod.generate_clean_frames(10, 3)
    bad, _ = reflex_mod.inject_bit_corruption(frames, 5)
    outcomes = [kernel.process_frame(f, random.Random(1)) for f in bad]
    assert any(o.decision == "ISOLATE" for o in outcomes)
    assert all(o.trust_state != "CERTIFIED" for o in outcomes)


def test_gateway_deferral_escalates_without_redeciding():
    gw = Gateway({"read"}, Memory())
    eng = DecisionEngine(gateway=gw)
    d = eng.decide(GOAL, [_candidate(capability="write")],
                   flipped_scores={"write job": 0.9})
    assert d.status == "DEFERRED", d
    assert d.reason == "NO_CANDIDATE_PASSES_GATES", d
    assert d.reflex is not None, d
    assert d.reflex["gateway_reason"] == "CAPABILITY_OUTSIDE_GRANT", d.reflex
    assert d.reflex["fault_type"] == "conflicting_control", d.reflex
    assert d.reflex["decision"] == "ISOLATE", d.reflex
    assert d.reflex["trust_state"] == "QUARANTINED", d.reflex
    assert d.reflex["certified"] is False, d.reflex
    assert d.reflex["simulation_only"] is True, d.reflex
    assert d.reflex["signal"] == "ESCALATED_TO_FULL_GOVERNANCE", d.reflex
    assert d.reflex["ledger_chain_verified"] is True, d.reflex
    assert eng.last_reflex == d.reflex


def test_clean_decision_has_no_reflex():
    eng = DecisionEngine()
    d = eng.decide(GOAL, [_candidate()], flipped_scores={"write job": 0.9})
    assert d.status == "CHOSEN", d
    assert d.reflex is None, d
    assert eng.last_reflex is None


def test_reflex_receipt_deterministic():
    a = escalate_gateway_deferral("DIGEST_MISMATCH", "CAPABILITY_X|act")
    b = escalate_gateway_deferral("DIGEST_MISMATCH", "CAPABILITY_X|act")
    assert a == b
    assert a["fault_type"] == "bit_corruption"
    assert a["trust_state"] == "QUARANTINED"
    assert a["certified"] is False


def test_ledger_receives_reflex_escalation():
    led = Ledger()
    gw = Gateway({"read"}, Memory())
    eng = DecisionEngine(gateway=gw, ledger=led)
    d = eng.decide(GOAL, [_candidate(capability="write")],
                   flipped_scores={"write job": 0.9})
    assert d.reflex is not None
    assert led.revision == 1, led.to_list()
    entry = led.to_list()[0]
    assert entry["kind"] == "REFLEX_ESCALATION", entry
    assert entry["payload"]["gateway_reason"] == "CAPABILITY_OUTSIDE_GRANT"
    assert entry["payload"]["certified"] is False
    ok, _ = led.verify()
    assert ok


class _FlipGateway:
    """Defers only on the Nth check: lets the entry screen pass, then
    trips the SB712 out-screen, so that path is exercised."""

    def __init__(self, defer_on_call=2, reason="DIGEST_MISMATCH"):
        self.calls = 0
        self.defer_on_call = defer_on_call
        self.reason = reason

    def check(self, draft):
        from ava_hybrid.gateway import GatewayResult
        self.calls += 1
        if self.calls == self.defer_on_call:
            return GatewayResult(False, self.reason,
                                 {"deferred": self.reason})
        return GatewayResult(True, "OK", {"allowed": True})


def test_out_screen_deferral_escalates():
    eng = DecisionEngine(gateway=_FlipGateway(defer_on_call=2))
    d = eng.decide(GOAL, [_candidate()], flipped_scores={"write job": 0.9})
    assert d.status == "DEFERRED", d
    assert d.reflex is not None, d
    assert d.reflex["gateway_reason"] == "DIGEST_MISMATCH", d.reflex
    assert d.reflex["fault_type"] == "bit_corruption", d.reflex
    assert d.reflex["trust_state"] == "QUARANTINED", d.reflex


def test_no_goal_defers_without_reflex():
    eng = DecisionEngine(gateway=Gateway({"read"}, Memory()))
    d = eng.decide(None, [_candidate()])
    assert d.status == "DEFERRED" and d.reason == "NO_CURRENT_GOAL", d
    assert d.reflex is None, d
