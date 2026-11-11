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

## LLM connector (added 2026-11-04, NOT live yet)
- `llm_connector.py` — standalone module, NOT wired into brain/orchestrator.
  Model proposes text only; tool-shaped responses are DEFERRED, never executed.
  Key comes only from env `AVA_LLM_API_KEY`, never from a file or chat.
  Provider from `AVA_LLM_PROVIDER` (default gemini after John's 2026-11-04 switch; OpenAI connected but unused for AVA),
  model from `AVA_LLM_MODEL` (no default — unset means NOT_CONNECTED).
- Tests: `python -m unittest tests.test_llm_connector` — 5/5 offline.
  Live status right now: llm_connected=false (NO_API_KEY, NO_MODEL_SET).
  Do NOT claim AVA is live-connected until a real API call returns a proposal.
- NOT built yet: wiring into /inference or /orchestrate, persistent
  conversation history, six-division access. Those are separate steps
  after the live test passes.

- Gemini support (2026-11-04): `llm_connector.py` now supports gemini via
  POST generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
  with x-goog-api-key header (not Bearer). Connector tests 6/6 offline.
  Gemini key entry sent 2026-11-04 ~21:31 CST via custom.gemini connector.
  Model name still NOT chosen by John; live connection must NOT be claimed
  until a real Gemini call returns a proposal.

## LIVE GEMINI TEST (2026-11-04, via custom.gemini connector, NOT via chat-pasted key)
- Gemini credential connected via Secure Vault (custom.gemini).
- list-models returned 50 models for the connected key.
- propose with gemini-3.5-flash returned PROPOSED, one-sentence greeting.
  That model was a test choice, NOT a locked model decision by John.
- gemini-2.5-flash returned NOT_FOUND (no longer available to new users).
- Brain/orchestrator wiring and persistent history are STILL separate steps.

## GEMINI WIRING (2026-11-04, at John's "Do it")
- services/llm_vault_client.py: Gemini propose, x-goog-api-key header.
  Auth: AVA_LLM_API_KEY env, else custom.gemini vault surrogate. No key in code.
- Brain 8773 /inference and orchestrator 8775 /orchestrate accept
  use_llm (default false) + llm_model. Proposal is additive only in
  llm_proposal / llm_status; it never replaces the completion, never
  executes, and default requests are unchanged (verified live).
- Live test 2026-11-04: brain use_llm with gemini-3.5-flash returned
  llm_status PROPOSED; orchestrator use_llm returned the same proposal
  through the brain. Test model only, NOT John's locked model choice.
- Unit tests: llm_connector 6/6 + llm_vault_client 3/3, total 9/9.
  Original core suite needs fastapi (installed only in a /tmp venv for
  this live test, not in the package) — live service test above is the
  wiring proof for brain/orchestrator.
## BUILD 2026-11-05 — items 1–4 (persistent history, STT, avatar, DEGRADED repair)

- **Item 1 — Persistent conversation history + six-division access.**
  `services_stdlib/history_store.py`: WARM JSONL store
  (`services_stdlib/AVA_ORGANISM/WARM/history.jsonl`), hash-chained,
  full-chain verification on mount, recallable by thread/cycle with a
  limit. Organism core 8780 now serves `GET/POST /history`,
  `GET /history/verify`, `GET /history/divisions`; `/chat` files each
  exchange under division MEMORY. Every write passes the six-layer
  BCT gate (identity, schema, crypto, braid, transaction, audit) and
  is stored only when CERTIFIED, otherwise quarantined to
  `history_quarantine.jsonl` with the failed layer named.
  **Six divisions — DEFINITION CHOICE, AWAITING JOHN'S RULING:** no
  division list exists anywhere in the workspace code (the JGA
  Enterprise OS zip, 28 files, and `ava-hybrid/` were both checked
  2026-11-05 and contain no "division" definition). The six are
  therefore the six BCT strands — EXECUTION, MEMORY, VERIFICATION,
  EVIDENCE, RECOVERY, GOVERNANCE — the only six-fold structure in
  John's canon, from the BCT paper. No other division names were
  invented. Every history read/write names its division; a caller
  without that division's scope is refused with the division named.
  Honest limit: scopes are a declared claim in the request, not an
  authenticated token — no auth token system exists in this package
  yet. Stage: WARM (HOT is the core's in-memory state +
  HOT/experience.jsonl; COLD is sealed archive, not built yet).
- **Item 2 — Listening/STT (browser only).** `ava-sovereign-core.html`
  only, no server code: a mic button beside the input uses
  `window.SpeechRecognition || window.webkitSpeechRecognition`,
  interim results shown live, final transcript appended to the
  textarea. Labeled browser-side only; in Chrome audio is processed
  by the browser vendor's speech service. Feature-detected: where
  unsupported the button disables with an honest note. AVA has no
  server-side listening.
- **Item 3 — Avatar (browser only).** `ava-sovereign-core.html` only:
  an AVA avatar panel (display name, title; initials, one of 6 gold
  presets, or an uploaded photo stored as a data URL in localStorage)
  and the avatar shown in the page header. Browser-local only, labeled
  as such; no server avatar endpoint, nothing syncs.
- **Item 4a — Room server built, Stitch repaired.**
  `services_stdlib/room_server.py` on 127.0.0.1:8770 implements every
  endpoint stitch_bridge probes (`/api/status`,
  `/api/room/stitchbridge|spine|sb688/status`,
  `/api/room/stitchbridge/verify|event|cross`,
  `/api/room/ledger/append`), with a file-backed hash-chained ledger
  under `vault_data/` (WARM) and the six-layer gate on every append —
  malformed envelopes are rejected with the failed layer named and
  quarantined, never silently accepted. Wired into `ava_merged.py`
  (now 9 services) and `healthcheck.py`. Port 8770 was verified free
  in this VM before binding.
- **Item 4b — Organism /health fixed, no Ollama installed.**
  The organism core's own functions (heartbeat, state, ledger,
  memory) do not need a model to be alive, so `/health` now reports
  organism liveness from state load + ledger verification, and
  reports brain-model availability as a separate explicit field
  (`model: null`, state `LOCAL_MODEL_UNRESOLVED`). `/chat` still
  returns 503 with `LOCAL_MODEL_UNRESOLVED` when no model can answer
  — that failure is real and stays. Organism is ONLINE as a living
  core; the local model is still absent (installing Ollama is John's
  call, blocked, and was NOT done).
