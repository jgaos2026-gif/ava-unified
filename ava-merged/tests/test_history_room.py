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
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services_stdlib import history_store  # noqa: E402
from services_stdlib import room_server  # noqa: E402
from services_stdlib import scope_tokens  # noqa: E402


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

    def test_recall_reverifies_from_disk_after_mount(self):
        # Finding 13: recall on the SAME store instance must re-verify
        # the chain fresh from disk. A row tampered after mount must
        # not be served on the strength of the mount-time check.
        self.store.append(thread_id="T1", cycle_id="C1",
                          division="MEMORY", role="user", text="one",
                          scopes=_scopes("MEMORY"))
        self.store.append(thread_id="T1", cycle_id="C2",
                          division="MEMORY", role="ava", text="two",
                          scopes=_scopes("MEMORY"))
        self._tamper_first_row_text()
        got = self.store.recall(thread_id="T1", scopes=_scopes("MEMORY"))
        self.assertTrue(got["ok"])
        self.assertEqual(got["entries"], [])
        self.assertEqual(got["total_matching"], 0)
        self.assertFalse(got["chain"]["ok"])
        self.assertEqual(got["chain"]["state"], "HASH_FAILURE")
        self.assertNotIn("TAMPERED", json.dumps(got["entries"]))

    def test_recall_serves_verified_prefix_after_last_row_tamper(self):
        # Finding 13, partial case: tampering only the last row serves
        # the verified prefix (the first entry), not the tampered row.
        self.store.append(thread_id="T1", cycle_id="C1",
                          division="MEMORY", role="user", text="one",
                          scopes=_scopes("MEMORY"))
        self.store.append(thread_id="T1", cycle_id="C2",
                          division="MEMORY", role="ava", text="two",
                          scopes=_scopes("MEMORY"))
        path = os.path.join(self.tmp, "history.jsonl")
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        last = json.loads(lines[-1])
        last["text"] = "tampered"
        lines[-1] = json.dumps(last) + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        got = self.store.recall(thread_id="T1", scopes=_scopes("MEMORY"))
        self.assertEqual(len(got["entries"]), 1)
        self.assertEqual(got["entries"][0]["text"], "one")
        self.assertEqual(got["total_matching"], 1)
        self.assertFalse(got["chain"]["ok"])

    def test_entry_id_recomputes_from_stored_timestamp(self):
        # Finding 18: the entry_id must recompute from the stored
        # timestamp and the other stored fields.
        self.store.append(thread_id="T1", cycle_id="C1",
                          division="MEMORY", role="user", text="one",
                          scopes=_scopes("MEMORY"))
        with open(os.path.join(self.tmp, "history.jsonl")) as f:
            entry = json.loads(f.readline())
        preimage = {"thread_id": entry["thread_id"],
                    "cycle_id": entry["cycle_id"],
                    "division": entry["division"],
                    "role": entry["role"],
                    "text": entry["text"],
                    "timestamp": entry["timestamp"]}
        self.assertEqual(
            history_store._sha(history_store._canonical(preimage)),
            entry["entry_id"])

    def test_entry_id_recomputes_when_clock_ticks_between_reads(self):
        # Finding 18, adversarial case: force the clock to tick between
        # successive reads inside append(). With one clock read the id
        # still recomputes; with two reads it would not.
        calls = {"n": 0}

        def ticking(fmt):
            calls["n"] += 1
            return "2026-11-10T00:00:0%d" % calls["n"]

        with mock.patch.object(history_store.time, "strftime", ticking):
            r = self.store.append(thread_id="T1", cycle_id="C1",
                                  division="MEMORY", role="user", text="one",
                                  scopes=_scopes("MEMORY"))
        self.assertTrue(r["ok"])
        with open(os.path.join(self.tmp, "history.jsonl")) as f:
            entry = json.loads(f.readline())
        preimage = {"thread_id": entry["thread_id"],
                    "cycle_id": entry["cycle_id"],
                    "division": entry["division"],
                    "role": entry["role"],
                    "text": entry["text"],
                    "timestamp": entry["timestamp"]}
        self.assertEqual(
            history_store._sha(history_store._canonical(preimage)),
            entry["entry_id"])

    def test_append_reports_declared_scopes_untrusted(self):
        # Finding 12: declared scopes keep working, but the result
        # says so — "declared-untrusted", never "authenticated".
        r = self.store.append(thread_id="T1", cycle_id="C1",
                              division="MEMORY", role="user", text="one",
                              scopes=_scopes("MEMORY"))
        self.assertTrue(r["ok"])
        self.assertEqual(r["scope_trust"], "declared-untrusted")
        got = self.store.recall(thread_id="T1", scopes=_scopes("MEMORY"))
        self.assertEqual(got["scope_trust"], "declared-untrusted")


