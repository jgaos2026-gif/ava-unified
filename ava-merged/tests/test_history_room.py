"""Tests for the 2026-11-05 build: persistent history + six-division
access (Item 1), OASIS room server (Item 4a), organism /health fix
(Item 4b). Stdlib unittest, no live mesh needed. Items 2 (STT) and 3
(avatar) are browser-only HTML/JS and are checked by node --check
plus a source read, not by this suite.
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services_stdlib import history_store  # noqa: E402
from services_stdlib import room_server  # noqa: E402


def _scopes(*divisions):
    return list(divisions)


class TestHistoryStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ava_history_test_")
        self.store = history_store.HistoryStore(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_append_certified_and_recall_by_thread_cycle_limit(self):
        r1 = self.store.append(thread_id="T1", cycle_id="C1",
                               division="MEMORY", role="user",
                               text="hello ava", scopes=_scopes("MEMORY"))
        self.assertTrue(r1["ok"])
        self.assertTrue(r1["certified"])
        self.assertEqual(r1["state"], "CERTIFIED")
        self.store.append(thread_id="T1", cycle_id="C2",
                          division="MEMORY", role="ava",
                          text="hello john", scopes=_scopes("MEMORY"))
        self.store.append(thread_id="T2", cycle_id="C3",
                          division="EVIDENCE", role="user",
                          text="other thread", scopes=_scopes("EVIDENCE"))
        got = self.store.recall(thread_id="T1", scopes=_scopes("MEMORY"))
        self.assertTrue(got["ok"])
        self.assertEqual(got["total_matching"], 2)
        got = self.store.recall(cycle_id="C2", scopes=_scopes("MEMORY"))
        self.assertEqual(len(got["entries"]), 1)
        self.assertEqual(got["entries"][0]["text"], "hello john")
        got = self.store.recall(thread_id="T1", scopes=_scopes("MEMORY"),
                                limit=1)
        self.assertEqual(len(got["entries"]), 1)

    def test_scope_refusal_names_division(self):
        self.store.append(thread_id="T1", cycle_id="C1",
                          division="MEMORY", role="user", text="x",
                          scopes=_scopes("MEMORY"))
        refused = self.store.recall(division="MEMORY", scopes=_scopes("EVIDENCE"))
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["state"], "REFUSED")
        self.assertEqual(refused["division"], "MEMORY")
        write = self.store.append(thread_id="T1", cycle_id="C9",
                                  division="GOVERNANCE", role="user",
                                  text="x", scopes=_scopes("MEMORY"))
        self.assertFalse(write["ok"])
        self.assertEqual(write["failed_layer"], "identity")
        self.assertEqual(write["state"], "QUARANTINED")

    def test_unknown_division_refused(self):
        write = self.store.append(thread_id="T1", cycle_id="C1",
                                  division="FINANCE", role="user",
                                  text="x", scopes=_scopes("FINANCE"))
        self.assertFalse(write["ok"])
        self.assertEqual(write["failed_layer"], "identity")

    def test_malformed_entry_quarantined_with_layer_named(self):
        bad = self.store.append(thread_id="T1", cycle_id="C1",
                                division="MEMORY", role="user",
                                text="has\x00null", scopes=_scopes("MEMORY"))
        self.assertFalse(bad["ok"])
        self.assertEqual(bad["failed_layer"], "schema")
        self.assertEqual(self.store.verify_chain()["entries"], 0)
        with open(os.path.join(self.tmp, "history_quarantine.jsonl")) as f:
            q = json.loads(f.readline())
        self.assertEqual(q["failed_layer"], "schema")

    def test_chain_verify_and_tamper_detected(self):
        self.store.append(thread_id="T1", cycle_id="C1",
                          division="MEMORY", role="user", text="one",
                          scopes=_scopes("MEMORY"))
        self.assertTrue(self.store.verify_chain()["ok"])
        with open(os.path.join(self.tmp, "history.jsonl"), "a") as f:
            f.write('{"entry_hash": "tampered", "previous_hash": "nope"}\n')
        v = history_store.HistoryStore(self.tmp).verify_chain()
        self.assertFalse(v["ok"])
        self.assertEqual(v["state"], "CHAIN_BREAK")

    def _tamper_first_row_text(self):
        path = os.path.join(self.tmp, "history.jsonl")
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        first = json.loads(lines[0])
        first["text"] = "tampered"
        lines[0] = json.dumps(first) + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)

    def test_append_refused_after_external_tamper(self):
        # The fixed write path: a store mounted on a healthy chain,
        # then an existing row modified externally, must refuse the
        # next append instead of certifying on top of corruption.
        self.store.append(thread_id="T1", cycle_id="C1",
                          division="MEMORY", role="user", text="one",
                          scopes=_scopes("MEMORY"))
        self.store.append(thread_id="T1", cycle_id="C2",
                          division="MEMORY", role="ava", text="two",
                          scopes=_scopes("MEMORY"))
        self._tamper_first_row_text()
        r = self.store.append(thread_id="T1", cycle_id="C3",
                              division="MEMORY", role="user", text="three",
                              scopes=_scopes("MEMORY"))
        self.assertFalse(r["ok"])
        self.assertFalse(r["certified"])
        self.assertEqual(r["state"], "QUARANTINED")
        self.assertEqual(r["failed_layer"], "crypto")
        self.assertEqual(self.store.verify_chain()["entries"], 0)
        # A fresh mount on the tampered file still refuses writes.
        fresh = history_store.HistoryStore(self.tmp)
        r2 = fresh.append(thread_id="T1", cycle_id="C4",
                          division="MEMORY", role="user", text="four",
                          scopes=_scopes("MEMORY"))
        self.assertFalse(r2["ok"])
        self.assertEqual(r2["failed_layer"], "crypto")

    def test_append_refused_after_last_row_tamper(self):
        # The stored-head case: tampering the last row must also
        # refuse the next append, not link a new entry onto it.
        self.store.append(thread_id="T1", cycle_id="C1",
                          division="MEMORY", role="user", text="one",
                          scopes=_scopes("MEMORY"))
        path = os.path.join(self.tmp, "history.jsonl")
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        last = json.loads(lines[-1])
        last["text"] = "tampered"
        lines[-1] = json.dumps(last) + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        r = self.store.append(thread_id="T1", cycle_id="C2",
                              division="MEMORY", role="ava", text="two",
                              scopes=_scopes("MEMORY"))
        self.assertFalse(r["ok"])
        self.assertFalse(r["certified"])
        self.assertEqual(r["failed_layer"], "crypto")

    def test_append_existing_refused_after_external_tamper(self):
        self.store.append(thread_id="T1", cycle_id="C1",
                          division="MEMORY", role="user", text="one",
                          scopes=_scopes("MEMORY"))
        other_tmp = tempfile.mkdtemp(prefix="ava_history_other_")
        try:
            other = history_store.HistoryStore(other_tmp)
            other.append(thread_id="T9", cycle_id="C9",
                         division="MEMORY", role="user", text="other",
                         scopes=_scopes("MEMORY"))
            with open(os.path.join(other_tmp, "history.jsonl")) as f:
                entry = json.loads(f.readline())
        finally:
            shutil.rmtree(other_tmp, ignore_errors=True)
        self._tamper_first_row_text()
        r = self.store.append_existing(entry, scopes=_scopes("MEMORY"))
        self.assertFalse(r["ok"])
        self.assertFalse(r["certified"])
        self.assertEqual(r["failed_layer"], "crypto")

    def test_divisions_are_the_six_bct_strands_awaiting_ruling(self):
        d = self.store.divisions()
        self.assertEqual(d["divisions"],
                         ["EXECUTION", "MEMORY", "VERIFICATION",
                          "EVIDENCE", "RECOVERY", "GOVERNANCE"])
        self.assertEqual(d["status"], "AWAITING_JOHNS_RULING")
        self.assertFalse(d["certified"])


class TestRoomServer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ava_room_test_")
        self.server = room_server.create_server(0, ledger_dir=self.tmp)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _req(self, path, method="GET", payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            "http://127.0.0.1:%d%s" % (self.port, path), data=data,
            headers={"Content-Type": "application/json"}, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    def _envelope(self, **over):
        env = {"schema": "JGA-AVA-STITCH-ENVELOPE-1",
               "timestamp": 1730000000.0, "source": "AVA",
               "room": "ava", "event_type": "AVA_EVENT",
               "payload": {"note": "test"},
               "governance": {"no_bypass": True, "no_silent_trust": True,
                              "no_self_certification": True,
                              "preserve_failed_evidence": True}}
        env.update(over)
        return env

    def test_status_endpoints_all_answer(self):
        for path in ("/api/status", "/api/room/stitchbridge/status",
                     "/api/room/spine/status", "/api/room/sb688/status"):
            status, body = self._req(path)
            self.assertEqual(status, 200, path)
            self.assertTrue(body["ok"])

    def test_health_and_verify(self):
        status, body = self._req("/health")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        status, body = self._req("/api/room/stitchbridge/verify",
                                 method="POST", payload=self._envelope())
        self.assertTrue(body["verified"])
        self.assertFalse(body["certified"])

    def test_append_certified_then_malformed_quarantined(self):
        status, body = self._req("/api/room/ledger/append", method="POST",
                                 payload=self._envelope())
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertTrue(body["certified"])
        status, body = self._req("/api/room/ledger/append", method="POST",
                                 payload={"schema": "WRONG"})
        self.assertEqual(status, 422)
        self.assertEqual(body["failed_layer"], "schema")
        self.assertEqual(body["state"], "QUARANTINED")
        status, body = self._req("/api/room/ledger/verify")
        self.assertTrue(body["verification"]["ok"])
        self.assertEqual(body["verification"]["entries"], 1)

    def test_event_and_cross_accept_envelopes(self):
        for path in ("/api/room/stitchbridge/event",
                     "/api/room/stitchbridge/cross"):
            status, body = self._req(path, method="POST",
                                     payload=self._envelope())
            self.assertEqual(status, 200, path)
            self.assertTrue(body["ok"])


class TestOrganismHealth(unittest.TestCase):
    """Load a COPY of local_organism_core.py from a temp dir so the
    test never touches the real AVA_ORGANISM data."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ava_organism_test_")
        src = os.path.join(os.path.dirname(__file__), "..",
                           "services_stdlib", "local_organism_core.py")
        dst = os.path.join(self.tmp, "local_organism_core.py")
        shutil.copy(src, dst)
        spec = importlib.util.spec_from_file_location(
            "organism_under_test", dst)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_health_ok_without_model_reports_unresolved_separately(self):
        report = self.mod.build_health_response(
            None, {"ok": True, "entries": 1,
                   "state": "INTEGRITY_VERIFIED"},
            {"identity": {"name": "AVA"}})
        self.assertTrue(report["ok"])
        self.assertIsNone(report["brain"]["model"])
        self.assertFalse(report["brain"]["model_available"])
        self.assertEqual(report["brain"]["state"], "LOCAL_MODEL_UNRESOLVED")

    def test_health_not_ok_when_ledger_broken(self):
        report = self.mod.build_health_response(
            None, {"ok": False, "entries": 0, "state": "CHAIN_BREAK"},
            {"identity": {"name": "AVA"}})
        self.assertFalse(report["ok"])
        self.assertEqual(report["brain"]["state"], "LOCAL_MODEL_UNRESOLVED")


if __name__ == "__main__":
    unittest.main()
