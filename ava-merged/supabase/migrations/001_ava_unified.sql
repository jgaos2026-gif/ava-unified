-- ============================================================================
-- AVA unified memory — one shared hash-chained memory for all AVA instances
-- ============================================================================
-- John's words (2026-11-05): "Connect all ava she is one unified system
-- and she keeps her memory she lives in the Stitch."
--
-- What this file creates: a new `ava` schema in Supabase project jga-apps.
--   * ava.identity  — one row: AVA's canonical Stitch identity (v2 resident
--     `ava`, v3 key sb-104d8a7cea512393092a90048ef9cc73, Ed25519 fingerprint).
--     No private key anywhere in this file or schema. The private key lives
--     only in vault_data/ava_identity.key (0600) on the local VM.
--   * ava.memories — THE shared hash-chained memory. One row per memory
--     entry, same fields as the local history store
--     (services_stdlib/history_store.py). A fact learned in one place is
--     recallable in the others because it is the same row in the same chain.
--   * ava.append_memory(...) — security-definer function. The six-layer BCT
--     gate in the database. Refuses with the failed layer named.
--   * ava.verify_memory_chain() — re-verifies the whole chain in the DB.
--   * ava.recall_memory(...) / ava.get_identity() — read paths.
--   * public.ava_* wrappers — the RPCs the servers actually call
--     (service_role only, same lockdown as 002_tap_public_wrappers.sql).
--
-- Apply AFTER the existing migrations, in the same project. Idempotent:
-- re-running it is a no-op (create if not exists / create or replace /
-- ON CONFLICT DO NOTHING). Applying it from both Render packages is safe.
--
-- pgcrypto NOTE (read this): digest() lives in schema `extensions`. The
-- existing tap/brick1 security-definer functions set search_path to
-- `tap, public` / `brick1, public`, so digest() is unresolvable inside
-- them — that is the known 2026-11-05 bug, and fixing THOSE functions is
-- John's decision (candidate: ALTER EXTENSION pgcrypto SET SCHEMA public).
-- This file does NOT touch those functions. The NEW functions here declare
-- `extensions` in their OWN search_path (`ava, public, extensions`), so
-- they resolve digest() even while the old functions stay broken. That is
-- the correct declaration for a new function that needs digest(), not a
-- workaround for the old ones.
--
-- Hash formula (ONE formula, Python and SQL identical — see
-- AVA-UNIFIED-DESIGN.md section 3):
--   entry_id   = sha256(canonical_json({thread_id, cycle_id, division,
--               role, text, timestamp}))
--   entry_hash = sha256(canonical_json(entry without entry_hash))
--   canonical_json = Python json.dumps(obj, sort_keys=True,
--               ensure_ascii=False) — keys sorted lexicographically,
--               ", " and ": " separators.
-- The SQL helpers below construct the exact same string: keys in sorted
-- order, each string value rendered with to_jsonb(value)::text (same JSON
-- escaping as Python for text), booleans as true/false, null as null.
-- Sorted key order for a full entry: cycle_id, division, entry_id,
-- evidence_hash, previous_hash, role, self_certified, stage, text,
-- thread_id, timestamp, trust_state.
-- Sorted key order for entry_id: cycle_id, division, role, text,
-- thread_id, timestamp.
-- A memory entry is the same entry in every store only when its entry_id
-- and entry_hash match byte-for-byte.
--
-- Write discipline (enforced here + in the clients):
--   Supabase FIRST (this function assigns the chain position and verifies
--   the hash), then mirror verbatim locally / in the app store. The local
--   store is never ahead of Supabase. Sync pulls in seq order; a pulled
--   entry whose previous_hash does not equal the local head stops the sync
--   and is reported — never silently repaired.
--
-- Owner's-room rule: nothing from the owner's room ever enters this chain.
-- Room threads are owner-only in the instance that holds them; they are
-- not synced, mirrored, or recalled by any other instance. This chain
-- holds AVA's own memory (facts, corrections, decisions, preferences
-- about the work and herself) — never per-person private content and
-- never room content.
--
-- No secrets in this file.
-- ============================================================================

create schema if not exists ava;

