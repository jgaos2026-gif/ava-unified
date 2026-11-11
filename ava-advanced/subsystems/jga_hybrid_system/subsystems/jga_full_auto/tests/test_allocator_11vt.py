"""Tests for the 11VT receipt-only allocator and its invoice wiring."""
import unittest

from jga_auto.allocator_11vt import allocate_cleared_payment, VAULT_TARGETS
from jga_auto.books import build_invoice
from jga_auto.pipeline import Job


class TestAllocator11VT(unittest.TestCase):
    def test_5750_example_balances(self):
        r = allocate_cleared_payment(575000, "DEPOSIT_CLEARED_35", "JOB-TEST")
        self.assertTrue(r["balanced"])
        self.assertEqual(r["banking_execution"], "NONE_LEDGER_RECEIPT_ONLY")
        self.assertEqual(r["tax_disclaimer"],
                         "INTERNAL_RESERVE_TARGETS_NOT_STATUTORY_TAX_LIABILITY")
        self.assertEqual(r["v7_plug_notice"], "ABSORBS_PENNY_ROUNDING_DELTAS")
        self.assertEqual(r["vaults"]["V1_FED_TAX_RESERVE"]["amount_cents"], 86250)
        self.assertEqual(r["vaults"]["V8_OWNER_W2_RESERVE"]["amount_cents"], 115000)
        self.assertEqual(r["vaults"]["V10_CAPITAL_RESERVE"]["name"],
                         "Internal Capital Reserve")
        self.assertEqual(sum(v["amount_cents"] for v in r["vaults"].values()), 575000)

    def test_rates_sum_to_one(self):
        self.assertEqual(sum(m["rate"] for m in VAULT_TARGETS.values()), 1)

    def test_odd_amount_balances_via_v7_plug(self):
        r = allocate_cleared_payment(8750, "FINAL_PAID_65", "JOB-ODD")
        self.assertTrue(r["balanced"])
        self.assertEqual(sum(v["amount_cents"] for v in r["vaults"].values()), 8750)

    def test_refuses_contract_price_stage(self):
        with self.assertRaises(ValueError):
            allocate_cleared_payment(575000, "CONTRACT_TOTAL", "JOB-X")

    def test_refuses_negative(self):
        with self.assertRaises(ValueError):
            allocate_cleared_payment(-1, "DEPOSIT_CLEARED_35", "JOB-X")


class TestInvoice11VT(unittest.TestCase):
    def _delivered_job(self):
        job = Job(customer="Test Co", package="Quick Creative Help", brief="x")
        job.scope()  # $75, deposit $26 (35% integer)
        job.mark_deposit_cleared()
        job.submit_draft("draft")
        job.client_decision(True)
        job.mark_final_paid()
        job.deliver_clean_files()
        return job

    def test_invoice_binds_both_cleared_splits(self):
        inv = build_invoice(self._delivered_job())
        self.assertEqual(inv.deposit_11vt_split["payment_stage"], "DEPOSIT_CLEARED_35")
        self.assertEqual(inv.final_11vt_split["payment_stage"], "FINAL_PAID_65")
        self.assertTrue(inv.deposit_11vt_split["balanced"])
        self.assertTrue(inv.final_11vt_split["balanced"])
        self.assertEqual(inv.deposit_11vt_split["banking_execution"],
                         "NONE_LEDGER_RECEIPT_ONLY")
        # Receipt hash is recomputable from the invoice payload itself.
        import hashlib
        self.assertEqual(inv.receipt_sha256,
                         hashlib.sha256(inv.receipt_payload()).hexdigest())
        # Splits sum to their cleared payments, never to the contract
        # price in a single split.
        self.assertEqual(
            sum(v["amount_cents"] for v in inv.deposit_11vt_split["vaults"].values()),
            inv.deposit_cents)
        self.assertEqual(
            sum(v["amount_cents"] for v in inv.final_11vt_split["vaults"].values()),
            inv.balance_cents)

    def test_invoice_refuses_uncleared(self):
        job = Job(customer="Test Co", package="Quick Creative Help", brief="x",
                  state="DONE", price_cents=7500)
        with self.assertRaises(ValueError):
            build_invoice(job)


if __name__ == "__main__":
    unittest.main()
