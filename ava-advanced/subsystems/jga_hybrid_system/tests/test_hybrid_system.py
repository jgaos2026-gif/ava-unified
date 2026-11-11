import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import hybrid


class HybridSystemTests(unittest.TestCase):
    def test_sourced_claim_commits_unsourced_does_not(self):
        s = hybrid.govern("John lives in Peoria", ["john-2026-10-22"])
        self.assertEqual(s["state"], "COMMIT")
        u = hybrid.govern("John won the lottery", [])
        self.assertNotEqual(u["state"], "COMMIT")

    def test_gateway_defers_all_six(self):
        c = hybrid.check()
        for label, r in c["gateway_deferrals"].items():
            self.assertFalse(r["allowed"], label)

    def test_decision_chooses_proper_job_and_is_simulation(self):
        d = hybrid.decide_demo()
        self.assertEqual(d["chosen"], "proper job at site price")
        self.assertEqual(d["proof_level"], "SIMULATION")

    def test_micro_spine_selftest_and_money_balanced(self):
        c = hybrid.check()
        self.assertTrue(c["micro_spine_selftest"])
        self.assertTrue(c["brick1_split_balanced"])
        self.assertFalse(c["money_moved"])
        self.assertFalse(c["llm_connected"])

    def test_no_goal_means_defer(self):
        sys.path.insert(0, str(hybrid.SUB))
        from ava_hybrid import DecisionEngine
        eng = DecisionEngine()
        d = eng.decide(None, [])
        self.assertEqual(d.status, "DEFERRED")


if __name__ == "__main__":
    unittest.main()
