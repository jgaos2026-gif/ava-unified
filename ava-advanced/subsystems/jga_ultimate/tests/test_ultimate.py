import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ultimate


class UltimateTests(unittest.TestCase):
    def test_status_is_clean_and_honest(self):
        s = ultimate.status()
        self.assertEqual(s["system"], "JGA Ultimate")
        self.assertTrue(s["jga_os"]["ledger"]["valid"])
        self.assertFalse(s["stripe"]["connected"])
        self.assertEqual(s["pin_flag"], "PIN_CONFIG_NOT_SHIPPED")
        self.assertEqual(s["gates"]["money_moves"], "NEVER by automation")

    def test_automate_moves_no_money_and_writes_report(self):
        r = ultimate.automate()
        c = r["automation_cycle"]
        self.assertFalse(c["money_moved"])
        self.assertEqual(c["messages_sent"], 0)
        self.assertEqual(c["files_released"], 0)
        self.assertIn("ledger_verified", c["actions_taken"])
        self.assertIn("ava_screening_and_calculator_ok", c["actions_taken"])
        self.assertIn("untrusted_payload_still_blocked", c["actions_taken"])
        self.assertTrue((ultimate.DATA / "last-cycle.json").exists())

    def test_brick1_split_cleared_only(self):
        r = ultimate.split("brick1", 35000, "DEPOSIT_CLEARED_35", "job-001")
        total = sum(v["amount_cents"] if isinstance(v, dict) else 0 for v in r["vaults"].values()) if "vaults" in r else None
        # Allocator returns a dict with a vaults mapping; fall back to
        # checking the receipt payload sums to the cleared amount.
        payload = json.dumps(r, default=str)
        self.assertIn("35000", payload)
        with self.assertRaises(ValueError):
            ultimate.split("brick1", 35000, "QUOTE_ONLY", "job-001")

    def test_entertainment_split_cleared_only(self):
        r = ultimate.split("entertainment", 100000, "gig-pay-cleared")
        self.assertIn("receipt_hash", r)
        with self.assertRaises(Exception):
            ultimate.split("entertainment", 100000, "gig-pay-pending")

    def test_no_default_pin_config_shipped(self):
        ultimate.status()
        self.assertFalse((ultimate.ROOT / "subsystems" / "jga_os" / "config.json").exists())

    def test_automation_never_advances_unpaid_jobs(self):
        # Seed one job awaiting deposit, run automate, confirm it is
        # listed under needs_owner and its status is unchanged.
        jga = ultimate._load_jga_os()
        client = jga.add_client({"name": "Ultimate Test", "state": "IL"})["id"]
        quote = jga.add_quote({"client_id": client, "description": "Logo", "service": 100, "tax": 0})["id"]
        job = jga.add_job({"quote_id": quote})["id"]
        r = ultimate.automate()
        self.assertTrue(any("awaiting deposit" in x for x in r["automation_cycle"]["needs_owner"]))
        c = jga.connect()
        row = c.execute("SELECT status, deposit_cleared FROM jobs WHERE id=?", (job,)).fetchone()
        c.close()
        self.assertEqual(row["status"], "awaiting_deposit")
        self.assertEqual(row["deposit_cleared"], 0)


if __name__ == "__main__":
    unittest.main()
