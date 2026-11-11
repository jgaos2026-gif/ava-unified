"""AVA <-> Supabase shared-memory mirror (services_stdlib/supabase_mirror.py).

The local side of the unified AVA memory. The shared chain lives in the
Supabase project "jga-apps", schema `ava` (see
supabase/migrations/001_ava_unified.sql): one table `ava.memories`, one
gate function `ava.append_memory`, one verifier, recall + identity RPCs.

Write discipline (see AVA-UNIFIED-DESIGN.md section 4):
  Supabase FIRST (assigns the chain position, verifies the hash), then
  mirror verbatim into the local WARM history store via
  HistoryStore.append_existing. The local store is never ahead of
  Supabase. If the Supabase write fails, nothing is stored locally.

Sync: pull shared entries in seq order; append each one missing locally
(by entry_id) through the gated verbatim path. If a pulled entry's
previous_hash does not equal the local head, sync STOPS and reports the
divergence. Never silently repair, never re-hash, never drop.

Secrets: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY come from the
environment ONLY. Both must be set and the URL must be https. On any
failure (not configured, unreachable, wrong key) the client fails safe:
it returns False / raises a short error and never crashes, never retries
in a loop, never logs a key. No key is ever written to a file, a log
line, or an exception message. The project URL host is not secret.

Stdlib only (urllib), mirroring the proven pattern in the Render
packages' supabase_store.py. No new dependency.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

_RPC_TIMEOUT = 10.0
_GET_TIMEOUT = 10.0
_GATE_RE = re.compile(r"AVA_GATE_REFUSED layer=([a-z]+)")

# The three live AVA instances. The local system writes as 'ava-merged'.
SOURCES = ("ava-merged", "talent-agent-plus", "jays-graphic-arts")


class SupabaseMirrorError(Exception):
    """A Supabase call failed. The message never contains a key."""


class GateRefused(SupabaseMirrorError):
    """ava.append_memory refused the entry; `layer` names the failed layer."""

    def __init__(self, layer, detail=""):
        self.layer = layer
        super().__init__("gate refused layer=%s %s" % (layer, detail))


class NotConfigured(SupabaseMirrorError):
    """SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing or not https."""


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def entry_to_rpc_params(entry: dict, source: str = "ava-merged") -> dict:
    """Map a local history entry to the ava_append_memory parameters.
    The entry keeps its own entry_id, timestamp and entry_hash — the
    database recomputes both hashes from the fields and refuses on
    mismatch, so a caller cannot smuggle in a hash that does not match."""
    if source not in SOURCES:
        raise ValueError("unknown source: %s" % source)
    return {
        "p_entry_id": entry["entry_id"],
        "p_timestamp": entry.get("timestamp") or entry.get("timestamp_text"),
        "p_thread_id": entry["thread_id"],
        "p_cycle_id": entry["cycle_id"],
        "p_division": entry["division"],
        "p_role": entry["role"],
        "p_text": entry["text"],
        "p_evidence_hash": entry.get("evidence_hash"),
        "p_previous_hash": entry["previous_hash"],
        "p_entry_hash": entry["entry_hash"],
        "p_source": source,
    }


def normalize_row(row: dict) -> dict:
    """Map a Supabase ava.memories row to the local 12-key entry shape.
    The local store holds exactly the twelve canonical keys plus
    entry_hash; seq/created_at/source ride along under underscore keys
    and are stripped by HistoryStore.append_existing."""
    entry = {
        "entry_id": row["entry_id"],
        "timestamp": row.get("timestamp_text") or row.get("timestamp"),
        "thread_id": row["thread_id"],
        "cycle_id": row["cycle_id"],
        "division": row["division"],
        "role": row["role"],
        "text": row["text"],
        "evidence_hash": row.get("evidence_hash"),
        "trust_state": "PROVISIONAL",
        "self_certified": False,
        "previous_hash": row["previous_hash"],
        "stage": "WARM",
        "entry_hash": row["entry_hash"],
        "_source": row.get("source"),
        "_seq": row.get("seq"),
    }
    return entry


class SupabaseMirror:
    """PostgREST client for the shared `ava` memory chain. Fail-safe."""

    def __init__(self, url: str | None = None, key: str | None = None):
        self._url = (url if url is not None else _env("SUPABASE_URL")).rstrip("/")
        self._key = key if key is not None else _env("SUPABASE_SERVICE_ROLE_KEY")

    @classmethod
    def from_env(cls):
        return cls()

    @property
    def configured(self) -> bool:
        return bool(self._url and self._key
                    and self._url.startswith("https://"))

    def _headers(self) -> dict:
        return {
            "apikey": self._key,
            "Authorization": "Bearer " + self._key,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, body=None, timeout: float = _RPC_TIMEOUT):
        if not self.configured:
            raise NotConfigured("Supabase URL/key not configured")
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self._url + path, data=data,
                                     headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return resp.status, json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:300]
            raise SupabaseMirrorError(
                "Supabase HTTP %s on %s: %s" % (e.code, path, detail))
        except Exception as e:  # noqa: BLE001 - fail safe, short message
            raise SupabaseMirrorError(
                "Supabase request failed on %s: %s" % (path, type(e).__name__))

    def _rpc(self, name: str, params: dict | None = None):
        _, payload = self._request("POST", "/rest/v1/rpc/" + name,
                                   body=params or {})
        return payload

    # -- health -------------------------------------------------------
    def initialize(self) -> bool:
        """Ping the project through the chain verifier. False on any
        failure; never raises, never logs a key."""
        try:
            self.verify_chain()
            return True
        except SupabaseMirrorError:
            return False

    # -- reads --------------------------------------------------------
    def verify_chain(self) -> dict:
        return self._rpc("ava_verify_memory_chain")

    def get_identity(self) -> dict:
        return self._rpc("ava_get_identity")

    def recall_memory(self, thread_id=None, cycle_id=None, division=None,
                      limit: int = 20) -> list:
        rows = self._rpc("ava_recall_memory", {
            "p_thread_id": thread_id,
            "p_cycle_id": cycle_id,
            "p_division": division,
            "p_limit": max(1, min(int(limit), 100)),
        })
        if not isinstance(rows, list):
            raise SupabaseMirrorError("ava_recall_memory did not return a list")
        return [normalize_row(r) for r in rows]

    # -- writes -------------------------------------------------------
    def append_memory(self, entry: dict, source: str = "ava-merged") -> str:
        """Write one entry to the shared chain. Returns the entry_hash.
        Raises GateRefused (layer named) when the database gate refuses,
        SupabaseMirrorError otherwise. Stores nothing locally — the
        caller mirrors verbatim after a successful return."""
        try:
            result = self._rpc("ava_append_memory",
                               entry_to_rpc_params(entry, source))
        except SupabaseMirrorError as e:
            m = _GATE_RE.search(str(e))
            if m:
                raise GateRefused(m.group(1))
            raise
        if not isinstance(result, str) or len(result) != 64:
            raise SupabaseMirrorError("ava_append_memory returned no entry hash")
        return result

    def push_entry(self, store, entry: dict, source: str = "ava-merged") -> dict:
        """Write discipline in one call: Supabase first, then mirror
        verbatim locally. If the Supabase write fails, nothing is stored
        locally. Returns the local append result on success."""
        entry_hash = self.append_memory(entry, source)
        if entry_hash != entry.get("entry_hash"):
            raise SupabaseMirrorError(
                "shared chain returned a different entry hash")
        return store.append_existing(entry, scopes=["MEMORY"])

    def seed_entry(self, entry: dict, source: str = "ava-merged") -> dict:
        """One-time backfill of an entry that already exists locally
        (written before the shared chain existed). Appends to Supabase
        only — the local copy is already there. A transaction-layer
        refusal means it is already seeded; that is reported, not an
        error."""
        try:
            entry_hash = self.append_memory(entry, source)
            return {"ok": True, "state": "SEEDED", "entry_hash": entry_hash,
                    "entry_id": entry["entry_id"]}
        except GateRefused as e:
            if e.layer == "transaction":
                return {"ok": True, "state": "ALREADY_PRESENT",
                        "entry_id": entry["entry_id"]}
            raise

    def sync_from_supabase(self, store, limit: int = 100) -> dict:
        """Pull shared entries in seq order; append each one missing
        locally through the gated verbatim path. Stops at the first
        failure (e.g. a previous_hash that does not match the local
        head = chain divergence) and reports it. Never silently repairs."""
        rows = self.recall_memory(limit=limit)
        local_ids = {e.get("entry_id") for e in store._read_entries()}
        synced = 0
        already = 0
        for entry in rows:
            if entry["entry_id"] in local_ids:
                already += 1
                continue
            result = store.append_existing(entry, scopes=["MEMORY"])
            if not result.get("ok"):
                return {"ok": False, "synced": synced,
                        "already_present": already,
                        "stopped_at": entry["entry_id"],
                        "failed_layer": result.get("failed_layer"),
                        "state": "STOPPED_DIVERGENCE"}
            local_ids.add(entry["entry_id"])
            synced += 1
        return {"ok": True, "synced": synced, "already_present": already,
                "state": "SYNCED"}


def _seed_entries(store):
    """The three proven mesh-talk entries (thread stitch-rumi-2026-11-05).
    The seed of the shared chain. Reads them from the local store."""
    rec = store.recall(thread_id="stitch-rumi-2026-11-05",
                       division="MEMORY", scopes=["MEMORY"])
    return rec.get("entries", [])


def main(argv=None):
    """Small CLI for hand-driving the mirror. Never prints a key.
    Usage: supabase_mirror.py [verify|identity|sync|seed]
    Env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY."""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from history_store import HistoryStore

    args = list(argv or [])
    cmd = args[0] if args else "verify"
    mirror = SupabaseMirror.from_env()
    if not mirror.configured:
        print("NOT_CONFIGURED: set SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY")
        return 2
    if cmd == "verify":
        print(json.dumps(mirror.verify_chain(), indent=2))
        return 0
    if cmd == "identity":
        print(json.dumps(mirror.get_identity(), indent=2))
        return 0
    if cmd == "sync":
        store = HistoryStore()
        print(json.dumps(mirror.sync_from_supabase(store), indent=2))
        return 0
    if cmd == "seed":
        store = HistoryStore()
        results = []
        for entry in _seed_entries(store):
            results.append(mirror.seed_entry(entry))
        print(json.dumps(results, indent=2))
        return 0
    print("unknown command: %s (verify|identity|sync|seed)" % cmd)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
