# BCT Phoenix Braid Kernel

This crate is the hardened replacement for the earlier `phoenix_garisde.rs` draft.

## Why it changed

The earlier draft mixed several ideas that should not be treated as equivalent:

1. A permutation is not enough to represent a general braid.
2. A true Garside left normal form needs correct simple-element lattice operations; the original `meet_left()` shortcut was not sufficiently justified.
3. `Delta^-1` cannot be reconstructed by only flipping signs. Inversion reverses generator order **and** flips signs.
4. A logical contradiction is not automatically a mathematical knot.
5. Phoenix should not blindly execute inverse business operations. The algebraic inverse is used to verify history; actual recovery restores a certified checkpoint and re-verifies it.
6. Fixed boundary indices such as `sigma_22` are only initially domain boundaries. Once strands braid, semantic strand identities move. The kernel therefore tracks labeled strand identities separately from braid positions.

## What this version uses instead

The algebraic verifier uses the faithful Artin representation:

`B_n -> Aut(F_n)`

For generator `sigma_i`:

- `x_i -> x_i x_{i+1} x_i^-1`
- `x_{i+1} -> x_i`

For `sigma_i^-1`:

- `x_i -> x_{i+1}`
- `x_{i+1} -> x_{i+1}^-1 x_i x_{i+1}`

Within configured memory/trace bounds, equality of the resulting automorphisms gives exact braid-group equality.

## Hardening (v0.2.0, 2026-11-02, draft — NOT production)

- Phoenix now distinguishes three things: committed verified history,
  candidate braid, and evidence. Evidence is quarantined, never inverted,
  and never included in the proof trace (`plan_phoenix_recovery_with_evidence`).
  The older `plan_phoenix_recovery` is kept for compatibility but treats
  everything after the verified prefix as the candidate.
- Randomized property tests (deterministic seed, no external crates):
  500 random words and 200 negative-only words with w·w⁻¹ = identity,
  200 randomized Artin rewrites, negative-generator normalization checked
  against the Artin formula for every index on 66 strands, and 66-strand
  boundary cases (1, 22/23, 58/59, 65).
- Resource-limit enforcement is tested (trace length).
- A separate Python Artin oracle (substitution method, different code)
  independently checked 2,000 random relation/inverse checks with 0 failures,
  plus the 66-strand boundaries.
- Still NOT included: a true Garside normal form, cryptographic
  authentication of GateProof flags, or an independent oracle comparison
  against a published braid library. Those are the remaining gates before
  any production claim.

## Build and test

```bash
cargo test
```

No external crates are required.

## BCT integration

Use this crate underneath the Braid ISA algebraic plane for:

- exact inverse verification
- Artin-relation tests
- equivalence checks
- Phoenix recovery proof generation
- semantic strand-boundary enforcement

Keep cryptographic signatures, SHA-256 commitments, capability envelopes, SQLite/WAL durability, and external witness logic in their existing higher layers.

## Hardening v0.3.0 (2026-11-02, at John's "add fix test harden" — draft, NOT production)
- Strand-count upper bound: MAX_STRANDS = 66, enforced in every constructor
  (BraidWord, BraidAction, LabeledTopology, Generator validation). This bounds
  identity-action allocation; larger `n` is out of scope for this kernel.
- Checked total-action arithmetic: the action total is accumulated with
  `checked_add`; overflow is an error, not a wrap.
- VerifiedGateProof: a proof type buildable only through `verify_gate_proof`,
  which refuses non-GREEN certification, any false flag, missing proof id,
  empty evidence hash, or empty authority id. HONEST LIMIT: this is a
  structural verifier, not a cryptographic signature verifier — signature
  verification still belongs in the Gatekeeper layer above.
- Durable checkpoint: `Checkpoint::to_text` / `from_text` (BCT-CKPT/1, FNV-1a
  checksum). Restore recomputes the Artin action and refuses a checkpoint
  whose checksum, strand count, generators, or action total disagree.
  A forger who recomputes the checksum can forge it — production checkpoints
  must also be sealed by the higher layer.
- Tests: 21/21 pass (18/18 from v0.2.0 + 3 new v0.3.0 tests).
- Still NOT included: a true Garside normal form, cryptographic
  authentication of GateProof flags, or comparison against a published
  braid library. Those gates remain before any production claim.
