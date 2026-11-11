# AVA Merged — one upgraded system

Built 2026-11-03 at John's "Merge". This package merges, into ONE
codebase with ONE launcher:

- **ava-nextgen-fixed** (corrected FastAPI services): brain 8773,
  sovereign orchestrator 8775, private vault 8776 (PIN-derived key),
  embedding braid 8781 (token-hash, not Q8), real 11-way allocator,
  gateway.py, measured health checks.
- **ava-combined** stdlib services that NextGen did not rewrite:
  voice 8772, stitch 8774, organism core 8780, tool sandbox 8782,
  plus on-demand quant benchmark and performance governor.
- **Both HTML pages merged into one**: `ava-sovereign-core.html` —
  the wired visualizer (live NextGen calls, safe calculator, client
  screening) PLUS the runtime engine's real hash-chain ledger
  (canonical JSON + SHA-256 + Audit Chain verify button).

One service per port, no conflicts. The old stdlib vault, brain,
braid, and orchestrator are NOT included — the corrected NextGen
versions replace them, because the old vault carried an exposed PIN
hash.

## Run
```bash
pip install -r requirements.txt
export AVA_VAULT_PIN_HASH=<sha256 hex of a NEW PIN, after rotation>
python ava_merged.py          # all 8 services, Ctrl-C / SIGTERM stops them all
python gateway.py --demo      # 11VT check + one orchestration cycle
# Open ava-sovereign-core.html on the same machine as the services.
# Docker: docker compose up --build -d (no secret is baked into the image)
```

## Tested here (2026-11-03)
- Unit tests: 6/6 pass (real 11VT, vault persistence, embedding honesty).
- Live mesh: all 8 ports answered /health from one launcher.
  Voice, brain, orchestrator, vault, braid, sandbox: ok:true.
  Stitch and organism: ok:false / UNRESOLVED — that is their own
  state (no brain endpoint / no model on this machine), and the
  health check reports them DEGRADED, not ONLINE. Orchestrator
  returned vector_context_injected:false with brain_fallback:true
  (labeled, not faked).
- Shutdown: SIGTERM to the launcher now stops the launcher AND all
  8 children (verified — all ports down after). An earlier launcher
  version left children orphaned; that bug was found in testing and
  fixed with explicit signal handlers + child termination.
- Merged HTML: tags balanced, JS syntax OK (node --check), chain
  logic (canonical JSON + verify) carried over from the runtime
  engine page, safe calculator carried over from the wired page.

## NOT merged in / NOT claimed
- A neural embedding model, a real ollama model, Streamlit UI run,
  Docker build — none exist on this machine, none claimed.
- The old AVA starting files are NOT deleted by this merge. They
  still exist in their original places until John confirms deletion
  (to trash, recoverable) after verifying this merged package.

## Merged everything (2026-11-03, v3 + docs)
- Merged HTML page (`ava-sovereign-core.html`) now carries the v3
  branding: SB-688 Mesh header, John E. Arenz / JGA attribution, and
  the JGA Architectural Intellectual Property section. Wiring is
  unchanged (live NextGen calls, safe calculator, client screening).
- Simulation mode added to the merged page (checkbox, "Simulation
  mode (no services)"): runs screening + local calculator + chain
  append with every result labeled SIMULATION, and NO fake scores —
  unlike the v3 page, which hardcoded 0.948 / 0.998. Use it to demo
  on a machine with no services running.
- Docs folder added: `docs/ava-sovereign-66-draft.md` (design draft,
  not built) and `docs/ava-complete.md` (document, not code).
- NOT merged into the services: the AVA hybrid prototype. It is a
  separate generation (identity/ledger/gateway, no HTTP services)
  and merging it into this runtime would mix two AVAs. It stays
  separate unless John explicitly orders it merged.
