-- 003_recall_memory_chain_check.sql -- AVA unified memory (2026-11-10)
-- Replaces ava.recall_memory from 001_ava_unified.sql (CREATE OR REPLACE).
-- Change: the whole existing chain must verify before any row is served.
-- The 001 version returned rows without checking the chain, so a caller
-- could read (and a sync could mirror) entries sitting on top of
-- corruption. The 003 version calls ava.verify_memory_chain() first
-- (from 001) and refuses with AVA_GATE_REFUSED layer=crypto when the
-- chain does not verify — fail closed, same refusal shape as the 002
-- append gate. The public wrapper public.ava_recall_memory needs no
-- change: it calls ava.recall_memory and picks up the new body.
-- The SELECT that serves the rows is byte-identical to 001; only the
-- verification prologue and the plpgsql wrapper are new (verify with
-- diff: extract the SELECT from 001 and from this file).
-- Requires 001 applied first (ava.verify_memory_chain lives there).
-- Apply in the Supabase Dashboard SQL editor, after 001 and 002.
-- Idempotent: re-running replaces the same function with the same body.
-- NOT executed against the live database by the agent; apply + verify
-- in the Dashboard (call ava_verify_memory_chain after applying, and
-- confirm a recall on a healthy chain still returns rows).

create or replace function ava.recall_memory(
  p_thread_id text default null,
  p_cycle_id text default null,
  p_division text default null,
  p_limit integer default 20
) returns jsonb
language plpgsql
security definer
set search_path = ava, public, extensions
as $$
declare
  chain_report jsonb;
begin
  -- crypto -- the whole existing chain must verify before any row is
  -- served. Serving rows from a broken chain would hand the caller
  -- (and the local mirror sync) entries that sit on top of corruption,
  -- so a failed verification refuses the read (fail closed). Uses the
  -- verifier from 001.
  chain_report := ava.verify_memory_chain();
  if not coalesce((chain_report ->> 'ok')::boolean, false) then
    raise exception 'AVA_GATE_REFUSED layer=crypto reason=existing chain does not verify state=%', chain_report ->> 'state';
  end if;
  return (
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
  ) m
  );
end;
$$;
