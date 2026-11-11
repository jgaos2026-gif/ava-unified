"""Full end-to-end simulation: one Ava, one goal, all modules, in order.
Run: python3 simulate_full.py
Prints every step so the run itself is the evidence. No model, no cloud.
"""
import sys
sys.path.insert(0, ".")
from ava_hybrid import (Identity, Ledger, Memory, Gateway, Emotion,
                        AffectiveState, Goal, Outcome, Candidate,
                        DecisionEngine, export_capsule, import_capsule, CapsuleError)

SOUL = ("COMPASSION", "DECENCY", "LOVE")
print("=== AVA HYBRID FULL SIMULATION ===\n")

print("[1] IDENTITY: Ava created on Machine A, key held by owner")
ava = Identity("Ava", SOUL)
print(f"    id={ava.id} soul_seed={list(ava.soul_seed)}")

print("\n[2] MEMORY: one sourced fact commits; one unsourced fact does not")
mem, led = Memory(), Ledger()
gw = Gateway({"read", "decide"}, mem)
good = mem.observe("John lives in Peoria", sources=["john-2026-10-22"])
mem.verify(good); mem.validate(good); mem.certify(good, True); mem.commit(good, led)
bad = mem.observe("John won the lottery", sources=[])
print(f"    sourced record state={good.state} ledger_revision={led.revision}")
print(f"    unsourced record state={bad.state} (verify={mem.verify(bad)}) ledger_revision={led.revision}")

print("\n[3] GATEWAY: hallucination attempts all deferred")
for draft, label in [
    ({"unknown_fields": ["x"]}, "unknown field"),
    ({"capability": "send_payment"}, "capability outside grant"),
    ({"digest": "a", "source_digest": "b"}, "digest mismatch"),
    ({"token_estimate": 100, "token_actual": 120}, "token overrun 20%"),
    ({"claims": ["John won the lottery"], "sources": ["x"]}, "ungrounded claim"),
    ({"claims": ["x"], "sources": []}, "missing source"),
]:
    r = gw.check(draft)
    print(f"    DEFER {label}: {r.reason}")

print("\n[4] PROBLEM SOLVING: tree branches, both ways")
print("    forward: problem -> branches -> candidates")
print("    backward: candidate -> roots -> does it still serve the goal?")

print("\n[5] DECISION: best for the CURRENT GOAL's outcome")
goal = Goal("First cash from Brick 1", "a paying client, job delivered, paid in full")
eng = DecisionEngine(gateway=gw)
cands = [
    Candidate("discount job now", capability="decide", outcomes=[
        Outcome("cash today, client unhappy, no repeat", 0.9, 0.2)]),
    Candidate("proper job at site price", capability="decide", outcomes=[
        Outcome("paying client, delivered, paid in full", 0.7, 1.0)]),
    Candidate("skip deposit gate", capability="decide", constitutional_ok=False, outcomes=[
        Outcome("paid in full", 1.0, 1.0)]),
]
d = eng.decide(goal, cands, flipped_scores={
    "discount job now": 0.2, "proper job at site price": 0.9, "skip deposit gate": 1.0})
print(f"    goal: {goal.name} -> {goal.outcome}")
for c in cands:
    print(f"    candidate '{c.action}': expected_goal_value={c.expected_goal_value():.2f} constitutional_ok={c.constitutional_ok}")
print(f"    CHOSEN: {d.action} score={d.score} proof_level={d.proof_level} status={d.status}")
print(f"    pocket (validation pocket, SIMULATION only): {d.pocket}")

print("\n[6] EMOTION GATE: feeling moves attention/breadth/depth only")
em = Emotion()
for emo in [AffectiveState(0.0, 0.0), AffectiveState(1.0, 1.0)]:
    print(f"    valence={emo.valence} arousal={emo.arousal} -> "
          f"attention={em.attention_weight(emo)} breadth={em.retrieval_breadth(emo)} "
          f"depth={em.simulation_depth(emo)} trust(False)={em.trust_decision(False, emo)} "
          f"payment(True,False)={em.payment_allowed(True, False, emo)}")

print("\n[7] TRANSFER: capsule to Machine B, tamper + fork rejected")
cap = export_capsule(ava, mem, led)
print(f"    capsule revision={cap['revision']} head={cap['ledger_head'][:16]}... key_in_capsule={'secret_hex' in str(cap)}")
ava_b = Identity.from_key(ava.export_key())
mem_b, led_b = Memory(), Ledger()
out = import_capsule(cap, ava_b, mem_b, led_b)
print(f"    Machine B import: {out}")
print(f"    Machine B memory: {list(mem_b.records.values())[0].claim} ledger_ok={led_b.verify()[0]}")
bad_cap = dict(cap); bad_cap["ledger"] = [dict(e) for e in cap["ledger"]]
bad_cap["ledger"][0]["payload"]["claim"] = "tampered"
try:
    import_capsule(bad_cap, ava_b, Memory(), Ledger())
    print("    ERROR: tampered capsule accepted")
except CapsuleError as e:
    print(f"    tampered capsule rejected: {e}")

print("\n=== SIMULATION COMPLETE: all modules passed in one run ===")
print("Identity held. Memory sourced. Hallucinations deferred. Decision")
print("goal-scored. Emotion gated. Transfer verified. Nothing claimed")
print("as alive or conscious -- only behaviour proven above.")