-- -- identity ---------------------------------------------------------
create table if not exists ava.identity (
  id integer primary key default 1 check (id = 1),
  v2_resident text not null default 'ava',
  v3_key_id text not null default 'sb-104d8a7cea512393092a90048ef9cc73',
  fingerprint text not null default '104d8a7cea512393092a90048ef9cc73b109c00043315532a1bf8530668c9500',
  home_haven text not null default 'StitchBridge v2 127.0.0.1:8471 / v3 127.0.0.1:8473 (private, local-only)',
  created_at timestamptz not null default now()
);
insert into ava.identity (id) values (1) on conflict (id) do nothing;

-- -- shared memory ----------------------------------------------------
create table if not exists ava.memories (
  seq bigserial primary key,
  entry_id text not null unique,
  timestamp_text text not null,
  thread_id text not null,
  cycle_id text not null,
  division text not null check (division in ('EXECUTION','MEMORY','VERIFICATION','EVIDENCE','RECOVERY','GOVERNANCE')),
  role text not null check (role in ('user','ava','system')),
  text text not null check (length(text) between 1 and 100000),
  evidence_hash text,
  previous_hash text not null,
  entry_hash text not null,
  source text not null check (source in ('ava-merged','talent-agent-plus','jays-graphic-arts')),
  created_at timestamptz not null default now()
);
create index if not exists ava_memories_thread_idx on ava.memories (thread_id, seq);
create index if not exists ava_memories_division_idx on ava.memories (division, seq);

alter table ava.identity enable row level security;
alter table ava.memories enable row level security;
revoke all on table ava.identity, ava.memories from anon, authenticated;

-- -- canonical JSON helpers (ONE formula, shared by append + verify) --
-- Builds the exact string Python's json.dumps(obj, sort_keys=True,
-- ensure_ascii=False) produces for a full entry (without entry_hash).
create or replace function ava.canonical_entry_json(
  p_entry_id text,
  p_timestamp text,
  p_thread_id text,
  p_cycle_id text,
  p_division text,
  p_role text,
  p_text text,
  p_evidence_hash text,
  p_previous_hash text
) returns text
language sql
immutable
set search_path = ava, public, extensions
as $$
  select '{"cycle_id": ' || to_jsonb(p_cycle_id)::text
    || ', "division": ' || to_jsonb(p_division)::text
    || ', "entry_id": ' || to_jsonb(p_entry_id)::text
    || ', "evidence_hash": ' || coalesce(to_jsonb(p_evidence_hash)::text, 'null')
    || ', "previous_hash": ' || to_jsonb(p_previous_hash)::text
    || ', "role": ' || to_jsonb(p_role)::text
    || ', "self_certified": false'
    || ', "stage": "WARM"'
    || ', "text": ' || to_jsonb(p_text)::text
    || ', "thread_id": ' || to_jsonb(p_thread_id)::text
    || ', "timestamp": ' || to_jsonb(p_timestamp)::text
    || ', "trust_state": "PROVISIONAL"'
    || '}';
$$;

-- Builds the exact string Python's json.dumps(obj, sort_keys=True,
-- ensure_ascii=False) produces for the entry_id pre-image.
create or replace function ava.canonical_id_json(
  p_timestamp text,
  p_thread_id text,
  p_cycle_id text,
  p_division text,
  p_role text,
  p_text text
) returns text
language sql
immutable
set search_path = ava, public, extensions
as $$
  select '{"cycle_id": ' || to_jsonb(p_cycle_id)::text
    || ', "division": ' || to_jsonb(p_division)::text
    || ', "role": ' || to_jsonb(p_role)::text
    || ', "text": ' || to_jsonb(p_text)::text
    || ', "thread_id": ' || to_jsonb(p_thread_id)::text
    || ', "timestamp": ' || to_jsonb(p_timestamp)::text
    || '}';
$$;

-- -- append: the six-layer gate in the database -----------------------
create or replace function ava.append_memory(
  p_entry_id text,
  p_timestamp text,
  p_thread_id text,
  p_cycle_id text,
  p_division text,
  p_role text,
  p_text text,
  p_evidence_hash text,
  p_previous_hash text,
  p_entry_hash text,
  p_source text
) returns text
language plpgsql
security definer
set search_path = ava, public, extensions
as $$
declare
  head_hash text;
  expected_id text;
  expected_hash text;
