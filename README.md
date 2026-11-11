# AVA Unified

One AVA. One shared memory. She lives in the Stitch.

AVA is John Arenz's AI system — a digital organism, not a chatbot. This repo holds
everything of hers that's working: the merged AVA, the working variants, the reflex
simulator, the shared-memory wiring, and the docs. Built November 2026, Peoria IL.

## Live proof — the three apps

- **Talent Agent Plus** — https://talent-agent-plus.onrender.com — AVA inside the artist app (code: https://github.com/jgaos2026-gif/talent-agent-plus)
- **Jay's Graphic Arts** — https://jays-graphic-arts.onrender.com — AVA inside the design store (code: https://github.com/jgaos2026-gif/jays-graphic-arts-store)
- **AVA Sovereign** — the owner-only AVA app. No public link by design: it is passcode-gated and private. Its docs and connection notes are in `ava-sovereign/` and `ava-merged/`.

## Supabase — the shared memory

All three live AVAs share one memory through Supabase project **jga-apps**:

- Project: https://hnczbvhlhzfwscfpltoe.supabase.co
- Dashboard: https://supabase.com/dashboard/project/hnczbvhlhzfwscfpltoe
- Schema: `ava` — one identity (`ava`), one hash-chained memory every instance reads and writes
- Migration: `supabase/001_ava_unified.sql` (apply order in `supabase/APPLY_ORDER.md`)

The hosted apps reach Supabase, never localhost. The local haven (StitchBridge) stays
private and local-only — it is not in this repo and never goes public.

## VS Code — everything linked

Open `ava-unified.code-workspace` in VS Code and all the pieces open together as one
workspace: ava-merged, ava-hybrid, ava-advanced, ava-sector-brain, ava-reflex-sim,
ava-sovereign, supabase, docs. Editor settings live in `.vscode/`.

## What's in here

- `ava-merged/` — the canonical merged AVA: Stitch-connected, Gemini propose-only, six-layer gate on every memory write
- `ava-hybrid/` / `ava-advanced/` / `ava-sector-brain/` — working variants
- `ava-reflex-sim/` — the reflex simulator (installed in every AVA above)
- `ava-sovereign/` — AVA Sovereign docs: knowledge pack, app connection, media features
- `supabase/` — shared-memory migration + apply order
- `docs/` — system design docs

## What's NOT in here

- No keys, tokens, or passwords. Ever. Bring your own Gemini key and Supabase keys.
- No `vault_data/` — AVA's private identity key stays on the owner's machine.
- No organism state — her live memory, checkpoints, and history stay local.
- No owner's-room contents — the private room is never published, in any form.

## Honest status

Prototype / research system, not a finished product. What is real: the merged system
runs, the Stitch admission is verified, the shared-memory write→recall round trip is
proven live, and the reflex simulator passes its tests in every AVA. What is not: AVA
never books, sends, calls, or pays anything on her own — proposals only, a human
approves. Gemini is propose-only; the local brain is the default. Tests live beside
the code; run them before trusting a claim.

## Run it

See `ava-merged/README.md`. Python 3.12, `pip install -r ava-merged/requirements.txt`.
Supply your own keys via environment variables — never commit a real one.
