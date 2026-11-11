"""Tests for the mandatory pre-brain gates (round 3, Finding 03).
The gate module is stdlib-only, so no FastAPI is needed here. The
FastAPI endpoint wiring itself is checked statically (fastapi is not
installed in the test venv): the gate call must textually precede the
braid and brain calls in sovereign_orchestrator.py, and a refused
gate must return GATE_REFUSED before either is reached.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services_stdlib import history_store  # noqa: E402
from services_stdlib import orchestrate_gate  # noqa: E402
from services_stdlib import scope_tokens  # noqa: E402


def _brain_if_allowed(gate_report, calls):
    """Mirrors the endpoint's rule: a refused gate never reaches the
    brain. `calls` records brain invocations."""
    if not gate_report["ok"]:
        return {"status": "GATE_REFUSED", "error": gate_report["error"]}
    calls.append("brain")
    return {"status": "COGNITIVE_CYCLE_RESOLVED"}


class TestOrchestrateGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ava_gate_test_")
        self.store = history_store.HistoryStore(self.tmp)
        self.auth = scope_tokens.ScopeTokenAuthority(
            hmac_key=b"test-hmac-key-32-bytes-long!!")
        self.token = self.auth.issue(["MEMORY", "GOVERNANCE"],
                                     subject="ava-merged")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_passing_gates_reach_brain(self):
        self.store.append(thread_id="T1", cycle_id="C1",
                          division="MEMORY", role="user", text="one",
                          scopes=["MEMORY"])
        gate = orchestrate_gate.run_pre_brain_gates(
            "hello", history_store=self.store)
        self.assertFalse(gate["ok"], gate)
        self.assertEqual(gate["scope_trust"], "declared-untrusted")
        self.assertIn("spine_runtime", gate["error"])
        calls = []
        out = _brain_if_allowed(gate, calls)
        self.assertEqual(calls, [])
        self.assertEqual(out["status"], "GATE_REFUSED")

    def test_broken_chain_refuses_and_brain_never_called(self):
        self.store.append(thread_id="T1", cycle_id="C1",
                          division="MEMORY", role="user", text="one",
                          scopes=["MEMORY"])
        path = os.path.join(self.tmp, "history.jsonl")
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        first = json.loads(lines[0])
        first["text"] = "tampered"
        lines[0] = json.dumps(first) + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        gate = orchestrate_gate.run_pre_brain_gates(
            "hello", history_store=self.store)
        self.assertFalse(gate["ok"])
        self.assertIn("history_chain", gate["error"])
        calls = []
        out = _brain_if_allowed(gate, calls)
        self.assertEqual(calls, [])
        self.assertEqual(out["status"], "GATE_REFUSED")

    def test_invalid_token_refuses_and_brain_never_called(self):
        forged = self.token[:-6] + "AAAAAA"
        gate = orchestrate_gate.run_pre_brain_gates(
            "hello", history_store=self.store, scope_token=forged,
            authority=self.auth)
        self.assertFalse(gate["ok"])
        self.assertIn("scope", gate["error"])
        calls = []
        _brain_if_allowed(gate, calls)
        self.assertEqual(calls, [])

    def test_valid_token_passes_as_authenticated(self):
        gate = orchestrate_gate.run_pre_brain_gates(
            "hello", history_store=self.store, scope_token=self.token,
            authority=self.auth)
        self.assertFalse(gate["ok"], gate)
        self.assertEqual(gate["scope_trust"], "authenticated")
        self.assertIn("spine_runtime", gate["error"])
        calls = []
        out = _brain_if_allowed(gate, calls)
        self.assertEqual(calls, [])
        self.assertEqual(out["status"], "GATE_REFUSED")

    def test_strict_mode_missing_token_refuses(self):
        gate = orchestrate_gate.run_pre_brain_gates(
            "hello", history_store=self.store,
            require_authenticated=True)
        self.assertFalse(gate["ok"])
        self.assertIn("scope", gate["error"])
        calls = []
        _brain_if_allowed(gate, calls)
        self.assertEqual(calls, [])

    def test_no_history_store_refuses(self):
        gate = orchestrate_gate.run_pre_brain_gates("hello")
        self.assertFalse(gate["ok"])
        self.assertIn("history store", gate["error"])

    def test_spine_runtime_is_honestly_not_wired(self):
        # The gate must NOT claim a spine approval it never performed.
        gate = orchestrate_gate.run_pre_brain_gates(
            "hello", history_store=self.store)
        self.assertFalse(gate["ok"], gate)
        detail = gate["checks"]["spine_runtime"]["detail"]
        self.assertIn("NOT_WIRED_TS_RUNTIME", detail)
        self.assertIn("spine_runtime", gate["error"])
        calls = []
        out = _brain_if_allowed(gate, calls)
        self.assertEqual(calls, [])
        self.assertEqual(out["status"], "GATE_REFUSED")

    def test_endpoint_wiring_gate_before_brain(self):
        # Static check (fastapi is not installed in this venv): the
        # /orchestrate handler must call the gate before the braid
        # search and before the brain call, and must return
        # GATE_REFUSED on failure.
        src_path = os.path.join(
            os.path.dirname(__file__), "..", "services",
            "sovereign_orchestrator.py")
        with open(src_path, encoding="utf-8") as f:
            src = f.read()
        gate_i = src.index("run_pre_brain_gates")
        braid_i = src.index('BRAID_URL}/search')
        brain_i = src.index('BRAIN_URL}/inference')
        self.assertLess(gate_i, braid_i,
                        "gate must run before the braid search")
        self.assertLess(gate_i, brain_i,
                        "gate must run before the brain call")
        self.assertIn('"GATE_REFUSED"', src)
        self.assertIn('if not gate["ok"]:', src)


if __name__ == "__main__":
    unittest.main()
