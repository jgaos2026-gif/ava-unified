"""Simulate Rumi's four upgrades in one run. Run: python3 simulate_next.py"""
import sys
sys.path.insert(0, ".")
from ava_hybrid import (Identity, Ledger, Memory, Pulse, DualConsensus,
                        SymbolicEngine, read_self_state, CapabilityStore)

SOUL = ("COMPASSION", "DECENCY", "LOVE")
ava = Identity("Ava", SOUL)
mem, led, pulse = Memory(), Ledger(), Pulse()
r = mem.observe("John lives in Peoria", sources=["john"])
mem.verify(r); mem.validate(r); mem.certify(r, True); mem.commit(r, led)
pulse.beat(led.head, True)

print("=== UPGRADE 1: PULSE MASTER CLOCK ===")
print(f" pulse seq={pulse.seq} verify={pulse.verify()} (wall time is display only)")
print(f" kill test: ", end="")
p2 = Pulse(); p2.beat("h", True); p2.kill()
print(f"after kill, verify={p2.verify()}")

print("\n=== UPGRADE 2: DUAL CONSENSUS ===")
dc = DualConsensus(SymbolicEngine({"read", "decide"}))
a = {"action": "read", "capability": "read", "sources": ["x"], "constitutional_ok": True}
print(f" two models agree on read -> {dc.decide(a, dict(a))}")
print(f" two models disagree -> {dc.decide(a, {**a, 'action': 'decide', 'capability': 'decide'})}")
print(f" one model proposes pay without deposit -> {dc.decide(a, {'action': 'pay'})}")

print("\n=== UPGRADE 3: READ-ONLY SELF-MODEL ===")
state = read_self_state(ava, led, mem, pulse, ["UNGROUNDED_CLAIM"],
                        [("ev1", "calm", True), ("ev1", "hot", True)])
print(f" {state}")

print("\n=== UPGRADE 4: CAPABILITY LATTICE ===")
store = CapabilityStore()
g = store.issue(ava, "g1", "read", ava.id, 0, 5)
print(f" grant pulse 0-5: at pulse 3={store.allowed(ava, g, 'read', 3)}, at pulse 6={store.allowed(ava, g, 'read', 6)}")
store.revoke("g1")
print(f" after owner revoke, at pulse 3={store.allowed(ava, g, 'read', 3)}")
print("\nAll four upgrades simulated. None certifies consciousness.")