begin
  -- 1. identity — division known, source known, thread named.
  if p_division not in ('EXECUTION','MEMORY','VERIFICATION','EVIDENCE','RECOVERY','GOVERNANCE') then
    raise exception 'AVA_GATE_REFUSED layer=identity reason=unknown division %', p_division;
  end if;
  if p_source not in ('ava-merged','talent-agent-plus','jays-graphic-arts') then
    raise exception 'AVA_GATE_REFUSED layer=identity reason=unknown source %', p_source;
  end if;
  if p_thread_id is null or length(p_thread_id) = 0 then
    raise exception 'AVA_GATE_REFUSED layer=identity reason=empty thread_id';
  end if;
  -- 2. schema — role, text bounds, no NUL byte, ids well-formed.
  if p_role not in ('user','ava','system') then
    raise exception 'AVA_GATE_REFUSED layer=schema reason=unknown role %', p_role;
  end if;
  if p_text is null or length(p_text) < 1 or length(p_text) > 100000 then
    raise exception 'AVA_GATE_REFUSED layer=schema reason=text length out of bounds';
  end if;
  -- No NUL-byte check here by design: chr(0) in Postgres returns an
  -- empty string, so a position(chr(0) ...) test would be true for every
  -- input. NUL rejection is enforced client-side (the Python six-layer
  -- gate and the app servers refuse NUL bytes), and Postgres rejects a
  -- NUL byte at the JSON/text boundary before it can reach this
  -- function — invalid input fails closed, never silently stored.
  if p_cycle_id is null or length(p_cycle_id) = 0 then
    raise exception 'AVA_GATE_REFUSED layer=schema reason=empty cycle_id';
  end if;
  if p_timestamp is null or length(p_timestamp) = 0 then
    raise exception 'AVA_GATE_REFUSED layer=schema reason=empty timestamp';
  end if;
  if p_entry_id is null or p_entry_id !~ '^[0-9a-f]{64}$' then
    raise exception 'AVA_GATE_REFUSED layer=schema reason=entry_id not 64 hex chars';
  end if;
  if p_entry_hash is null or p_entry_hash !~ '^[0-9a-f]{64}$' then
    raise exception 'AVA_GATE_REFUSED layer=schema reason=entry_hash not 64 hex chars';
  end if;
  -- 3. crypto — entry_id and entry_hash recomputed from the fields.
  expected_id := encode(digest(convert_to(
    ava.canonical_id_json(p_timestamp, p_thread_id, p_cycle_id, p_division, p_role, p_text),
    'utf8'), 'sha256'), 'hex');
  if expected_id <> p_entry_id then
    raise exception 'AVA_GATE_REFUSED layer=crypto reason=entry_id mismatch';
  end if;
  expected_hash := encode(digest(convert_to(
    ava.canonical_entry_json(p_entry_id, p_timestamp, p_thread_id, p_cycle_id, p_division, p_role, p_text, p_evidence_hash, p_previous_hash),
    'utf8'), 'sha256'), 'hex');
  if expected_hash <> p_entry_hash then
    raise exception 'AVA_GATE_REFUSED layer=crypto reason=entry_hash mismatch';
  end if;
  -- Serialize writers: one append at a time holds the chain.
  lock table ava.memories in share row exclusive mode;
  select entry_hash into head_hash from ava.memories order by seq desc limit 1;
  if p_previous_hash is distinct from coalesce(head_hash, 'GENESIS') then
    raise exception 'AVA_GATE_REFUSED layer=crypto reason=previous_hash does not match chain head';
  end if;
  -- 4. braid — thread/cycle linkage present (non-emptiness checked
  --    above; kept as its own layer for the record).
  -- 5. transaction — entry_id unique.
  if exists (select 1 from ava.memories where entry_id = p_entry_id) then
    raise exception 'AVA_GATE_REFUSED layer=transaction reason=entry_id already present';
  end if;
  -- 6. audit — the insert itself. trust_state is always PROVISIONAL and
  --    self_certified always false here: this chain never self-certifies.
  insert into ava.memories (entry_id, timestamp_text, thread_id, cycle_id, division, role, text, evidence_hash, previous_hash, entry_hash, source)
  values (p_entry_id, p_timestamp, p_thread_id, p_cycle_id, p_division, p_role, p_text, p_evidence_hash, p_previous_hash, p_entry_hash, p_source);
  return p_entry_hash;
end;
$$;

-- -- verify: re-verify the whole chain in the database ----------------
create or replace function ava.verify_memory_chain()
returns jsonb
language plpgsql
security definer
set search_path = ava, public, extensions
as $$
declare
  r record;
  expected_prev text := 'GENESIS';
  expected_hash text;
  n integer := 0;
