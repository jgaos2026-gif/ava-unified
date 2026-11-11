import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brick import Brick
from ledger import LedgerError
from money import MoneyError


def setup(key=None):
    br = Brick(key=key)
    a = br.add_artist("A", "music", rate_floor_cents=1000)
    b = br.offer(a.artist_id, "Venue", "Gig", 100000, "2026-12-01")
    return br, a, b


def confirm(b):
    b.to_draft().approve(b.artist).confirm()


class TestLedger(unittest.TestCase):
    def test_gig_pay_needs_confirmed_booking(self):
        br, a, b = setup()
        with self.assertRaises(LedgerError):
            br.record_cleared("tx1", 50000, "gig-pay-cleared")          # no booking
        with self.assertRaises(LedgerError):
            br.record_cleared("tx1", 50000, "gig-pay-cleared", b.id)    # OFFER
        confirm(b)
        e = br.record_cleared("tx1", 50000, "gig-pay-cleared", b.id)
        self.assertEqual(sum(e["receipts"][0]["split"].values()), 50000)

    def test_gig_pay_cannot_exceed_rate_cumulatively(self):
        br, a, b = setup(); confirm(b)
        br.record_cleared("tx1", 60000, "gig-pay-cleared", b.id)
        with self.assertRaises(LedgerError):
            br.record_cleared("tx2", 40001, "gig-pay-cleared", b.id)
        br.record_cleared("tx2", 40000, "gig-pay-cleared", b.id)

    def test_duplicate_external_ref_refused(self):
        br, a, b = setup()
        br.record_cleared("tx1", 100, "merch-cleared")
        with self.assertRaises(LedgerError):
            br.record_cleared("tx1", 100, "merch-cleared")
        for bad in ("", "  ", None):
            with self.assertRaises(LedgerError):
                br.record_cleared(bad, 100, "merch-cleared")

    def test_unknown_booking_and_bad_stage(self):
        br, a, b = setup()
        with self.assertRaises(LedgerError):
            br.record_cleared("t", 100, "merch-cleared", "book-999")
        with self.assertRaises(MoneyError):
            br.record_cleared("t", 100, "promised")

    def test_chained_cuts_cannot_be_replayed(self):
        # The old caveat: a stale receipt could be cut twice. Via the ledger the
        # caller never holds receipts; V8 can only be drawn down once overall.
        br, a, b = setup()
        e = br.record_cleared("t", 100000, "merch-cleared")
        br.pay_cut(e["id"], 15000, "Manager")
        with self.assertRaises(MoneyError):
            br.pay_cut(e["id"], 5001, "Feature")   # only 5000 left in V8
        br.pay_cut(e["id"], 5000, "Feature")
        self.assertEqual(br.ledger.head(e["id"])["split"]["V8"], 0)
        self.assertEqual(len(e["receipts"]), 3)

    def test_totals_identity(self):
        br, a, b = setup(); confirm(b)
        e1 = br.record_cleared("t1", 77777, "gig-pay-cleared", b.id)
        e2 = br.record_cleared("t2", 12345, "merch-cleared")
        br.pay_cut(e1["id"], 1000, "M")
        t = br.ledger.vault_totals()
        self.assertEqual(t["gross_cents"], 77777 + 12345)
        self.assertEqual(sum(t["vaults"].values()) + t["collaborator_cuts_cents"], t["gross_cents"])

    def test_summary(self):
        br, a, b = setup(); confirm(b)
        br.add_release("S", "A")
        br.expenses.add("travel", 500)
        s = br.summary()
        self.assertEqual(s["bookings_by_state"], {"CONFIRMED": 1})
        self.assertEqual(s["expenses_by_category_cents"]["travel"], 500)
        self.assertEqual(s["releases_distributor_ready"], 0)


if __name__ == "__main__":
    unittest.main()
