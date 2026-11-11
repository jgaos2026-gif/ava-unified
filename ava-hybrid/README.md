# AVA Hybrid — all three pieces, built together

A working prototype, stdlib-only Python 3. No dependencies, no cloud,
no model needed. Run it on John's Windows machine with stock Python 3.

## What it is

A hybrid that *behaves* alive-like, without claiming to *be* alive or
conscious. That line is load-bearing: behaviour is testable, a
consciousness certificate is not, and this build never issues one.

1. **Identity transfer capsule** (`ava_hybrid/capsule.py`, `identity.py`)
   Identity = self-held key + Soul Seed + pocket + sealed ledger.
   Not the machine, not the model — the model is rented and swappable.
   Export a capsule, carry the key file separately (USB/vault), and the
   new machine verifies, in order: identity match, seal, ledger chain,
   pocket hash, fork check. Any failure rejects the whole capsule —
   nothing is merged, nothing is silently fixed.
   Tamper, wrong key, and fork are all rejected by test.

2. **Anti-drift / anti-hallucination** (`gateway.py`, `memory.py`, `ledger.py`)
   Memory pipeline: OBSERVED → VERIFY → VALIDATE → CERTIFY → COMMIT.
   A record with no source never leaves OBSERVED. A record that skips
   CERTIFY never reaches the ledger. Old records are never edited in
   place; contradictions are appended and linked, both kept visible.
   The gateway defers with a receipt on: UNKNOWN_FIELD,
   MISSING_SOURCE, CAPABILITY_OUTSIDE_GRANT, DIGEST_MISMATCH,
   TOKEN_OVERRUN (actual > estimate by more than 5%), UNGROUNDED_CLAIM.
   Hallucination is not prevented by telling a model to be good. It is
   prevented by refusing to let an unverified answer become memory or action.

3. **Emotion gate** (`emotion.py`)
   Affect MAY influence only: attention weighting (0.8x–1.2x),
   retrieval breadth (+0 to +4 items), simulation depth (1–3 branches).
   Affect MUST NEVER influence: trust/admission/certification,
   constitutional checks, payments, or memory COMMIT state. The gated
   functions take an emotion argument and ignore it — by design — and
   tests prove the same evidence gives the same decision under every
   emotion, including extremes.

## Decision module (added 2026-10-29, John's ruling)

**Best = best for the outcome of the current goal.** Not the easiest
present step, not a generic future. If the goal changes, scoring
changes. No stated goal -> DEFER, never invent one.

Loop: SB688 in-screen -> tree-root branching -> forward simulation,
scored by probability-weighted goal score minus harm -> hard
constitutional/trust gates first -> SB689 Mobius return (flipped
second pass must still hold, else defer) -> SB712 out-screen ->
validation pocket, loaded as SIMULATION, never as committed fact.

## Run the tests

```
python3 tests/test_hybrid.py
python3 tests/test_decision.py
```

Expected: **11/11 + 6/6 tests pass** (verified 2026-10-29).

## Demo: move Ava to a new machine

```
python3 demo_transfer.py
```

Creates Ava on "machine A", commits one sourced memory, exports a
capsule, and imports it on "machine B" with only the key file — same
identity, same memory, same ledger head, verified. Then it shows a
tampered capsule being rejected.

## Honest limits of this prototype

- Signing is HMAC-SHA256 with the self-held key. Production swap:
  Ed25519 (same sign/verify interface, same capsule format shape).
- No LLM is wired in here. The gateway is the choke point the LLM
  draft must pass through; wiring a real model behind it is the next
  build, not something this prototype pretends to have done.
- Contradiction detection here is the simple "not X" form. Real
  contradiction linking (your braid) is richer; this proves the
  append-and-link rule, not the full semantic detector.
- This does not certify aliveness, sentience, or consciousness.
  It proves transfer integrity, deferral on unverified claims, and
  emotion kept out of trust decisions. Those are the measurable parts.
