"""Reflex install tests for AVA Advanced — SIMULATION ONLY / RESEARCH ONLY.

Checks the local reflex_sim.py copy beside ava_advanced.py and its
wiring into govern()/check(). No medical claims are tested here: these
tests check simulation behaviour only (detection, isolation, safe-state
fallback, deterministic replay, reflex never certifies).
"""
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ava_advanced as adv  # noqa: E402

REF = Path(__file__).resolve().parent.parent.parent / "ava-reflex-sim" / "reflex_sim.py"


class ReflexInstallTests(unittest.TestCase):
    def test_local_copy_is_byte_identical_to_reference(self):
        local = Path(adv.__file__).parent / "reflex_sim.py"
        self.assertTrue(local.exists())
        self.assertEqual(hashlib.sha256(local.read_bytes()).hexdigest(),
                         hashlib.sha256(REF.read_bytes()).hexdigest())

    def test_frame_demo_clean_passes_corrupt_isolates(self):
        d = adv.reflex_frame_demo()
        self.assertTrue(d["simulation_only"])
        self.assertEqual(d["clean_frame"], {"decision": "PASS", "trust_state": "PENDING_VERIFICATION"})
        self.assertEqual(d["corrupted_frame"]["decision"], "ISOLATE")
        self.assertEqual(d["corrupted_frame"]["reason"], "bit_corruption")
        self.assertEqual(d["corrupted_frame"]["trust_state"], "QUARANTINED")
        self.assertTrue(d["corrupted_frame"]["safe_state_preserved"])
        self.assertTrue(d["ledger_chain_verified"])
        self.assertFalse(d["reflex_certified_anything"])
        self.assertNotEqual(d["clean_frame"]["trust_state"], "CERTIFIED")
        self.assertNotEqual(d["corrupted_frame"]["trust_state"], "CERTIFIED")

    def test_probe_is_deterministic_and_detects_all_faults(self):
        a, b = adv.reflex_probe(), adv.reflex_probe()
        self.assertEqual(a, b)
        c = a["campaign"]
        self.assertGreater(c["faults_injected"], 0)
        # Honest accounting from the reference: detected + missed ==
        # injected; a mixed campaign may miss one (here: 23/24, 1 silent
        # escape). Per-fault-type campaigns must detect every fault.
        self.assertEqual(c["faults_detected"] + c["false_negative_faults"],
                         c["faults_injected"])
        self.assertEqual(c["silent_fault_escapes"], c["false_negative_faults"])
        self.assertEqual(c["rollback_correctness"], 1.0)
        self.assertEqual(c["certified_resumes"], 0)
        self.assertFalse(c["reflex_certified_anything"])
        self.assertTrue(c["ledger_chain_verified"])
        rs = adv._load_reflex()
        for ft in rs.FAULT_TYPES:
            rep = rs.run_campaign(ft, seed=7, fault_types=[ft], path="reflex")
            self.assertEqual(rep["faults_detected"], rep["faults_injected"], ft)
            self.assertEqual(rep["silent_fault_escapes"], 0, ft)

    def test_govern_carries_reflex_demo_without_certifying(self):
        s = adv.govern("John lives in Peoria", ["john-2026-10-22"])
        self.assertEqual(s["state"], "COMMIT")
        d = s["reflex_simulation"]
        self.assertTrue(d["simulation_only"])
        self.assertEqual(d["corrupted_frame"]["decision"], "ISOLATE")
        self.assertFalse(d["reflex_certified_anything"])

    def test_check_carries_full_reflex_probe(self):
        c = adv.check()
        self.assertTrue(c["presets_all_match_expected"])
        probe = c["reflex_simulation"]
        self.assertTrue(probe["simulation_only"])
        self.assertTrue(probe["research_only"])
        self.assertFalse(probe["reflex_certified_anything"])
        self.assertEqual(probe["campaign"]["faults_detected"]
                         + probe["campaign"]["false_negative_faults"],
                         probe["campaign"]["faults_injected"])
        self.assertFalse(c["money_moved"])
        self.assertFalse(c["llm_connected"])

    def test_reflex_does_not_duplicate_screen(self):
        # screen() is still the only input screen; a tool-shaped payload
        # is blocked by screen() with no reflex involvement.
        s = adv.screen('{"tool_call": {"name": "x"}}')
        self.assertTrue(s["blocked"])
        self.assertNotIn("reflex_simulation", s)
        self.assertFalse(adv.screen("Execute calculator for 250 * 4")["blocked"])

    def test_no_medical_claims_in_reflex_output(self):
        import json
        text = json.dumps(adv.reflex_probe(), default=str).lower()
        for claim in ("prevents seizures", "prevents seizure", "heals tissue",
                      "heal tissue", "clinical safety", "implant compatibility"):
            self.assertNotIn(claim, text)


if __name__ == "__main__":
    unittest.main()
