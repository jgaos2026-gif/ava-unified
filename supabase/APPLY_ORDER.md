# Talent Agent Plus — Supabase apply order (project "jga-apps")

Project: https://hnczbvhlhzfwscfpltoe.supabase.co (ref `hnczbvhlhzfwscfpltoe`,
FREE, West US / Oregon). Apply in the Supabase Dashboard → SQL editor,
in this exact order. No secrets live in any of these files.

## 1. `supabase/migrations/001_tap_core.sql`
The `tap` schema: artists, trials (one-time-ever), bookings + state machine,
design_orders, payments (idempotent on the Stripe object id), allocations
(11VT split, V7 residual), ava_threads/messages/memories (hash-linked),
referrals, social_accounts (provider + external id only, no tokens),
addon_purchases, ledger_events (hash-chained). RLS on; revoke-all from
anon/authenticated — the Python server (service-role key) is the only
database client.

## 2. `supabase/migrations/002_tap_public_wrappers.sql`
Public RPC wrappers for the tap security-definer functions
(`tap_claim_trial`, `tap_record_cleared_payment`, `tap_transition_booking`,
`tap_append_evidence`) plus `tap_verify_evidence_chain()`. PostgREST serves
the `public` schema by default, so the server calls these wrappers; each is
revoked from public/anon/authenticated and granted to service_role only.

## 2b. `supabase/migrations/003_trial_expiry_and_design_jga.sql`
Trial expiry + effective tier + Design · JGA audit columns. `tap.trials`
gains `expires_at` (claimed_at + 7 days); `tap.effective_tier()` returns
`'full_label'` while a trial is live, else the stored tier (public wrapper
`tap_effective_tier`, service_role only); `tap.design_orders` gains
`base_price_cents`, `discount_pct`, `promo_code`, `effective_tier`, and
`upload_ref` so a locked Design · JGA price can be audited later.

## 3. Expose the `tap` schema (Dashboard → Settings → API → Exposed schemas)
Add `tap` next to `public`. Needed only for direct table reads
(`artist_by_email`); the RPC wrappers work without it. If this step is
skipped, table reads fail and the adapter reports it plainly — the server
still runs in-memory.

## 4. Render env vars (Dashboard → the `talent-agent-plus` service)
Set these two (values from Supabase Dashboard → Settings → API; never in
chat, never in the repo):
- `SUPABASE_URL` = the project URL above
- `SUPABASE_SERVICE_ROLE_KEY` = the service_role key (NOT the anon key)

Then redeploy. The server pings Supabase once at startup: if it answers,
`/api/health` reports `"store": "supabase"`; if not, it reports
`"store": "in-memory"` and runs exactly as before. Verify with:
- `GET /api/health` → `"store": "supabase"`, `"supabase_configured": true`
- `GET /api/store/verify` (owner token) → `"evidence_chain_valid": true`
  (empty ledger verifies as true — the chain check passes on zero entries)

## Known rounding difference (do not silently "fix" — John's call)
The database 11VT split (`tap.split_11vt`) floors the ten fixed buckets and
gives V7 the remainder. The Python engine rounds half-up (with a round-down
fallback), V7 as plug. Both sum exactly to the cleared amount, but the
per-bucket distribution can differ by a cent on odd amounts. Reconcile the
rounding rule in the live-DB step; neither side was changed here.

## What is NOT wired yet (live-DB step, after the browser applies this)
- The runtime engine (artists/bookings/receipts) still lives in memory in
  v1; the adapter is the durable-store client for trials, cleared payments,
  booking transitions, and evidence. A full engine-to-Postgres migration is
  verified against the live database, not claimed here.
- Engine artists now carry an email (optional, lowercased) so a trial
  claim can bind to an artist in the engine; the tap schema still keys
  artists by email. Trial claims resolve the tap artist by email. A full
  artist sync (engine id ↔ tap uuid) is part of that live-DB step.
- Design · JGA orders live in the engine in v1 (see design_jga.py); the
  tap.design_orders columns from migration 003 are ready for the
  live-DB step. Cleared design payments already reconcile through
  tap_record_cleared_payment with a design_order_id.
- In Supabase mode the trial claim lives in the database (tap.trials)
  and the database-side effective tier is tap.effective_tier(); the
  engine-side effective tier (the /api/artists/<id>/effective-tier
  route) reads the engine's claim. The two agree once the engine id ↔
  tap uuid artist sync lands — that sync is the live-DB step, not
  claimed here.

## AVA unified memory — 001_ava_unified.sql (2026-11-05, John's unification order)
Apply AFTER 001/002, in the same project. Creates the shared `ava` schema:
`ava.identity` (one row: AVA's Stitch identity — no private key), `ava.memories`
(the ONE shared hash-chained memory), `ava.append_memory` (six-layer gate),
`ava.verify_memory_chain`, `ava.recall_memory`, `ava.get_identity`, plus the
four public RPC wrappers (`ava_append_memory`, `ava_verify_memory_chain`,
`ava_recall_memory`, `ava_get_identity`, service_role only). Idempotent —
re-running is a no-op, and applying it from both Render packages is safe.
pgcrypto NOTE: the new functions declare `extensions` in their own
search_path, so digest() resolves even while the old tap/brick1 functions
stay broken (that fix is John's decision). No new schema exposure needed:
recall/identity go through RPCs. Seed after applying: push the three proven
mesh-talk entries (thread stitch-rumi-2026-11-05, cycle mesh-roundtrip-1)
via the local mirror script (ava-merged/supabase_mirror.py seed) or the app
server; they become the first three rows of the shared chain.

## AVA unified memory — 002_append_memory_chain_check.sql (2026-11-10)
Replaces `ava.append_memory` (CREATE OR REPLACE). The 001 version checked
only that the new entry's previous hash matched the current head; 002
verifies the whole existing chain first (via `ava.verify_memory_chain`
from 001) and refuses the write if the chain does not verify — appending
onto a broken chain would certify new entries on top of corruption.
Apply after 001, in the Dashboard SQL editor. NOT yet applied to the live
project — apply + verify with `ava_verify_memory_chain` after. (The local
HistoryStore got the same rule in code the same day: re-verify fresh
before every write, check the post-write re-verification before reporting
success.)
