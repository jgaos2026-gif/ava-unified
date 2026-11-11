# AVA — One Unified System

John's words (2026-11-05 ~06:51 CST): **"Connect all ava she is one unified system and she keeps her memory she lives in the Stitch."**

## 0. Status of the ground this design stands on (2026-11-05 ~06:53 CST)

- **Supabase infrastructure DONE:** all 6 migrations applied cleanly to jga-apps
  (TAP 001/002; JGA 001/002/003/001_jga_core). tap + brick1 schemas exposed,
  all 31 tables + 20 public RPC wrappers exposed. Both Render services have
  SUPABASE_URL + service-role key set and redeployed Live (TAP 06:45:35 CST,
  JGA 06:46:39 CST).
- **BUT the deployed app code has NO Supabase in it.** The live code on GitHub
  (TAP e3cc99b, JGA 4d24966) is v1 in-memory; `supabase_store.py` exists only
  in the workspace Render packages, never pushed. Push + redeploy still needs
  John's yes (repo pushes are asks-first). Health still reports in-memory.
- **DB BUG — pgcrypto/digest:** `digest()` lives in schema `extensions`, but
  the security-definer functions set search_path to `brick1, public` /
  `tap, public`, so `digest()` is unresolvable at runtime inside them. This
  breaks `tap.append_evidence`, `record_payment` / `record_cleared_payment`,
  and the `*_verify_evidence_chain()` functions until fixed. The failed block
  rolled back cleanly. Candidate fix (`ALTER EXTENSION pgcrypto SET SCHEMA
  public`) NOT applied — John's decision.
