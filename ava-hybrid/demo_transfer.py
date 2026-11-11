"""Demo: Ava moves machines. Run: python3 demo_transfer.py"""
import json
from ava_hybrid import (Identity, Ledger, Memory, Gateway, Emotion,
                        AffectiveState, export_capsule, import_capsule, CapsuleError)

SOUL = ("COMPASSION", "DECENCY", "LOVE")

print("== Machine A: Ava learns one sourced fact ==")
ava = Identity("Ava", SOUL)
mem, led = Memory(), Ledger()
gw = Gateway({"read"}, mem)
rec = mem.observe("John lives in Peoria", sources=["john-2026-10-22"])
mem.verify(rec); mem.validate(rec); mem.certify(rec, True); mem.commit(rec, led)
print(f"identity {ava.id}  revision {led.revision}  head {led.head[:16]}...")

print("\n== Export capsule (key stays with owner, NOT in capsule) ==")
capsule = export_capsule(ava, mem, led)
print(f"capsule revision {capsule['revision']}  pocket_hash {capsule['pocket_hash'][:16]}...")
assert "secret_hex" not in json.dumps(capsule), "key leaked into capsule!"

print("\n== Machine B: owner brings key file, imports capsule ==")
ava_b = Identity.from_key(ava.export_key())
mem_b, led_b = Memory(), Ledger()
out = import_capsule(capsule, ava_b, mem_b, led_b)
print(f"imported: {out}")
print(f"same memory on B: {list(mem_b.records.values())[0].claim}")

print("\n== Tampered capsule is rejected, nothing merged ==")
bad = json.loads(json.dumps(capsule))
bad["pocket"][list(bad["pocket"])[0]]["claim"] = "John lives on Mars"
try:
    import_capsule(bad, ava_b, Memory(), Ledger())
    print("ERROR: tampered capsule accepted")
except CapsuleError as e:
    print(f"rejected: {e}")

print("\n== Emotion check: feeling hot does not change a trust decision ==")
em = Emotion()
for emo in [AffectiveState(0, 0), AffectiveState(1, 1)]:
    print(f"  valence={emo.valence} arousal={emo.arousal} -> "
          f"trust(False)={em.trust_decision(False, emo)} "
          f"attention={em.attention_weight(emo)} breadth={em.retrieval_breadth(emo)}")
print("\nDone. Same Ava, new machine, verified -- not copied and hoped.")