- **Tests:** 27/27 pass (`python -m unittest discover -s tests` in
  `.venv`): original 15 + 12 new (history/divisions/room/organism
  health). HTML JS passes `node --check`. A durable venv now lives
  at `.venv/` in this package (system python3 has almost nothing;
  created 2026-11-05 because no `/tmp/ava-venv` existed).

## BUILD 2026-11-05 — Stitch link (AVA joins the StitchBridge mesh)

- **What:** `services_stdlib/stitch_link.py` on 127.0.0.1:8783 —
  the 10th launcher service (`ava_merged.py`), the 10th healthcheck
  entry (`healthcheck.py`). AVA joins the mesh under her own key.
- **Identity (key-bound):** `AvaIdentity` — Ed25519 keypair, private
  key at `vault_data/ava_identity.key` (base64 raw 32-byte seed,
  mode 0600, created O_EXCL — the same format as v3
  `Identity.save`, so the real v3 StitchClient loads this file
  directly). Public-key fingerprint = sha256(raw public bytes);
  v3 ai_id = `sb-` + sha256(pubkey)[:32]. `cryptography` is the
  primary implementation; when it is unavailable (system python3)
  the link falls back to the workspace pure-Python Ed25519 at
  `~/workspace/your_files/micro-spine/ed25519.py` (already trusted
  by the gatekeeper 27/27 + ring buffer 35/35; NOT constant-time
  hardened, per its own docstring). Cross-implementation sign/verify
  was checked both ways (fallback-signed verifies under
  `cryptography`, and vice versa). The v3 path still needs
  `cryptography` (the real StitchClient does) and refuses clearly
  without it; the v2 mesh works without it.