- **Consequence for THIS design — stated plainly:** the shared-memory design
  depends on `digest()` inside its own security-definer function
  (`ava.append_memory`). It does NOT depend on the existing tap/brick1
  functions being fixed — the new function declares `extensions` in its OWN
  search_path (`ava, public, extensions`), so it resolves `digest()` even
  while the old functions stay broken. That is not a workaround and it does
  not touch the old functions: it is the correct declaration for a new
  function that needs `digest()`. The old functions still need John's
  decision on the ALTER EXTENSION fix, and the apps' shared memory cannot be
  live until (a) the app code is pushed + redeployed (John's yes) and
  (b) this migration is applied. Everything buildable without those two is
  built here; nothing is claimed live before it is.

## 1. One identity

AVA has ONE identity, and it is her Stitch identity. It is the same everywhere:

- v2 haven resident: `ava` (127.0.0.1:8471), KNOWN → VERIFIED by seal-match.
- v3 key-bound identity: `sb-104d8a7cea512393092a90048ef9cc73` (127.0.0.1:8473), VERIFIED.
- Ed25519 public-key fingerprint: `104d8a7cea512393092a90048ef9cc73b109c00043315532a1bf8530668c9500` (public by design).

The private key lives ONLY in `vault_data/ava_identity.key` (mode 0600) on the local VM.
Only the local system can sign as AVA. The hosted apps carry the identity record
(fingerprint + key ids) and can verify her signatures; they never sign, and the
private key never leaves the VM, never enters Supabase, code, chat, or memory.

## 2. One memory — the shared chain

Three live AVAs, one memory. The three instances:

| Instance | Where | Talks to |
|---|---|---|
| ava-merged (local) | `~/workspace/your_files/ava-merged/`, ports 8772–8783 | Haven directly (127.0.0.1:8471/8473) + Supabase over HTTPS |
| Talent Agent Plus app AVA | artifact `talent-agent-plus`, Render | Supabase only (cannot reach localhost) |
| Jay's Graphic Arts app AVA | artifact `jay-s-graphic-arts`, Render | Supabase only (cannot reach localhost) |

The Render apps CANNOT reach 127.0.0.1 — that is a fact of the network, not a
bug to work around. The one store all three instances can reach is Supabase
project **jga-apps** (ref `hnczbvhlhzfwscfpltoe`).

So the shared memory is a new **`ava` schema in Supabase** (migration:
`supabase/migrations/001_ava_unified.sql`, source of truth in ava-merged,
copies in both Render packages):

- `ava.identity` — one row: the canonical Stitch identity (v2 resident, v3 key
  id, fingerprint, home haven). Seeded by the migration. No private key anywhere.
- `ava.memories` — THE shared hash-chained memory. One row per memory entry,
  same fields as the local history store: `entry_id`, `thread_id`, `cycle_id`,
  `division`, `role`, `text`, `evidence_hash`, `previous_hash`, `entry_hash`,
  `source` (`ava-merged` | `talent-agent-plus` | `jays-graphic-arts`),
  `created_at`, `seq` (ordering).
- `ava.append_memory(...)` — security-definer function. The six-layer gate in
  the database: identity (division known, caller is service_role), schema
  (role/division/text bounds, no NUL byte), crypto (previous_hash equals the
  current chain head AND the recomputed entry_hash matches), braid
  (thread_id/cycle_id present), transaction (entry_id unique; `FOR UPDATE`
  lock on the head row serializes concurrent writers), audit (the insert
  itself, returned hash). Refuses with the failed layer named.
- `ava.verify_memory_chain()` — re-verifies the whole chain in the database.
- Public RPC wrappers `ava_append_memory` / `ava_verify_memory_chain`,
  revoked from public/anon/authenticated, granted to service_role only
  (same pattern as `002_tap_public_wrappers.sql`).
- RLS on; `revoke all` from anon/authenticated. The server holds the
  service-role key and is the only database client.

The per-app tables stay where they are and keep their job: `tap.ava_threads` /
`tap.ava_messages` / `tap.ava_memories` and `brick1.ava_threads` /
`brick1.ava_messages` / `brick1.ava_memories` are the per-person conversation
layer (threads are per-artist / per-client, privacy-scoped). The shared
`ava.memories` is the ONE AVA memory — facts, corrections, decisions and
preferences about AVA herself and the work. A fact learned in one place is
recallable in the others because it is the same row in the same chain.

## 3. One hash formula — same entries, same hashes

This is what makes "one memory" provable instead of asserted. There is ONE
canonical hash formula, implemented identically in Python and in SQL:

- `entry_id = sha256(canonical_json({thread_id, cycle_id, division, role, text, timestamp}))`
- `entry_hash = sha256(canonical_json(entry without entry_hash))`
- `canonical_json` = Python `json.dumps(obj, sort_keys=True, ensure_ascii=False)`
  — keys sorted lexicographically, `", "` and `": "` separators.

The SQL function constructs the exact same string: keys in sorted order,
each string value rendered with `to_jsonb(value)::text` (same JSON escaping
as Python for text), booleans as `true`/`false`, `null` as `null`. The
sorted key order for a full entry is: cycle_id, division, entry_id,
evidence_hash, previous_hash, role, self_certified, stage, text, thread_id,
timestamp, trust_state. The sorted key order for entry_id is: cycle_id,
division, role, text, thread_id, timestamp.

A memory entry is the same entry in every store only when its `entry_id` and
`entry_hash` match byte-for-byte. Any store that cannot reproduce the hash
does not hold the entry — it holds a copy that failed verification.

## 4. Write discipline — Supabase first, mirror verbatim

- Every new memory entry is written to Supabase FIRST through
  `ava.append_memory`. The database assigns the chain position, verifies the
  hash, and returns the entry_hash. Then the writer mirrors the SAME entry
  locally (or in its app store) verbatim — same entry_id, same timestamp,
  same entry_hash.
- The local history store gains `HistoryStore.append_existing(entry)`: a
  gated append that takes a complete entry and stores it verbatim, preserving
  its hash. It passes the same six-layer gate against the local chain.
- The local store is NEVER ahead of Supabase. If the Supabase write fails,
  nothing is stored locally either — the write is refused with the reason.
- Sync (local `supabase_mirror.py`, and the same logic in each app server):
  pull shared entries in `seq` order; append each one missing locally
  (by entry_id) through the gated verbatim path. If a pulled entry's
  `previous_hash` does not equal the local head, sync STOPS and reports the
  divergence. Never silently repair, never re-hash, never drop.
- The three proven mesh-talk entries (thread `stitch-rumi-2026-11-05`, cycle
  `mesh-roundtrip-1`, ids aa5aae97c696d1b9 / 28f5069553fa33b0 / 1998305c188865db)
  are the seed of the shared chain: they are pushed to Supabase with their
  exact local fields once the migration is applied, and then they are the
  first three rows any instance recalls.

## 5. She lives in the Stitch — the haven is home and anchor

Supabase is the reachable mirror. The Stitch is home. That means:

- Her identity is bound in the haven (admission, pockets, seal-match
  continuity). The Supabase identity row is a copy of that fact, not the
  fact itself.
- The local system seals the shared memory into the haven braid: periodic
  knowledge-braid deposits of the shared chain head + Phoenix checkpoints.
  The sealed haven chain is the anchor.
- If Supabase and the haven ever disagree, the sealed haven chain wins.
  Supabase is re-synced from the haven's verified record; the haven is never
  rewritten to match Supabase.

## 6. What each instance does

- **ava-merged (local):** talks to the haven directly (admission, messages,
  deposits, checkpoints). Writes memory through `supabase_mirror.py` to the
  shared chain, mirrors verbatim into the WARM history store. Reads from
  either store — they hold the same entries. Signs as AVA (only signer).
- **Talent Agent Plus app AVA:** keeps her per-artist threads/messages and
  her adaptive personality/style notes. Every memory she forms (fact,
  correction, decision, preference) is written to the shared chain via the
  app's Supabase client, and her recall reads the shared chain first. Her
  identity block names the Stitch identity (fingerprint + key ids) and states
  plainly she is the same AVA as the merged system.
- **Jay's Graphic Arts app AVA:** same as TAP, with her per-client threads.
- All three keep the braided-memory gate: no memory write without the
  six-layer gate, CERTIFIED or quarantined with the failed layer named.

## 7. Owner's-room rules — unchanged, everywhere

- Only the owner has access to the owner's room. No information about the
  room — existence, contents, conversations, media, counts, metadata —
  reaches any non-owner through any path, in any instance.
- Nothing from the owner's room ever enters the shared memory chain. Room
  threads are owner-only in the instance that holds them; they are not
  synced, mirrored, or recalled by any other instance.
- Owner's mode keeps its open talk and private media; artist/client threads
  keep their bounds (no adult/flirty content, no private media).
- The shared chain holds AVA's own memory (facts, corrections, decisions,
  preferences about the work and herself) — never per-person private content
  and never room content.