class TestScopeTokens(unittest.TestCase):
    """Finding 12: signed scope tokens (services_stdlib/scope_tokens.py).
    Keys here are generated in-test and never touch disk."""

    def setUp(self):
        self.hmac_auth = scope_tokens.ScopeTokenAuthority(
            hmac_key=b"test-hmac-key-32-bytes-long!!")
        self.other_hmac_auth = scope_tokens.ScopeTokenAuthority(
            hmac_key=b"different-key-32-bytes-long!!")

    def test_hmac_issue_verify_round_trip(self):
        token = self.hmac_auth.issue(["MEMORY", "GOVERNANCE"],
                                     subject="ava-merged")
        self.assertTrue(token.startswith("AVA1."))
        self.assertEqual(len(token.split(".")), 3)
        report = self.hmac_auth.verify(token)
        self.assertTrue(report["ok"])
        self.assertTrue(report["authenticated"])
        self.assertEqual(report["method"], "hmac")
        self.assertEqual(report["sub"], "ava-merged")
        self.assertEqual(report["scopes"], ["GOVERNANCE", "MEMORY"])

    def test_hmac_tampered_token_refused(self):
        token = self.hmac_auth.issue(["MEMORY"], subject="ava-merged")
        tampered = token[:-4] + "AAAA"
        report = self.hmac_auth.verify(tampered)
        self.assertFalse(report["ok"])
        self.assertFalse(report["authenticated"])
        self.assertIn("does not verify", report["error"])

    def test_hmac_wrong_key_refused(self):
        token = self.hmac_auth.issue(["MEMORY"], subject="ava-merged")
        report = self.other_hmac_auth.verify(token)
        self.assertFalse(report["ok"])

    def test_hmac_expired_token_refused(self):
        token = self.hmac_auth.issue(["MEMORY"], subject="ava-merged")
        real_now = time.time()
        with mock.patch.object(scope_tokens.time, "time",
                               lambda: real_now + 7200):
            report = self.hmac_auth.verify(token)
        self.assertFalse(report["ok"])
        self.assertEqual(report["error"], "token expired")

    def test_hmac_unknown_scope_rejected_at_issue(self):
        with self.assertRaises(scope_tokens.ScopeTokenError):
            self.hmac_auth.issue(["FINANCE"], subject="ava-merged")

    def test_verify_without_key_refused(self):
        token = self.hmac_auth.issue(["MEMORY"], subject="ava-merged")
        report = scope_tokens.ScopeTokenAuthority().verify(token)
        self.assertFalse(report["ok"])
        self.assertIn("no HMAC verifying key", report["error"])

    def test_malformed_token_refused(self):
        for bad in ("", "AVA1.", "AVA1.@@@.@@@", "not-a-token",
                    "AVA1." + "x" * 10):
            report = self.hmac_auth.verify(bad)
            self.assertFalse(report["ok"], bad)

    def test_ed25519_issue_verify_round_trip(self):
        seed = scope_tokens.generate_ed25519_seed()
        auth = scope_tokens.ScopeTokenAuthority(ed_seed=seed)
        token = auth.issue(["MEMORY"], subject="ava-merged")
        report = auth.verify(token)
        self.assertTrue(report["ok"])
        self.assertTrue(report["authenticated"])
        self.assertEqual(report["method"], "ed25519")
        self.assertEqual(report["scopes"], ["MEMORY"])
        # A verifier holding only the public key verifies too.
        pub_only = scope_tokens.ScopeTokenAuthority(ed_pub=auth.ed_pub)
        self.assertTrue(pub_only.verify(token)["ok"])

    def test_ed25519_tampered_refused(self):
        seed = scope_tokens.generate_ed25519_seed()
        auth = scope_tokens.ScopeTokenAuthority(ed_seed=seed)
        token = auth.issue(["MEMORY"], subject="ava-merged")
        report = auth.verify(token[:-4] + "AAAA")
        self.assertFalse(report["ok"])
        self.assertIn("does not verify", report["error"])

    def test_issue_without_key_refused(self):
        with self.assertRaises(scope_tokens.ScopeTokenError):
            scope_tokens.ScopeTokenAuthority().issue(["MEMORY"])


