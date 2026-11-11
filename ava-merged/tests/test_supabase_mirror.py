"""Tests for the AVA <-> Supabase shared-memory mirror
(services_stdlib/supabase_mirror.py) and the verbatim-mirror path
(HistoryStore.append_existing).

Stdlib unittest. The PostgREST layer is mocked (no live Supabase, no key
needed). The one test that matters most is the canonical-hash equality:
the string the SQL function builds (explicit sorted key order, one JSON
value per field — replicated here exactly as written in
001_ava_unified.sql) must equal, byte-for-byte, what Python's
json.dumps(obj, sort_keys=True, ensure_ascii=False) produces for the
same entry, and the sha256 of that string must equal the entry_hash the
local store computed. That is what makes "same entries, same hashes"
true across stores.

The Postgres half (to_jsonb(value)::text escaping == Python's json.dumps
escaping for a single string) is verified by construction + review, not
by execution: there is no Postgres in this environment. The SQL is
structured so each value is rendered by to_jsonb, which escapes
quote/backslash/control characters the same way Python does and passes
non-ASCII through raw, matching ensure_ascii=False.
"""
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services_stdlib import supabase_mirror  # noqa: E402
from services_stdlib.history_store import HistoryStore  # noqa: E402
from services_stdlib.supabase_mirror import (  # noqa: E402
    GateRefused, NotConfigured, SupabaseMirror, SupabaseMirrorError,
    entry_to_rpc_params, normalize_row)


def _j(v):
    return json.dumps(v, ensure_ascii=False)


def sql_canonical_entry(e):
    """The string ava.canonical_entry_json builds, replicated exactly."""
    ev = _j(e["evidence_hash"]) if e.get("evidence_hash") is not None else "null"
    return ('{"cycle_id": ' + _j(e["cycle_id"])
            + ', "division": ' + _j(e["division"])
            + ', "entry_id": ' + _j(e["entry_id"])
            + ', "evidence_hash": ' + ev
            + ', "previous_hash": ' + _j(e["previous_hash"])
            + ', "role": ' + _j(e["role"])
            + ', "self_certified": false'
            + ', "stage": "WARM"'
            + ', "text": ' + _j(e["text"])
            + ', "thread_id": ' + _j(e["thread_id"])
            + ', "timestamp": ' + _j(e["timestamp"])
            + ', "trust_state": "PROVISIONAL"'
            + '}')


def sql_canonical_id(e):
    """The string ava.canonical_id_json builds, replicated exactly."""
    return ('{"cycle_id": ' + _j(e["cycle_id"])
            + ', "division": ' + _j(e["division"])
            + ', "role": ' + _j(e["role"])
            + ', "text": ' + _j(e["text"])
            + ', "thread_id": ' + _j(e["thread_id"])
            + ', "timestamp": ' + _j(e["timestamp"])
            + '}')


def py_canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def _sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class _Resp:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    def read(self):
        if isinstance(self._payload, (dict, list)):
            return json.dumps(self._payload).encode("utf-8")
        return self._payload.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http_error(url, code, body):
    return urllib.error.HTTPError(url, code, "error", {},
                                  io.BytesIO(body.encode("utf-8")))


