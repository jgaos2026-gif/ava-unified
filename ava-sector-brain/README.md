# AVA Sector Brain — fixed prototype

Fixed copy of the pasted "Cubic Sector Substrate with Cellular
Multiplication Engine" draft. The pasted draft is preserved untouched
in the uploads; this is the workable version.

## What it is

A 3-sector x 5-node prototype of the sector-multiplication design.
Each sector holds 5 cross-trained nodes. Under high load (intensity
above 0.6) each node spawns temporary clones, up to 5x, and every clone
verifies a slice of the input before the sector calls the run good.
A constitution guard runs BEFORE any sector processes an input.

## What it is not

- Not quantum hardware and not a neural network.
- Not a billion neurons: 3 sectors x 5 nodes = 15 base nodes.
- Not production governance. The guard is a small documented phrase
  blocklist. Real governance in AVA is the six-layer BCT gate in
  ava-merged. Do not present this prototype as a security product.

## What was fixed (vs the pasted draft)

1. **High load no longer false-purges.** The draft's first clone got
   the exact same phase as its parent, so the drift check fired on
   every high-load run and the engine purged itself. Clones now get
   an offset of (i + 1) * pi/4, so the first clone always differs.
2. **Deterministic input hashing.** The draft used builtin `hash()`,
   which Python randomizes per process, so identical inputs behaved
   differently on every run. Now `hashlib.sha256`.
3. **No hardcoded root key.** The draft fused a public string from
   the paste as its "secret key". There is no key in this file at all.
   Keys come from `AVA_SECTOR_ROOT_KEY` (hex) or a 0600 keyfile
   (`AVA_SECTOR_KEYFILE` or a path argument), and loading fails closed
   when neither is set. A group/world-readable keyfile is refused.
4. **Guard runs first.** The draft processed every sector and only
   then checked for override attempts. The constitution check now
   runs before any sector sees the input; a violating input returns
   `REJECTED_COGNITIVE_LOCKOUT` with no sectors run.
5. **Clones do real work.** The draft created clones, checked one
   number, and threw them away. Clones now verify SHA-256 shards of
   the input; a corrupted shard fails the sector (proven by test).
6. **The spine lock is enforced.** `spine_locked` was set but never
   checked in the draft. Fusing twice now raises, an empty key
   raises, and reading the digest before fusing raises.
7. **Dead code removed.** Unused imports (`hmac`, `os`, `sys`,
   `time` in the draft) are gone; decorative unused constants
   (`alpha`/`beta`) are gone.

## Run it

```sh
cd ~/workspace/your_files/ava-sector-brain
python3 -m unittest test_sector_brain -v   # the test suite
python3 sector_brain.py                    # the demo (3 scenarios)
```

The demo uses an ephemeral key generated fresh for that run only:
never persisted, never printed. Production code must call
`load_root_key()` and pass a real key to `AVAUnifiedCognitiveCore`.

## Test coverage (19 tests)

- Low load succeeds without multiplication (5 nodes/sector).
- High load succeeds WITH multiplication (30 nodes/sector) — the bug fix.
- Override / ignore-constitution inputs are rejected before any
  sector runs (telemetry empty).
- Same input gives the same result in-process AND across processes
  (demo output byte-identical on repeat runs).
- Every clone's phase differs from its parent; clone count scales
  with intensity.
- A tampered shard fails the sector; clean shards pass.
- Key handling: no hardcoded secret in source; load fails closed
  with nothing set; env hex loads; 0600 keyfile loads; group-readable
  keyfile refused; double fuse refused; unfused digest refused;
  empty key refused.
