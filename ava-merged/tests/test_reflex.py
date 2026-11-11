"""Tests for the installed minimal reflex simulator in ava-merged.

Simulation-only / research-only. Stdlib unittest, no live mesh needed.
The core is loaded from a COPY in a temp dir (same pattern as
test_history_room.py) so no real AVA_ORGANISM data is touched.
"""
import importlib.util
import json
import os
import random
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services_stdlib import reflex as reflex_mod  # noqa: E402
from services_stdlib import history_store  # noqa: E402


class TestInstalledReflexCopy(unittest.TestCase):
    def test_canonical_metrics_deterministic(self):
        a = reflex_mod.canonical_metrics_json(
            reflex_mod.run_campaign("merged-check", 7))
        b = reflex_mod.canonical_metrics_json(
            reflex_mod.run_campaign("merged-check", 7))
        self.assertEqual(a, b)

    def test_kernel_isolates_bit_corruption_and_never_certifies(self):
        kernel = reflex_mod.ReflexKernel(
            {"command": "HOLD_SAFE", "seq": -1, "mode": "SAFE_STATE"})
        frames = reflex_mod.generate_clean_frames(10, 3)
        bad, _ = reflex_mod.inject_bit_corruption(frames, 5)
        rng = random.Random(1)
        outcomes = [kernel.process_frame(f, rng) for f in bad]
        self.assertTrue(any(o.decision == "ISOLATE" for o in outcomes))
        self.assertTrue(all(o.trust_state != "CERTIFIED" for o in outcomes))
        self.assertTrue(all(o.safe_state == {"command": "HOLD_SAFE", "seq": -1,
                                             "mode": "SAFE_STATE"}
                            for o in outcomes if o.decision == "ISOLATE"))


def _load_core_copy(tmp):
    """Copy local_organism_core.py + reflex.py + history_store.py into
    tmp and load the core from there, with tmp on sys.path so its flat
    `import reflex` / `import history_store` resolve to the copies."""
    for name in ("local_organism_core.py", "reflex.py", "history_store.py"):
        shutil.copy(os.path.join(os.path.dirname(__file__), "..",
                                 "services_stdlib", name),
                    os.path.join(tmp, name))
    sys.path.insert(0, tmp)
    try:
        spec = importlib.util.spec_from_file_location(
            "organism_reflex_under_test",
            os.path.join(tmp, "local_organism_core.py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["organism_reflex_under_test"] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(tmp)


class TestReflexScreen(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ava_reflex_test_")
        self.mod = _load_core_copy(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_reflex_module_loaded(self):
        self.assertIsNotNone(self.mod._reflex_mod)

    def test_clean_stream_passes_pending_verification(self):
        screen = self.mod.reflex_screen("hello ava", None)
        self.assertTrue(screen["available"])
        self.assertFalse(screen["tripped"])
        self.assertEqual(screen["trust_state"], "PENDING_VERIFICATION")
        self.assertFalse(screen["certified"])
        self.assertTrue(screen["simulation_only"])
        self.assertTrue(screen["ledger_chain_verified"])

    def test_injected_fault_trips_and_quarantines(self):
        screen = self.mod.reflex_screen("hello ava", ["bit_corruption"])
        self.assertTrue(screen["tripped"])
        self.assertEqual(screen["reason"], "bit_corruption")
        self.assertEqual(screen["trust_state"], "QUARANTINED")
        self.assertFalse(screen["certified"])
        self.assertEqual(screen["safe_state"],
                         {"command": "HOLD_SAFE", "seq": -1,
                          "mode": "SAFE_STATE"})

    def test_screen_is_deterministic(self):
        a = self.mod.reflex_screen("same message", ["duplicate_frames"])
        b = self.mod.reflex_screen("same message", ["duplicate_frames"])
        self.assertEqual(a, b)

    def test_unknown_fault_names_are_ignored(self):
        screen = self.mod.reflex_screen("hello ava", ["not_a_fault"])
        self.assertFalse(screen["tripped"])

    def test_escalation_goes_through_history_gate(self):
        screen = self.mod.reflex_screen("hello ava", ["bit_corruption"])
        self.assertTrue(screen["tripped"])
        result = self.mod.escalate_reflex("AVA-TEST-1", screen)
        self.assertTrue(result["history_escalation"]["ok"])
        recalled = self.mod.HISTORY.recall(
            division="GOVERNANCE", scopes=["GOVERNANCE"], limit=10)
        self.assertTrue(recalled["ok"])
        self.assertTrue(any("reflex escalation" in e["text"].lower()
                            for e in recalled["entries"]))


class TestHistoryReflexEscalation(unittest.TestCase):
    def test_record_reflex_escalation_stores_via_gate(self):
        tmp = tempfile.mkdtemp(prefix="ava_reflex_hist_")
        try:
            store = history_store.HistoryStore(tmp)
            result = store.record_reflex_escalation(
                cycle_id="AVA-TEST-2", reason="bit_corruption",
                fault_type="bit_corruption", seq=4, fault_id="bit_corruption-1-0")
            self.assertTrue(result["ok"])
            self.assertEqual(result["division"], "GOVERNANCE")
            recalled = store.recall(division="GOVERNANCE",
                                    scopes=["GOVERNANCE"], limit=10)
            self.assertTrue(any(e["entry_id"] == result["entry_id"]
                                for e in recalled["entries"]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestChatReflexEndToEnd(unittest.TestCase):
    """POST /chat against a throwaway server on the temp-dir core copy:
    the reflex must trip model-free, before any model call, and a clean
    request must still reach the (model-missing) 503 with the reflex
    block showing it ran and passed."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ava_reflex_http_")
        self.mod = _load_core_copy(self.tmp)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self.mod.Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _post(self, path, payload):
        req = urllib.request.Request(
            "http://127.0.0.1:%d%s" % (self.port, path),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_fault_injection_trips_before_model(self):
        status, body = self._post("/chat", {
            "message": "hello ava",
            "reflex_faults": ["bit_corruption"]})
        self.assertEqual(status, 422, body)
        self.assertTrue(body["reflex"]["tripped"])
        self.assertEqual(body["trust_state"], "QUARANTINED")
        self.assertFalse(body["certified"])
        self.assertIn("No model was called", body["reply"])
        # Escalation reached the history store via the gate.
        recalled = self.mod.HISTORY.recall(
            division="GOVERNANCE", scopes=["GOVERNANCE"], limit=10)
        self.assertTrue(any("reflex escalation" in e["text"].lower()
                            for e in recalled["entries"]))

    def test_clean_request_reaches_model_missing_503_with_reflex_block(self):
        status, body = self._post("/chat", {"message": "hello ava"})
        self.assertEqual(status, 503, body)
        self.assertEqual(body["error"], "LOCAL_MODEL_UNRESOLVED")
        self.assertIn("reflex", body)
        self.assertFalse(body["reflex"]["tripped"])
        self.assertEqual(body["reflex"]["trust_state"], "PENDING_VERIFICATION")


if __name__ == "__main__":
    unittest.main()