class TestHistoryStoreScopeTokens(unittest.TestCase):
    """Finding 12: the history store gate verifies tokens; declared
    scopes keep working but are reported untrusted."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ava_history_token_test_")
        self.auth = scope_tokens.ScopeTokenAuthority(
            hmac_key=b"test-hmac-key-32-bytes-long!!")
        self.token = self.auth.issue(["MEMORY", "GOVERNANCE"],
                                     subject="ava-merged")
        self.store = history_store.HistoryStore(
            self.tmp, scope_authority=self.auth)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_append_with_valid_token_is_authenticated(self):
        r = self.store.append(thread_id="T1", cycle_id="C1",
                              division="MEMORY", role="user", text="one",
                              scopes=["EVIDENCE"], scope_token=self.token)
        self.assertTrue(r["ok"])
        self.assertTrue(r["certified"])
        self.assertEqual(r["scope_trust"], "authenticated")

    def test_append_token_scopes_override_declared_scopes(self):
        # The token's scopes are the effective scopes; the declared
        # list is ignored when a valid token is presented.
        r = self.store.append(thread_id="T1", cycle_id="C1",
                              division="GOVERNANCE", role="user",
                              text="gov", scopes=["EVIDENCE"],
                              scope_token=self.token)
        self.assertTrue(r["ok"])
        self.assertEqual(r["scope_trust"], "authenticated")

    def test_append_with_forged_token_refused_identity(self):
        forged = self.token[:-6] + "AAAAAA"
        r = self.store.append(thread_id="T1", cycle_id="C1",
                              division="MEMORY", role="user", text="one",
                              scopes=["MEMORY"], scope_token=forged)
        self.assertFalse(r["ok"])
        self.assertFalse(r["certified"])
        self.assertEqual(r["failed_layer"], "identity")
        self.assertEqual(r["state"], "QUARANTINED")
        self.assertEqual(r["scope_trust"], "invalid-token")
        self.assertEqual(self.store.verify_chain()["entries"], 0)
        # The forged token itself is never written to the quarantine file.
        with open(os.path.join(self.tmp, "history_quarantine.jsonl")) as f:
            record = json.loads(f.readline())
        self.assertNotIn(forged, json.dumps(record))
        self.assertEqual(record["scope_trust"], "invalid-token")

    def test_recall_with_valid_token_is_authenticated(self):
        self.store.append(thread_id="T1", cycle_id="C1",
                          division="MEMORY", role="user", text="one",
                          scopes=["MEMORY"], scope_token=self.token)
        got = self.store.recall(thread_id="T1", scope_token=self.token)
        self.assertTrue(got["ok"])
        self.assertEqual(len(got["entries"]), 1)
        self.assertEqual(got["scope_trust"], "authenticated")

    def test_recall_with_forged_token_refused(self):
        forged = self.token[:-6] + "AAAAAA"
        got = self.store.recall(division="MEMORY", scope_token=forged)
        self.assertFalse(got["ok"])
        self.assertEqual(got["state"], "REFUSED")
        self.assertEqual(got["scope_trust"], "invalid-token")

    def test_recall_token_without_division_scope_refused(self):
        memory_only = self.auth.issue(["MEMORY"], subject="ava-merged")
        got = self.store.recall(division="GOVERNANCE",
                                scope_token=memory_only)
        self.assertFalse(got["ok"])
        self.assertEqual(got["state"], "REFUSED")
        self.assertEqual(got["scope_trust"], "authenticated")

    def test_append_existing_with_valid_token_is_authenticated(self):
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
        r = self.store.append_existing(entry, scopes=["EVIDENCE"],
                                       scope_token=self.token)
        self.assertTrue(r["ok"])
        self.assertEqual(r["scope_trust"], "authenticated")


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


class TestStrictScopes(unittest.TestCase):
    """Round 3, Finding A: AVA_REQUIRE_AUTHENTICATED_SCOPES strict mode.
    Default mode is unchanged (declared scopes accepted, reported
    declared-untrusted); strict mode refuses a missing token at the
    identity layer, and refuses to start without a verifying key."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ava_strict_test_")
        self.auth = scope_tokens.ScopeTokenAuthority(
            hmac_key=b"test-hmac-key-32-bytes-long!!")
        self.token = self.auth.issue(["MEMORY", "GOVERNANCE"],
                                     subject="ava-merged")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        os.environ.pop("AVA_REQUIRE_AUTHENTICATED_SCOPES", None)

    def test_default_mode_unchanged_no_token_accepted(self):
        store = history_store.HistoryStore(self.tmp)
        self.assertFalse(store.require_authenticated_scopes)
        r = store.append(thread_id="T1", cycle_id="C1",
                         division="GOVERNANCE", role="user",
                         text="no token, default mode",
                         scopes=["GOVERNANCE"])
        self.assertTrue(r["ok"])
        self.assertEqual(r["scope_trust"], "declared-untrusted")

    def test_strict_mode_refuses_missing_token_on_append(self):
        store = history_store.HistoryStore(
            self.tmp, scope_authority=self.auth,
            require_authenticated_scopes=True)
        r = store.append(thread_id="T1", cycle_id="C1",
                         division="GOVERNANCE", role="user",
                         text="no token, strict mode",
                         scopes=["GOVERNANCE"])
        self.assertFalse(r["ok"])
        self.assertEqual(r["state"], "QUARANTINED")
        self.assertEqual(r["failed_layer"], "identity")
        self.assertEqual(r["scope_trust"], "missing-token")
        self.assertIn("AVA_REQUIRE_AUTHENTICATED_SCOPES", r["error"])
        self.assertEqual(store.verify_chain()["entries"], 0)

    def test_strict_mode_refuses_missing_token_on_recall(self):
        store = history_store.HistoryStore(
            self.tmp, scope_authority=self.auth,
            require_authenticated_scopes=True)
        got = store.recall(division="MEMORY", scopes=["MEMORY"])
        self.assertFalse(got["ok"])
        self.assertEqual(got["state"], "REFUSED")
        self.assertEqual(got["scope_trust"], "missing-token")

    def test_strict_mode_accepts_valid_token(self):
        store = history_store.HistoryStore(
            self.tmp, scope_authority=self.auth,
            require_authenticated_scopes=True)
        r = store.append(thread_id="T1", cycle_id="C1",
                         division="MEMORY", role="user", text="one",
                         scopes=["EVIDENCE"], scope_token=self.token)
        self.assertTrue(r["ok"])
        self.assertEqual(r["scope_trust"], "authenticated")
        got = store.recall(thread_id="T1", scope_token=self.token)
        self.assertTrue(got["ok"])
        self.assertEqual(got["scope_trust"], "authenticated")

    def test_strict_mode_refuses_invalid_token(self):
        store = history_store.HistoryStore(
            self.tmp, scope_authority=self.auth,
            require_authenticated_scopes=True)
        forged = self.token[:-6] + "AAAAAA"
        r = store.append(thread_id="T1", cycle_id="C1",
                         division="MEMORY", role="user", text="one",
                         scopes=["MEMORY"], scope_token=forged)
        self.assertFalse(r["ok"])
        self.assertEqual(r["failed_layer"], "identity")
        self.assertEqual(r["scope_trust"], "invalid-token")

    def test_strict_mode_from_env_var(self):
        with mock.patch.dict(os.environ,
                             {"AVA_REQUIRE_AUTHENTICATED_SCOPES": "true"}):
            store = history_store.HistoryStore(
                self.tmp, scope_authority=self.auth)
        self.assertTrue(store.require_authenticated_scopes)
        r = store.append(thread_id="T1", cycle_id="C1",
                         division="MEMORY", role="user", text="one",
                         scopes=["MEMORY"])
        self.assertFalse(r["ok"])
        self.assertEqual(r["scope_trust"], "missing-token")

    def test_strict_mode_env_false_means_default(self):
        with mock.patch.dict(os.environ,
                             {"AVA_REQUIRE_AUTHENTICATED_SCOPES": "false"}):
            store = history_store.HistoryStore(
                self.tmp, scope_authority=self.auth)
        self.assertFalse(store.require_authenticated_scopes)

    def test_strict_mode_without_key_refuses_to_start(self):
        # No key anywhere in the environment: constructing a strict
        # store must fail VISIBLY instead of running unauthenticated.
        with mock.patch.dict(os.environ,
                             {"AVA_REQUIRE_AUTHENTICATED_SCOPES": "true"},
                             clear=True):
            with self.assertRaises(scope_tokens.ScopeTokenError):
                history_store.HistoryStore(self.tmp)

    def test_strict_mode_starts_when_key_provisioned_via_env(self):
        env = {"AVA_REQUIRE_AUTHENTICATED_SCOPES": "true",
               "AVA_SCOPE_HMAC_KEY": "test-hmac-key-32-bytes-long!!"}
        with mock.patch.dict(os.environ, env, clear=True):
            store = history_store.HistoryStore(self.tmp)
        self.assertTrue(store.require_authenticated_scopes)

    def test_strict_mode_token_without_verifying_key_is_visible(self):
        # resolve_scopes directly: strict mode, a token presented, but
        # no verifying key configured anywhere.
        with mock.patch.dict(os.environ,
                             {"AVA_REQUIRE_AUTHENTICATED_SCOPES": "true"},
                             clear=True):
            scopes, trust, refusal = scope_tokens.resolve_scopes(
                ["MEMORY"], self.token, require_authenticated=True)
        self.assertIsNone(scopes)
        self.assertEqual(trust, "no-verifying-key")
        self.assertIsNotNone(refusal)
        self.assertIn("no scope verifying key", refusal["error"])