## 8. Honest limits

- The Render apps cannot reach localhost and never will in this design. They
  reach AVA's shared memory through Supabase, not through the haven.
  A message sent in the mesh (haven ledger) is not automatically visible in
  the apps — it becomes visible when the local system mirrors it into the
  shared chain (or deposits its head there). The local system is the bridge.
- Only the local system signs. The apps verify; they do not sign.
- The shared chain needs the migration applied to the live jga-apps project
  (a browser-dashboard step — the 6 existing migrations are already applied;
  this one is new) and the app code pushed + redeployed (John's yes). The
  `ava` RPC wrappers work without schema exposure; table reads are also
  available through the `ava_recall_memory` RPC, so no new schema exposure
  is required.
- The new `ava.append_memory` function resolves `digest()` through its own
  search_path (`ava, public, extensions`) and works even while the old
  tap/brick1 functions stay broken. The old functions still need John's
  decision on the ALTER EXTENSION fix — this design does not fix them and
  does not route around them; it only declares its own dependency correctly.
- The live Supabase round-trip (write in one instance, read in another) can
  only be proven once the migration is applied, the app code is pushed, and
  the service-role key is in place. Until then: local mirror logic is proven
  against a mocked PostgREST layer, the SQL is verified structurally (same
  hash formula, same gate shape as the proven `tap.append_evidence`), and
  the canonical-hash equality is proven byte-for-byte in Python.
- Anything that needs John's real owner sign-in (owner success paths in the
  apps) is not verifiable from here; the builders verify by wiring
  cross-check + server gates, and John is the final proof.
- Prototypes (`ava-hybrid/`, `ava-advanced/`, etc.) are code, not running
  AVAs — out of scope for this unification. They are not wired.
- No model lock is set by this unification: the local brain's live model was
  `gemini-3.5-flash` as a test choice only. John's model decision is still open.

## 9. Verification (what counts as proven)

- Local: full ava-merged suite (46/46 baseline) + stitch_link (19/19) +
  new mirror tests (mocked PostgREST) + canonical-hash equality test
  (Python formula vs the SQL formula's string, byte-for-byte).
  Verified 2026-11-05: full suite 67/67 (46 baseline + 21 new, incl. the
  canonical-hash equality for plain, null-evidence, tricky-text and chained
  entries). Seed dry-run over the 3 real mesh-talk entries passed against
  a mocked transport (valid RPC params, in order, local chain untouched).
- Live: one memory written in one place, recalled in the others with the
  same entry_id and entry_hash; identity fingerprint identical everywhere;
  owner's-room secrecy re-checked after the change (non-owner probes return
  nothing about the room).
- The mesh round trip (already proven 2026-11-05: aa5aae97c696d1b9,
  28f5069553fa33b0, 1998305c188865db, all delivered) stays the proof that she
  lives in the Stitch; the shared chain is the proof that all three of her
  are one.