class CanonicalHashTests(unittest.TestCase):
    """The SQL formula and the Python formula must agree byte-for-byte."""

    def _check_entry(self, entry):
        without_hash = {k: v for k, v in entry.items() if k != "entry_hash"}
        self.assertEqual(sql_canonical_entry(entry),
                         py_canonical(without_hash))
        self.assertEqual(_sha(sql_canonical_entry(entry)),
                         entry["entry_hash"])
        id_pre = {"thread_id": entry["thread_id"],
                  "cycle_id": entry["cycle_id"],
                  "division": entry["division"], "role": entry["role"],
                  "text": entry["text"], "timestamp": entry["timestamp"]}
        self.assertEqual(sql_canonical_id(entry), py_canonical(id_pre))
        self.assertEqual(_sha(sql_canonical_id(entry)), entry["entry_id"])

    def test_plain_entry_with_evidence(self):
        d = tempfile.mkdtemp()
        try:
            s = HistoryStore(directory=d)
            r = s.append("thread-1", "cycle-1", "MEMORY", "ava",
                         "Rumi — this is AVA.", scopes=["MEMORY"],
                         evidence_hash="aa5aae97c696d1b9")
            self.assertTrue(r["ok"])
            self._check_entry(s._read_entries()[0])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_null_evidence_and_tricky_text(self):
        d = tempfile.mkdtemp()
        try:
            s = HistoryStore(directory=d)
            tricky = ('Quote "back\\slash" newline\ntab\t unicode é — '
                      'em dash, {braces}, [brackets]')
            r = s.append("thread-2", "cycle-1", "MEMORY", "user", tricky,
                         scopes=["MEMORY"], evidence_hash=None)
            self.assertTrue(r["ok"])
            self._check_entry(s._read_entries()[0])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_second_entry_chained(self):
        d = tempfile.mkdtemp()
        try:
            s = HistoryStore(directory=d)
            s.append("t", "c", "MEMORY", "user", "first", scopes=["MEMORY"])
            s.append("t", "c", "MEMORY", "ava", "second", scopes=["MEMORY"])
            entries = s._read_entries()
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[1]["previous_hash"],
                             entries[0]["entry_hash"])
            for e in entries:
                self._check_entry(e)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class AppendExistingTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.store = HistoryStore(directory=self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _valid_entry(self, thread="t", cycle="c", role="user", text="hello"):
        self.store.append(thread, cycle, "MEMORY", role, text,
                          scopes=["MEMORY"])
        return self.store._read_entries()[-1]

    def test_verbatim_round_trip(self):
        e = self._valid_entry()
        d2 = tempfile.mkdtemp()
        try:
            s2 = HistoryStore(directory=d2)
            r = s2.append_existing(e, scopes=["MEMORY"])
            self.assertTrue(r["ok"], r)
            self.assertEqual(r["state"], "CERTIFIED")
            got = s2._read_entries()[0]
            self.assertEqual(got["entry_id"], e["entry_id"])
            self.assertEqual(got["entry_hash"], e["entry_hash"])
            self.assertEqual(got["text"], e["text"])
            self.assertEqual(s2.verify_chain()["state"],
                             "INTEGRITY_VERIFIED")
        finally:
            shutil.rmtree(d2, ignore_errors=True)

    def test_tampered_text_refused_crypto(self):
        e = self._valid_entry()
        bad = dict(e, text="tampered")
        r = self.store.append_existing(bad, scopes=["MEMORY"])
        self.assertFalse(r["ok"])
        self.assertEqual(r["failed_layer"], "crypto")
        self.assertEqual(len(self.store._read_entries()), 1)

    def test_duplicate_entry_id_refused_transaction(self):
        # Same entry_id (same thread/cycle/division/role/text/timestamp —
        # previous_hash is NOT in the entry_id preimage), re-linked onto
        # the current head with a recomputed entry_hash, so the gate
        # reaches the transaction layer instead of failing linkage first.
        from services_stdlib.history_store import _canonical, _sha
        e = self._valid_entry()
        d2 = tempfile.mkdtemp()
        try:
            s2 = HistoryStore(directory=d2)
            self.assertTrue(s2.append_existing(e, scopes=["MEMORY"])["ok"])
            e2 = dict(e)
            e2["previous_hash"] = e["entry_hash"]
            body = {k: v for k, v in e2.items() if k != "entry_hash"}
            e2["entry_hash"] = _sha(_canonical(body))
            r = s2.append_existing(e2, scopes=["MEMORY"])
            self.assertFalse(r["ok"])
            self.assertEqual(r["failed_layer"], "transaction")
        finally:
            shutil.rmtree(d2, ignore_errors=True)

    def test_wrong_previous_hash_refused(self):
        # A valid entry formed against GENESIS cannot append after the
        # local head has moved: linkage fails at the crypto layer.
        e1 = self._valid_entry(text="first")
        d2 = tempfile.mkdtemp()
        try:
            s2 = HistoryStore(directory=d2)
            s2.append("other", "c", "MEMORY", "user", "other",
                      scopes=["MEMORY"])
            r = s2.append_existing(e1, scopes=["MEMORY"])
            self.assertFalse(r["ok"])
            self.assertEqual(r["failed_layer"], "crypto")
        finally:
            shutil.rmtree(d2, ignore_errors=True)

    def test_supabase_row_shape_normalizes(self):
        e = self._valid_entry()
        row = dict(e)
        row["timestamp_text"] = row.pop("timestamp")
        row["seq"] = 7
        row["created_at"] = "2026-11-05T00:00:00+00:00"
        row["source"] = "talent-agent-plus"
        d2 = tempfile.mkdtemp()
        try:
            s2 = HistoryStore(directory=d2)
            r = s2.append_existing(row, scopes=["MEMORY"])
            self.assertTrue(r["ok"], r)
            got = s2._read_entries()[0]
            self.assertEqual(got["entry_hash"], e["entry_hash"])
            self.assertNotIn("source", got)
            self.assertNotIn("seq", got)
        finally:
            shutil.rmtree(d2, ignore_errors=True)


class MirrorClientTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.store = HistoryStore(directory=self.dir)
        self.env_patch = mock.patch.dict(os.environ, {}, clear=False)
        self.env_patch.start()
        os.environ.pop("SUPABASE_URL", None)
        os.environ.pop("SUPABASE_SERVICE_ROLE_KEY", None)

    def tearDown(self):
        self.env_patch.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def _mirror(self):
        return SupabaseMirror(url="https://example.supabase.co",
                              key="test-key-never-real")

    def _entry(self, text="hello from ava"):
        self.store.append("t", "c", "MEMORY", "ava", text, scopes=["MEMORY"])
        return self.store._read_entries()[-1]

    def test_not_configured_fails_safe(self):
        m = SupabaseMirror.from_env()
        self.assertFalse(m.configured)
        self.assertFalse(m.initialize())
        with self.assertRaises(NotConfigured):
            m.append_memory(self._entry())

    def test_initialize_false_on_http_error(self):
        m = self._mirror()
        with mock.patch("urllib.request.urlopen",
                        side_effect=_http_error("https://x", 500, "boom")):
            self.assertFalse(m.initialize())

    def test_append_success_returns_hash(self):
        m = self._mirror()
        e = self._entry()
        with mock.patch("urllib.request.urlopen",
                        return_value=_Resp(200, '"%s"' % e["entry_hash"])):
            self.assertEqual(m.append_memory(e), e["entry_hash"])

    def test_append_gate_refusal_names_layer(self):
        m = self._mirror()
        e = self._entry()
        body = json.dumps({"message":
                           "AVA_GATE_REFUSED layer=crypto reason=x"})
        with mock.patch("urllib.request.urlopen",
                        side_effect=_http_error("https://x", 400, body)):
            with self.assertRaises(GateRefused) as cm:
                m.append_memory(e)
            self.assertEqual(cm.exception.layer, "crypto")

    def test_recall_normalizes_rows(self):
        m = self._mirror()
        e = self._entry()
        row = dict(e)
        row["timestamp_text"] = row.pop("timestamp")
        row["seq"] = 3
        row["source"] = "talent-agent-plus"
        with mock.patch("urllib.request.urlopen",
                        return_value=_Resp(200, [row])):
            rows = m.recall_memory(thread_id="t")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["entry_id"], e["entry_id"])
            self.assertEqual(rows[0]["timestamp"], e["timestamp"])
            self.assertEqual(rows[0]["_source"], "talent-agent-plus")
            self.assertEqual(rows[0]["_seq"], 3)

    def test_verify_chain_passthrough(self):
        m = self._mirror()
        want = {"ok": True, "entries": 3, "state": "INTEGRITY_VERIFIED"}
        with mock.patch("urllib.request.urlopen",
                        return_value=_Resp(200, want)):
            self.assertEqual(m.verify_chain(), want)

    def test_push_entry_writes_supabase_then_local(self):
        m = self._mirror()
        e = self._entry()
        d2 = tempfile.mkdtemp()
        try:
            s2 = HistoryStore(directory=d2)
            with mock.patch(
                    "urllib.request.urlopen",
                    return_value=_Resp(200, '"%s"' % e["entry_hash"])):
                r = m.push_entry(s2, e)
            self.assertTrue(r["ok"], r)
            self.assertEqual(s2._read_entries()[0]["entry_hash"],
                             e["entry_hash"])
        finally:
            shutil.rmtree(d2, ignore_errors=True)

    def test_push_entry_supabase_failure_stores_nothing_local(self):
        m = self._mirror()
        e = self._entry()
        d2 = tempfile.mkdtemp()
        try:
            s2 = HistoryStore(directory=d2)
            body = json.dumps({"message":
                               "AVA_GATE_REFUSED layer=schema reason=x"})
            with mock.patch(
                    "urllib.request.urlopen",
                    side_effect=_http_error("https://x", 400, body)):
                with self.assertRaises(GateRefused):
                    m.push_entry(s2, e)
            self.assertEqual(len(s2._read_entries()), 0)
        finally:
            shutil.rmtree(d2, ignore_errors=True)

    def test_seed_entry_idempotent_on_transaction_refusal(self):
        m = self._mirror()
        e = self._entry()
        body = json.dumps({"message": "AVA_GATE_REFUSED layer=transaction"
                                      " reason=entry_id already present"})
        with mock.patch("urllib.request.urlopen",
                        side_effect=_http_error("https://x", 400, body)):
            r = m.seed_entry(e)
        self.assertEqual(r["state"], "ALREADY_PRESENT")

    def test_sync_pulls_missing_only(self):
        m = self._mirror()
        e1 = self._entry("first")
        e2 = self._entry("second")
        d2 = tempfile.mkdtemp()
        try:
            s2 = HistoryStore(directory=d2)
            s2.append_existing(e1, scopes=["MEMORY"])
            rows = []
            for e in (e1, e2):
                row = dict(e)
                row["timestamp_text"] = row.pop("timestamp")
                row["seq"] = 1 if e is e1 else 2
                row["source"] = "ava-merged"
                rows.append(row)
            with mock.patch("urllib.request.urlopen",
                            return_value=_Resp(200, rows)):
                r = m.sync_from_supabase(s2)
            self.assertTrue(r["ok"], r)
            self.assertEqual(r["synced"], 1)
            self.assertEqual(r["already_present"], 1)
            self.assertEqual(len(s2._read_entries()), 2)
        finally:
            shutil.rmtree(d2, ignore_errors=True)

    def test_sync_stops_on_divergence(self):
        m = self._mirror()
        # Local head is an unrelated entry; the pulled entry was formed
        # against GENESIS, so its previous_hash cannot match.
        self.store.append("local", "c", "MEMORY", "user", "local only",
                          scopes=["MEMORY"])
        d2 = tempfile.mkdtemp()
        try:
            s2 = HistoryStore(directory=d2)
            s2.append("local", "c", "MEMORY", "user", "local only",
                      scopes=["MEMORY"])
            foreign_dir = tempfile.mkdtemp()
            try:
                fs = HistoryStore(directory=foreign_dir)
                fs.append("t", "c", "MEMORY", "ava", "foreign",
                          scopes=["MEMORY"])
                fe = fs._read_entries()[0]
            finally:
                shutil.rmtree(foreign_dir, ignore_errors=True)
            row = dict(fe)
            row["timestamp_text"] = row.pop("timestamp")
            row["seq"] = 9
            row["source"] = "talent-agent-plus"
            with mock.patch("urllib.request.urlopen",
                            return_value=_Resp(200, [row])):
                r = m.sync_from_supabase(s2)
            self.assertFalse(r["ok"])
            self.assertEqual(r["state"], "STOPPED_DIVERGENCE")
            self.assertEqual(len(s2._read_entries()), 1)
        finally:
            shutil.rmtree(d2, ignore_errors=True)

    def test_rpc_params_map_entry(self):
        e = self._entry()
        p = entry_to_rpc_params(e, source="ava-merged")
        self.assertEqual(p["p_entry_id"], e["entry_id"])
        self.assertEqual(p["p_timestamp"], e["timestamp"])
        self.assertEqual(p["p_entry_hash"], e["entry_hash"])
        self.assertEqual(p["p_source"], "ava-merged")
        with self.assertRaises(ValueError):
            entry_to_rpc_params(e, source="not-an-ava")

    def test_normalize_row_keeps_hashes(self):
        e = self._entry()
        row = dict(e)
        row["timestamp_text"] = row.pop("timestamp")
        n = normalize_row(row)
        self.assertEqual(n["entry_hash"], e["entry_hash"])
        self.assertEqual(n["timestamp"], e["timestamp"])


if __name__ == "__main__":
    unittest.main()