begin
  for r in select * from ava.memories order by seq loop
    if r.previous_hash is distinct from expected_prev then
      return jsonb_build_object('ok', false, 'entries', n, 'state', 'CHAIN_BREAK', 'certified', false);
    end if;
    expected_hash := encode(digest(convert_to(
      ava.canonical_entry_json(r.entry_id, r.timestamp_text, r.thread_id, r.cycle_id, r.division, r.role, r.text, r.evidence_hash, r.previous_hash),
      'utf8'), 'sha256'), 'hex');
    if expected_hash <> r.entry_hash then
      return jsonb_build_object('ok', false, 'entries', n, 'state', 'HASH_FAILURE', 'certified', false);
    end if;
    expected_prev := r.entry_hash;
    n := n + 1;
  end loop;
  return jsonb_build_object('ok', true, 'entries', n, 'state', 'INTEGRITY_VERIFIED', 'head', expected_prev, 'certified', false);
end;
$$;

-- -- recall + identity (read paths) ------------------------------------
create or replace function ava.recall_memory(
  p_thread_id text default null,
  p_cycle_id text default null,
  p_division text default null,
  p_limit integer default 20
) returns jsonb
language sql
security definer
set search_path = ava, public, extensions
as $$
  select coalesce(jsonb_agg(row_to_json(m) order by m.seq), '[]'::jsonb)
  from (
    select entry_id, timestamp_text, thread_id, cycle_id, division, role,
           text, evidence_hash, previous_hash, entry_hash, source, seq, created_at
    from ava.memories
    where (p_thread_id is null or thread_id = p_thread_id)
      and (p_cycle_id is null or cycle_id = p_cycle_id)
      and (p_division is null or division = p_division)
    order by seq
    limit greatest(1, least(coalesce(p_limit, 20), 100))
  ) m;
$$;

create or replace function ava.get_identity()
returns jsonb
language sql
security definer
set search_path = ava, public, extensions
as $$
  select row_to_json(i)::jsonb from ava.identity i where id = 1;
$$;

-- -- public RPC wrappers (the servers call these) ----------------------
-- Same lockdown as 002_tap_public_wrappers.sql: revoked from public,
-- anon, and authenticated; granted to service_role ONLY. The Python
-- server holds the service-role key and is the only caller.
create or replace function public.ava_append_memory(
  p_entry_id text,
  p_timestamp text,
  p_thread_id text,
  p_cycle_id text,
  p_division text,
  p_role text,
  p_text text,
  p_evidence_hash text,
  p_previous_hash text,
  p_entry_hash text,
  p_source text
) returns text
language sql
security definer
set search_path = ava, public, extensions
as $$
  select ava.append_memory(p_entry_id, p_timestamp, p_thread_id, p_cycle_id,
    p_division, p_role, p_text, p_evidence_hash, p_previous_hash, p_entry_hash, p_source);
$$;

create or replace function public.ava_verify_memory_chain()
returns jsonb
language sql
security definer
set search_path = ava, public, extensions
as $$
  select ava.verify_memory_chain();
$$;

create or replace function public.ava_recall_memory(
  p_thread_id text default null,
  p_cycle_id text default null,
  p_division text default null,
  p_limit integer default 20
) returns jsonb
language sql
security definer
set search_path = ava, public, extensions
as $$
  select ava.recall_memory(p_thread_id, p_cycle_id, p_division, p_limit);
$$;

create or replace function public.ava_get_identity()
returns jsonb
language sql
security definer
set search_path = ava, public, extensions
as $$
  select ava.get_identity();
$$;

revoke all on function public.ava_append_memory(text, text, text, text, text, text, text, text, text, text, text) from public, anon, authenticated;
revoke all on function public.ava_verify_memory_chain() from public, anon, authenticated;
revoke all on function public.ava_recall_memory(text, text, text, integer) from public, anon, authenticated;
revoke all on function public.ava_get_identity() from public, anon, authenticated;

grant execute on function public.ava_append_memory(text, text, text, text, text, text, text, text, text, text, text) to service_role;
grant execute on function public.ava_verify_memory_chain() to service_role;
grant execute on function public.ava_recall_memory(text, text, text, integer) to service_role;
grant execute on function public.ava_get_identity() to service_role;