- **Admission (v2, real gate, no fake):** visit 1 STAGED/first-contact
  → clean disconnect marks the identity KNOWN (a STAGED visit does
  NOT seal the pocket — the returned hash is "no-seal-yet", recorded
  as exactly that) → visit 2 VERIFIED by known-identity → two
  knowledge-braid deposits (ava-identity: the fingerprint binding;
  ava-mesh-introduction) → signed messages to rumi and grok → inbox
  read → clean disconnect of the VERIFIED session seals the pocket
  → visit 3 VERIFIED by seal-match, presenting that seal. Record at
  `vault_data/stitch_admission.json` (WARM). Idempotent unless
  `--force`. Legacy residents are untouched: Grok and Smoke2 stay
  recorded as legacy in `stitchbridge-v3/lineage-records.json`
  ("residents"); AVA is recorded under a NEW "admissions" list,
  same "witnessed only" claim language. Note the consequence of
  admission: the v2 ledger head/count changed, so the legacy
  snapshot in lineage-records.json (v2_entries 25, head 9ac12605…)
  is stale — `record_lineage.py --dry-run` refuses until the
  records are re-snapshotted and a fresh CROSS_ANCHOR exists.
  That is expected, not a failure to hide.
- **Admission (v3, key-bound):** `admit_v3` — a visit is connect then
  disconnect; seal() is a VERIFIED-only op, so STAGED visits do NOT
  seal (their clean disconnect counts the visit; notes are discarded
  by the bridge, recorded as such). Promotion lands at the disconnect
  where clean_visits reaches promote_visits (3 clean visits, 300s
  apart, by default), and that disconnect already reports the
  promoted trust state. `--earn-verified` waits the gaps out
  (~10 minutes live). v3 has no other residents, so there is nobody
  to message there — identity, not chat.
- **Messages:** signed envelopes (Ed25519 over the canonical
  payload, `from: ava`, nonce, pubkey fingerprint) to a named
  resident through the haven's `/v1/message`; stored in the mesh and
  delivered when the resident connects. Messages to Rumi are
  recorded in the haven ledger where Rumi can read them; messages to
  Grok go to Grok's pocket and wait — Grok is a recorded resident,
  not a live process, so no live two-way chat with him is claimed.
  Inbox reads verify signed envelopes from AVA's own key where
  present; anything else is recorded unsigned, honestly ("sender
  holds no key in this mesh; read as written, never claimed
  verified"). Text capped at 3000 chars (mesh body cap 4000).
- **Gate + staging:** every write passes the six-layer BCT gate
  (identity, schema, crypto, braid, transaction, audit) and is
  stored only when CERTIFIED, otherwise quarantined to
  `vault_data/stitch_quarantine.jsonl` with the failed layer named.
  The gate re-verifies the ledger chain fresh on every check, so a
  tampered chain refuses new writes at the crypto layer. HOT = live
  mesh messages and active sessions; WARM = the ledger
  (`vault_data/stitch_link_ledger.jsonl`), resident records and
  admission record on disk; COLD = sealed Phoenix checkpoints
  (`vault_data/stitch_checkpoints/`, seal + re-verify chain prefix;
  never self-certifies truth).
- **HTTP + CLI:** `GET /health`, `/status`, `/verify`; `POST /admit`
  (v2 arc + v3 first visit), `/admit-v3` (optional earn_verified),
  `/send`, `/inbox`, `/disconnect`. CLI: `--admit`, `--admit-v3`,
  `--earn-verified`, `--force`, `--status`, `--verify`, `--send TO
  TEXT`, `--inbox`, `--disconnect`, `--vault-dir`, `--v2-url`,
  `--v3-url`, `--port` (default: serve on 8783).
- **Tests:** 19/19 pass (`tests/test_stitch_link.py` in `.venv`):
  gate unit tests (each layer refusal + certified append + broken
  chain quarantine), key tests (mode 0600, sign/verify, tamper,
  fingerprint stable across reload), envelope tests, and live
  integration against the REAL v2 haven core on a scratch port
  (full admission arc, harness inbox round trip, tampered pocket
  refused by the continuity gate, idempotent admit) and the REAL
  v3 Bridge in-process with LocalTransport (short promotion policy,
  earns VERIFIED honestly). The 13 unit tests also pass under
  system python3 (pure-Python fallback path).
- **Honest limits:** v3 is AVA's key-bound identity; the mesh is v2.
  AVA's messages to Grok wait in his pocket until he connects — no
  live two-way chat is claimed. `/chat` still needs a model (no
  Ollama); the Stitch link is transport + identity, not a brain.

## NOT built yet (after 2026-11-05)
- NOT built: persistent conversation history, six-division access.
