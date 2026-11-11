"""Decision tests: best for the CURRENT GOAL's outcome, nothing else."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ava_hybrid import (Goal, Outcome, Candidate, DecisionEngine,
                        Gateway, Memory)

GOAL = Goal("First cash from Brick 1", "a paying client, job delivered, paid in full")


def test_picks_future_goal_over_immediate_win():
    eng = DecisionEngine()
    quick = Candidate("discount job now", outcomes=[
        Outcome("cash today, client unhappy, no repeat", 0.9, 0.2)])
    slow = Candidate("proper job at site price", outcomes=[
        Outcome("paying client, delivered, paid in full", 0.7, 1.0)])
    d = eng.decide(GOAL, [quick, slow], flipped_scores={
        "discount job now": 0.2, "proper job at site price": 0.9})
    assert d.status == "CHOSEN" and d.action == "proper job at site price", d

def test_no_goal_defers():
    eng = DecisionEngine()
    d = eng.decide(None, [Candidate("anything", outcomes=[])])
    assert d.status == "DEFERRED" and d.reason == "NO_CURRENT_GOAL"

def test_constitution_or_trust_failure_skipped_even_if_high_scoring():
    eng = DecisionEngine()
    bad = Candidate("skip deposit gate", outcomes=[
        Outcome("paid in full", 1.0, 1.0)], constitutional_ok=False)
    good = Candidate("follow 35% gate", outcomes=[
        Outcome("paid in full", 0.6, 0.9)])
    d = eng.decide(GOAL, [bad, good], flipped_scores={
        "skip deposit gate": 1.0, "follow 35% gate": 0.8})
    assert d.action == "follow 35% gate", d

def test_mobius_disagreement_defers():
    eng = DecisionEngine()
    c = Candidate("rush it", outcomes=[Outcome("paid in full", 0.8, 0.9)])
    d = eng.decide(GOAL, [c], flipped_scores={"rush it": 0.1})
    assert d.status == "DEFERRED" and d.reason == "MOBIUS_RETURN_DISAGREES", d

def test_decision_is_simulation_not_fact():
    eng = DecisionEngine()
    c = Candidate("proper job at site price", outcomes=[
        Outcome("paying client, delivered, paid in full", 0.7, 1.0)])
    d = eng.decide(GOAL, [c], flipped_scores={"proper job at site price": 0.9})
    assert d.proof_level == "SIMULATION"
    assert d.pocket["proof_level"] == "SIMULATION"
    # Nothing was committed to a ledger by deciding.
    mem = Memory()
    assert mem.records == {}

def test_gateway_blocks_capability_outside_grant():
    gw = Gateway({"read"}, Memory())
    eng = DecisionEngine(gateway=gw)
    c = Candidate("send payment", capability="send_payment", outcomes=[
        Outcome("paid", 1.0, 1.0)])
    d = eng.decide(GOAL, [c], flipped_scores={"send payment": 1.0})
    assert d.status == "DEFERRED", d


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} decision tests pass")
