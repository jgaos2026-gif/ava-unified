# AVA Sovereign — Media Features Design
## File upload + storage · Pic upload + memory · Pic + video creation (personal use)
**Ordered by John 2026-11-09 ~04:33 CST:** "Add file upload and storage, pic upload and memory, pic and video creation, any kind, personal use — to AVA."
**Home:** AVA Sovereign only (artifact slug `ava-sovereign`, goal `goal_54b9853daf82`). NOT the TAP / JGA app AVAs.
**Status:** DESIGN + SCOPING ONLY. No artifact edits made here. Parent executes via `artifact.edit`.

---

## 1. Current state as read (2026-11-09)

### AVA Sovereign artifact (v6 live, no build running, not shared)
- 50+ actions. Relevant existing ones:
  - Memory (local braid, six-layer gate in the artifact server): `addmemory` (gate report returned; uncertified candidates quarantined with failed layer named), `listmemory`, `recallmemory`, `verifymemory`, `replaymemory`, `phoenixrecover`, `listquarantine`, `deletequarantine`.
  - Studio (already owner-only, private server-side): `generateart` (renders **stylized** artwork — local render, NOT a Gemini call; "Artwork only — never photorealistic photos or real footage of real people"), `createavatar`, `listmedia`, `deletemedia`.
  - Gemini key (hybrid rule, John's 2026-11-09 ~02:28 ruling): `savegeminikey` (live-validated via models-list check before reporting connected; rejected key NOT saved; never shown back or logged; sent only to `generativelanguage.googleapis.com` in the `x-goog-api-key` header), `testgemini`, `removegeminikey`, `getsettings` (connection state + model; key never returned).
  - No upload actions exist. No file/pic upload, no pic/video generation via Gemini.
- **Real-key acceptance still UNPROVEN.** The key flow was verified for rejection handling, but no real key has been accepted yet. Pic/video generation cannot be tested until John's key is pasted in Settings and accepted.

### ava-merged Python system (`~/workspace/your_files/ava-merged/`)
- `llm_connector.py` (158 lines): Gemini via `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`, `x-goog-api-key` header, key from env `AVA_LLM_API_KEY` only, propose-only, tool markers deferred. This is the exact shape the image path reuses (same host, same header, different model + image modalities).
- `services/private_vault.py`: local SQLite/file storage under `VAULT_DATA_DIR`. `services/embedding_braid.py`: in-memory only. No binary/media store in ava-merged.
- `supabase/migrations/001_ava_unified.sql`: `ava` schema — `ava.identity` (row 1, `ava` / `sb-104d8a7c…`), `ava.memories` (hash-chained), `ava.append_memory(...)` (six-layer BCT gate in the DB), `ava.verify_memory_chain()`, `ava.recall_memory(...)`.
- **Owner's-room rule (in the migration header, binding):** "nothing from the owner's room ever enters this chain. Room threads are owner-only in the instance that holds them; they are not synced, mirrored, or recalled by any other instance. This chain holds AVA's own memory — never per-person private content and never room content."

### Storage — what exists
- **No Supabase Storage bucket exists in jga-apps.** Grep of the whole workspace finds no `storage.buckets` creation, no `supabase.storage` use anywhere. The "storage" hits in the TAP/JGA Render packages are browser `localStorage` (auth tokens) and comments about platform secure storage for keys — not file storage.
- The Sovereign artifact's server store already holds Studio artwork + avatars (`listmedia`/`deletemedia`), so it holds image data. **Whether it holds arbitrary files (PDF/zip/audio) and at what size is UNVERIFIED from here** — the builder must probe at build time.
- Supabase free tier includes 1 GB Storage. Creating a bucket is a Dashboard/SQL step — optional fallback only, needs John's yes.

### Generation — what the owner's Gemini key can actually reach (verified against Google's official docs, crawled 2026-11-09)
- **Images — YES, same key, same host.** Nano Banana family via the Interactions API: `POST https://generativelanguage.googleapis.com/v1beta/interactions`, header `x-goog-api-key: <key>`, body `{"model": "gemini-nano-banana-2.1", "input": [...]}`. Output image is base64. Current models (official docs):
  - `gemini-nano-banana-2.1` — primary workhorse, 1K/2K/4K. **Use this.**
  - `gemini-3.1-flash-lite-image` (Nano Banana 2 Lite) — cheapest/fastest.
  - `gemini-3.1-flash-image` (Nano Banana 2), `gemini-3-pro-image` (Nano Banana Pro).
  - `gemini-2.5-flash-image` — legacy.
  - The older per-model `generateContent` endpoint with `responseModalities: ["TEXT","IMAGE"]` also works for these models (multiple independent sources). Image editing works too: input image(s) as base64 + text instruction, up to 3 reference images.
  - All generated images carry a **SynthID watermark** (Google).
  - Cost: a few cents per image, billed to the Google Cloud project attached to the key. Image calls are billed API usage, not free-tier.
- **Video — YES, but only with billing enabled, and NOT Veo 3.1.** Official docs (ai.google.dev/gemini-api/docs/video, crawled 2026-11-09):
  - **Veo 3.1 Preview in the Gemini API was SHUT DOWN October 22, 2026.** Any design naming Veo 3.1 is stale — do not build it.
  - Current model: **Gemini Omni Flash `gemini-omni-1.2-flash`** — text/image/video → video up to **15 seconds** with native audio, up to 6 reference images, multi-turn conversational editing, 16:9 or 9:16. `gemini-omni-1.1-flash` auto-routes to 1.2 effective **December 3, 2026**.
  - Same Interactions API: `POST /v1beta/interactions`, same key. REST returns base64 video in the `steps[]` array (`output_video` is SDK-only). Long-running — the UI needs progress/polling, not a blocking wait.
  - **Video generation is paid on every official route; there is no free tier.** It requires billing enabled on the Google Cloud project behind the key. Published token math puts it at ~$0.10/sec at 720p (8s ≈ $0.73, 15s ≈ $1.50) — verify exact 1.2 rates on Google's pricing page at build time.
- **Sora is closed** (OpenAI shut Sora 2 / Sora Videos API Sept 24, 2026) — not a fallback.

---

## 2. The honest limit on "any kind"

"Any kind, personal use" is bounded in two places, and neither is negotiable in this build:

1. **John's own rule (2026-11-05, standing):** private picture/video production happens ONLY in owner's mode. The Sovereign app is passcode-gated and owner-only by construction; the new tabs/actions live inside it. The owner's-room secrecy rule applies: nothing about the room — existence, contents, media, counts, metadata — is ever shown to any non-owner through any path. The new features must not leak media into any shared surface (no Discover, no public reads, no shared-chain writes — see §3b).
2. **Google's Generative AI Prohibited Use Policy** (linked from the official image docs): no sexually explicit content, no non-consensual intimate imagery, no deceptive/harassing/harmful content, nothing involving minors, no photorealistic images of real people. The app's existing Studio rule already says "no photorealistic people, no real footage."
3. **So "any kind" in practice =** any subject, style, or scene the owner wants *within Google's safety rules*: stylized/fictional people, art, landscapes, design work, fantasy, animation-style video, image-to-video from his own pics, etc. — but NOT pornographic/explicit imagery, NOT realistic images/video of real identifiable people, NOT deceptive deepfakes. Refusals must surface plainly ("Google refused this prompt") — never silently substituted with something else.
4. **If John wants truly unfiltered generation,** the only path is a local model on his own hardware (e.g. his Pavilion) — not through the Gemini key, not in this build. That is a separate decision (hardware, model, install) and needs his explicit say.

---

## 3. Design — the three features

### (a) File upload and storage — NO KEY NEEDED, builds first
- New actions: `uploadfile` (accept file → store bytes as base64 + metadata: name, mime, size, sha256, uploaded_at), `listfiles`, `downloadfile` (returns base64 for the browser to save), `deletefile`.
- New **Files** tab (owner-only, inside passcode gate). List shows name / type / size / date / hash; download + delete per row.
- Caps (build-time verification items): images ≤ 10 MB, other files ≤ 25 MB per file. If the artifact store rejects a size, the build reports the real cap instead of guessing.
- Every stored file gets a SHA-256 hash recorded with it — that hash is what memory entries reference (never the raw bytes in the braid).

### (b) Pic upload and memory — the braid part
- New actions: `uploadpic` (stores the pic + **auto-writes a braided memory entry through the existing six-layer gate**: text = owner's caption/description + file name + sha256 + storage id; the pic bytes stay in the app store, only the hash + pointer go in the braid), `listpics`, `getpic`, `deletepic` (deleting a pic also braids a correction entry noting the deletion — the chain never silently loses a link).
- New **Pics** tab. Upload from device/camera roll; optional caption at upload time (AVA can also describe the pic back to the owner with the local brain — no key needed — and the owner confirms or corrects the description before it is braided).
- **CRITICAL — where the memory goes:** the LOCAL Sovereign braid only (`addmemory` path). **Never the Supabase shared `ava` chain.** The migration's owner's-room rule forbids room content in the shared chain, and the Sovereign app's shared-chain sync is NOT CONNECTED by design. Pic memory is recallable in Sovereign (`recallmemory` returns the entry; the UI shows the linked pic). It is not visible to TAP/JGA AVAs, not synced, not mirrored.
- Gate failures quarantine the memory candidate with the failed layer named (existing behavior) — the pic itself stays stored; only the memory write is quarantined, and the owner can retry/dismiss.

### (c) Pic and video creation (personal use) — key-gated, pics first
- **Pic creation — lands first.** New action `generatepic`: prompt (+ optional reference image(s) chosen from his uploads, up to 3) → `POST /v1beta/interactions` with model `gemini-nano-banana-2.1`, header `x-goog-api-key` (the saved owner key, same handling as the text path: never shown back, never logged) → base64 image back → stored as Studio media + braided memory entry (prompt + model + hash). SynthID watermark noted in the UI. Refusals surface Google's refusal plainly.
  - Settings needs two new fields (the current `getsettings` has one model): `imageModel` (default `gemini-nano-banana-2.1`) and `videoModel` (default `gemini-omni-1.2-flash`). Text model stays as-is.
  - Existing `generateart` (stylized, no key) stays as-is — the new Gemini pic creation is a separate action, so the no-key experience doesn't break.
- **Video creation — gated, second.** New action `generatevideo`: text-to-video, or image-to-video from an uploaded/generated pic (up to 6 reference images supported by the model; start with 1) → `POST /v1beta/interactions` with model `gemini-omni-1.2-flash`, `response_format` aspect 16:9 or 9:16, 3–15s → async: poll the interaction until complete (UI shows progress; no blocking wait) → base64 mp4 back → stored + memory entry. **Cost shown before each render** (est. seconds × ~$0.10) and the run only starts after the owner confirms.
  - **Hard gate:** video stays OFF until (i) John confirms billing is enabled on the Google Cloud project behind his key, and (ii) the builder's probe (one 3-second render) succeeds. No charges happen without his say.

---

## 4. Build order (for the parent's artifact edits)

**Phase 0 — probes first (builder does these before promising anything):**
1. Store round-trip probe: upload a small test image + a test file in scratch, confirm list/download/delete work; record the real size caps.
2. Image probe: one `gemini-nano-banana-2.1` call with the saved key (needs John's key pasted + accepted first); report success/failure + actual cost. If no key is saved, pic creation cannot be tested — say so.
3. Video probe: only after John confirms billing; one 3-second Omni render; report success/failure + actual cost.

**Phase 1 — Files:** `uploadfile` / `listfiles` / `downloadfile` / `deletefile` + Files tab + SHA-256 per file.
**Phase 2 — Pics + memory:** `uploadpic` / `listpics` / `getpic` / `deletepic` + Pics tab + auto-braid via the six-layer gate (local braid only) + caption confirm flow.
**Phase 3 — Pic creation:** `generatepic` (Nano Banana 2.1) + `imageModel` setting + Studio tab extension + refusal surfacing + SynthID note.
**Phase 4 — Video creation (gated):** `generatevideo` (Omni 1.2 Flash) + `videoModel` setting + progress/polling UI + pre-render cost confirmation.
**Phase 5 — ava-merged Python parity (after Sovereign lands, optional):** `generate_image()` + `generate_video()` siblings to `propose()` in `~/workspace/your_files/ava-merged/llm_connector.py` (same host/header; models from env `AVA_LLM_IMAGE_MODEL` / `AVA_LLM_VIDEO_MODEL`); file storage under `vault_data` (private_vault); memory write via the local history-store gate — NOT the shared Supabase chain for room content. Keeps the VM AVA able to do the same in owner's mode.
**Phase 6 — Knowledge-pack patch:** revise pack lines ~27 (Gemini-only-for list), ~215, ~430 (Studio media row), ~439 (Gemini row) to record real Gemini image/video generation, the video billing gate, the SynthID watermark, and the restated "any kind" boundary. Fold into / after the still-unapplied triple-check patch-1 — do not conflict with it.

---

## 5. What still needs John

1. **His Gemini key pasted in Settings** (real-key acceptance still unproven — the flow rejects bad keys correctly, but no real key has been accepted yet). Nothing generative can be tested without it.
2. **Billing enabled on the Google Cloud project behind that key** — required for ANY video generation, and to confirm image generation isn't blocked. No charges without his say; video stays off until he confirms.
3. **Decision (only if the probe requires it):** artifact-store-only storage vs. creating a Supabase Storage bucket (free tier, 1 GB) as the fallback for large files. Only needed if Phase 0 probe 1 shows the artifact store can't hold them.
4. **The "any kind" boundary** (Google's rules block explicit / real-person content). If he wants truly unfiltered generation, that's a local-model path on his own hardware — a separate decision, not this build.

## 6. Unverified / to verify at build time
- Artifact-store size caps for arbitrary files (probe 1).
- Whether John's saved key can actually generate images (probe 2) — the models-list check does not prove this.
- Exact Gemini Omni 1.2 Flash rates on Google's pricing page (probe 3; estimate ~$0.10/sec from published token math).
- Whether the Interactions API or the older per-model `generateContent` endpoint is the better call path inside the artifact runtime (both are documented; builder picks by what the runtime supports and reports the choice).