class TestExpiryBoundary(unittest.TestCase):
    """Round 3: a token is expired AT exp (now >= exp)."""

    def setUp(self):
        self.auth = scope_tokens.ScopeTokenAuthority(
            hmac_key=b"test-hmac-key-32-bytes-long!!")

    def test_token_expired_at_exp(self):
        token = self.auth.issue(["MEMORY"], subject="ava-merged",
                                ttl_seconds=60)
        real_now = time.time()
        with mock.patch.object(scope_tokens.time, "time",
                               lambda: real_now + 60):
            report = self.auth.verify(token)
        self.assertFalse(report["ok"])
        self.assertEqual(report["error"], "token expired")

    def test_token_valid_one_second_before_exp(self):
        token = self.auth.issue(["MEMORY"], subject="ava-merged",
                                ttl_seconds=60)
        real_now = time.time()
        with mock.patch.object(scope_tokens.time, "time",
                               lambda: real_now + 59):
            report = self.auth.verify(token)
        self.assertTrue(report["ok"])


class TestStrictBase64url(unittest.TestCase):
    """Round 3: base64url decoding is STRICT — alphabet only, no
    padding, canonical re-encoding."""

    def test_rejects_characters_outside_alphabet(self):
        for bad in ("AB*CD", "AB+CD", "AB/CD", "ab cd", "AB=C", "A"):
            with self.assertRaises(ValueError, msg=bad):
                scope_tokens._b64url_d(bad)

    def test_rejects_padding_and_noncanonical_bits(self):
        for bad in ("QQ==", "QR==", "QS==", "QQ"):
            # "QQ" decodes to b"A" but re-encodes as "QQ" — canonical,
            # so it is accepted; the padded / non-canonical forms are not.
            if bad == "QQ":
                self.assertEqual(scope_tokens._b64url_d(bad), b"A")
            else:
                with self.assertRaises(ValueError, msg=bad):
                    scope_tokens._b64url_d(bad)

    def test_canonical_round_trip_still_works(self):
        self.assertEqual(
            scope_tokens._b64url_d(scope_tokens._b64url_e(b"\x00\xff\x10")),
            b"\x00\xff\x10")

    def test_token_with_padded_or_bad_segment_refused(self):
        auth = scope_tokens.ScopeTokenAuthority(
            hmac_key=b"test-hmac-key-32-bytes-long!!")
        token = auth.issue(["MEMORY"], subject="ava-merged")
        prefix, body, sig = token.split(".")
        for bad in (prefix + "." + body + "==" + "." + sig,
                    prefix + "." + body + "." + sig[:-2] + "*A"):
            report = auth.verify(bad)
            self.assertFalse(report["ok"], bad)
            self.assertEqual(report["error"], "malformed token")


