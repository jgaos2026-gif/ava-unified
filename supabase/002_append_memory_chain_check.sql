-- 002_append_memory_chain_check.sql -- AVA unified memory (2026-11-10)
-- Replaces ava.append_memory from 001_ava_unified.sql (CREATE OR REPLACE).
-- Change: the whole existing chain must verify before any append. The 001
-- version checked only that p_previous_hash matched the current head, so
-- a broken chain could still accept new entries on top of corruption.
-- Requires 001 applied first (ava.verify_memory_chain lives there).
-- Apply in the Supabase Dashboard SQL editor, after 001. Idempotent:
-- re-running replaces the same function with the same body.
-- NOT executed against the live database by the agent; apply + verify
-- in the Dashboard (call ava_verify_memory_chain after applying).

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
  chain_report jsonb;
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
  -- 3b. crypto -- the whole existing chain must verify before any
  --     append. Appending onto a broken chain would certify new
  --     entries on top of corruption, so a failed verification
  --     refuses the write (fail closed). Uses the verifier from 001.
  chain_report := ava.verify_memory_chain();
  if not coalesce((chain_report ->> 'ok')::boolean, false) then
    raise exception 'AVA_GATE_REFUSED layer=crypto reason=existing chain does not verify state=%', chain_report ->> 'state';
  end if;
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
