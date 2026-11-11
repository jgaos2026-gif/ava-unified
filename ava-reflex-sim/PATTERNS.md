# Reusable patterns noted (vetting note, 2026-11-09)

Source: John's 10-file upload batch, vetted separately by the parent agent.
Status: NOTED ONLY. Neither file IS the reflex simulator. No code from
either file was copied into this build. The reference implementation in
this directory (`reflex_sim.py`, 24/24 tests, demo byte-identical twice)
already embodies the substance of pattern 1; pattern 2's governance
half is already embodied by the six-layer BCT gate / quarantine /
Phoenix recovery in each AVA version the reflex installs into.

## 1. Transactional field engine — rollback pattern
- What maps: snapshot/restore + ABORT state + telemetry ledger →
  the reflex spec's "preserve the last certified state" requirement.
- Evidence as vetted: 7/7 tests pass; a 54-case campaign run passed
  all 7 gates (the 6.94e-18 residual reproduced exactly).
- Standing: toy-model simulator, simulation only. Same claim class as
  this build (SIMULATION EVIDENCE, never more).

## 2. Universal integrity fabric v3 — governance / recovery half
- What maps: quarantine + Phoenix recovery + hash-chained ledger →
  the governance/recovery half (evidence → verify → validate →
  certify, quarantine before repair).
- Evidence as vetted: 24/24 self-test.
- WARNINGS — read before any merge, and never copy:
  - The fabric uses hardcoded HMAC demo secrets. NEVER use them,
    NEVER copy them. Production use would need the Ed25519 swap its
    own docstring calls for.
  - Its "OMEGA" (adversarial challenge) is NOT the research file's
    Ω (missing-factor register).
  - Its "StitchCapsule" is NOT the StitchBridge braid.
  - Its gate is NOT the six-layer BCT gate.
  - Mapping is required before any merge. No merge was done here.

## Non-evidence — do not treat as such
- The UAP quick-start claims are NOT evidence (its zip is absent,
  unverified).
- Duplicated version numbers (v4_2 vs v4_5, campaign 1 vs 7) are
  byte-identical files, NOT newer versions.