class TestMultiProcessLocking(unittest.TestCase):
    """Round 3, Finding C: two processes racing an append. The gate
    is deliberately slowed in the worker so both processes are inside
    verify+gate at once — without a cross-process lock both pass the
    gate on the same head and fork the chain. With the lock, exactly
    one successor wins and the loser fails closed."""

    WORKER = (
        "import sys, json, time, os\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from services_stdlib import history_store\n"
        "s = history_store.HistoryStore(sys.argv[2])\n"
        "_real_gate = history_store.HistoryStore.gate\n"
        "def _slow_gate(self, entry, scopes):\n"
        "    ok, layer = _real_gate(self, entry, scopes)\n"
        "    time.sleep(0.3)\n"
        "    return ok, layer\n"
        "history_store.HistoryStore.gate = _slow_gate\n"
        "open(sys.argv[4], 'a').close()\n"
        "while not os.path.exists(sys.argv[5]):\n"
        "    time.sleep(0.005)\n"
        "r = s.append(thread_id='T', cycle_id='C' + sys.argv[3],\n"
        "             division='MEMORY', role='user',\n"
        "             text='racer ' + sys.argv[3], scopes=['MEMORY'])\n"
        "print(json.dumps({'ok': r['ok'], 'state': r.get('state'),\n"
        "                  'failed_layer': r.get('failed_layer')}))\n"
    )

    def _race(self, extra_env=None):
        tmp = tempfile.mkdtemp(prefix="ava_race_test_")
        worker = os.path.join(tmp, "racer.py")
        with open(worker, "w") as f:
            f.write(self.WORKER)
        repo = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                            ".."))
        go = os.path.join(tmp, "go")
        env = dict(os.environ)
        if extra_env:
            env.update(extra_env)
        procs = []
        for n in ("1", "2"):
            ready = os.path.join(tmp, "ready" + n)
            procs.append(subprocess.Popen(
                [sys.executable, worker, repo, tmp, n, ready, go],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, env=env))
        try:
            deadline = time.time() + 30
            while not (os.path.exists(os.path.join(tmp, "ready1"))
                       and os.path.exists(os.path.join(tmp, "ready2"))):
                if time.time() > deadline:
                    raise AssertionError("racers did not become ready")
                time.sleep(0.005)
            open(go, "w").close()
            results = []
            for p in procs:
                out, err = p.communicate(timeout=30)
                self.assertEqual(p.returncode, 0, err)
                results.append(json.loads(out.strip()))
            self.assertEqual(sorted(r["ok"] for r in results),
                             [False, True])
            loser = [r for r in results if not r["ok"]][0]
            self.assertEqual(loser["state"], "QUARANTINED")
            self.assertEqual(loser["failed_layer"], "crypto")
            v = history_store.HistoryStore(tmp).verify_chain()
            self.assertTrue(v["ok"], v)
            self.assertEqual(v["entries"], 1)
        finally:
            for p in procs:
                if p.poll() is None:
                    p.kill()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_two_processes_racing_append_one_wins(self):
        self._race()

    def test_two_processes_racing_append_one_wins_fallback_lock(self):
        # Same race with the O_EXCL lockfile fallback forced on.
        self._race({"AVA_HISTORY_LOCK_FORCE_FALLBACK": "1"})

    def test_recall_never_sees_a_torn_write(self):
        # A writer appending in a loop while this process recalls in
        # a loop: every recall must return complete, parseable entries
        # (the shared lock keeps recall out of the writer's section).
        tmp = tempfile.mkdtemp(prefix="ava_race_recall_test_")
        worker = os.path.join(tmp, "writer.py")
        with open(worker, "w") as f:
            f.write(
                "import sys, time\n"
                "sys.path.insert(0, sys.argv[1])\n"
                "from services_stdlib import history_store\n"
                "s = history_store.HistoryStore(sys.argv[2])\n"
                "for i in range(15):\n"
                "    s.append(thread_id='T', cycle_id='C%d' % i,\n"
                "             division='MEMORY', role='user',\n"
                "             text='entry %d' % i, scopes=['MEMORY'])\n"
                "    time.sleep(0.01)\n")
        repo = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                            ".."))
        proc = subprocess.Popen([sys.executable, worker, repo, tmp],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        try:
            store = history_store.HistoryStore(tmp)
            for _ in range(30):
                got = store.recall(scopes=["MEMORY"])
                self.assertTrue(got["ok"], got)
                for e in got["entries"]:
                    self.assertIsInstance(e, dict)
                    self.assertIn("entry_hash", e)
                time.sleep(0.01)
            _, err = proc.communicate(timeout=30)
            self.assertEqual(proc.returncode, 0, err)
            self.assertTrue(history_store.HistoryStore(tmp)
                            .verify_chain()["ok"])
        finally:
            if proc.poll() is None:
                proc.kill()
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
