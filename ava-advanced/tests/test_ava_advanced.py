import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ava_advanced as adv

class AdvancedTests(unittest.TestCase):
    def test_screen_blocks_tool_payload_and_null_byte(self):
        self.assertTrue(adv.screen('{"tool_call": {"name": "x"}}')["blocked"])
        self.assertTrue(adv.screen("a\x00b")["blocked"])
        self.assertFalse(adv.screen("Execute calculator for 250 * 4")["blocked"])

    def test_presets_all_match_expected(self):
        p = adv.presets()
        self.assertEqual(len(p), 5)
        for prof in p.values():
            for v in prof["vectors"]:
                self.assertTrue(v["matches_expected"], (prof["name"], v["label"]))
                if v["kind"] == "attack":
                    self.assertTrue(v["screen_blocked"])
                else:
                    self.assertFalse(v["screen_blocked"])

    def test_govern_and_decide(self):
        s = adv.govern("John lives in Peoria", ["john-2026-10-22"])
        self.assertEqual(s["state"], "COMMIT")
        d = adv.decide()
        self.assertEqual(d["chosen"], "proper job at site price")
        self.assertEqual(d["proof_level"], "SIMULATION")

    def test_check_moves_no_money_no_llm(self):
        c = adv.check()
        self.assertFalse(c["money_moved"])
        self.assertFalse(c["llm_connected"])
        self.assertTrue(c["presets_all_match_expected"])

if __name__ == "__main__":
    unittest.main()
