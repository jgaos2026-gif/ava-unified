# JGA Hybrid System — the OTHER systems, combined under one governor

Built 2026-11-03 at John's "Combine all other system file to create a
hybrid system". This is the second combined system, alongside
jga-ultimate (the operations system). Originals are untouched; this
folder holds copies, nothing was moved or deleted to make it.

## What "hybrid" means here, honestly
One governor — the AVA hybrid Gateway + DecisionEngine — sitting over
separate sealed subsystems. The ledgers are **never fused into one
chain**: the hybrid memory ledger, the MicroSpine chain, the JGA OS
event chain, and the Entertainment Brick ledger each keep their own
seals, because merging chains would destroy their tamper evidence.
Hybrid = governed together, not fused.

Every hybrid decision is labeled SIMULATION until it passes
OBSERVED -> VERIFY -> VALIDATE -> CERTIFY -> COMMIT. A simulation
never becomes a committed fact, and the governor cannot override a
gate: a candidate failing a constitutional or trust check is skipped,
however high it scores.

## Inside (copies)
- `subsystems/ava_hybrid/` — identity, memory, gateway, decision,
  emotion, capsule, did, zk, symbolic, dream, consensus, selfmodel,
  capability, pulse. No LLM wired in, no consciousness claim.
- `subsystems/micro_spine.py`, `bct_gatekeeper.py`, `ed25519.py` —
  append-only ledger + gatekeeper (pure-Python Ed25519, not
  constant-time hardened).
- `subsystems/pulse_*.py` — pulse prototype (scratch; needs a haven
  server to run live — included, not run live here).
- `subsystems/jga_full_auto/` — full Brick 1 pipeline (mock drafting;
  John is the designer until an engine is chosen; Phase B gate unmet).
- `subsystems/entertainment_brick/` — full Entertainment Brick.
- `subsystems/phoenix_kernel/` — Rust braid kernel v0.3.0 (see its
  README; run `cargo test` in that folder to re-verify).

## Commands
```
python hybrid.py check
python hybrid.py govern --claim "TEXT" --source NAME
python hybrid.py decide
```

## What it does NOT do
- No LLM, no live AI model, no bank movement, no message sent,
  no file released, no outreach, no publishing — same gates as
  ultimate. Money splits only on cleared money, receipt-only.
- Does NOT include the Windows CONTROL_ROOM files (never vetted here).
- Does NOT replace jga-ultimate. Ultimate runs operations; this
  hybrid governs claims and decisions. Use both, in that order:
  govern a claim here, act on it in ultimate only when it is COMMIT
  and its gates are satisfied.
