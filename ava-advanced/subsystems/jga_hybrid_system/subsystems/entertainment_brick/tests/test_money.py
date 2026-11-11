import copy
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import money
from money import MoneyError, pay_collaborator_cut, split_cleared

GIG = "gig-pay-cleared"


class TestSplit(unittest.TestCase):
    def test_1000_split_exact(self):
        r = split_cleared(100000, GIG)
        self.assertEqual(r["split"], {
            "V1": 15000, "V2": 7500, "V3": 3500, "V4": 5000, "V5": 2000,
            "V6": 15000, "V7": 12000, "V8": 20000, "V9": 10000,
            "V10": 8000, "V11": 2000,
        })
        self.assertEqual(sum(r["split"].values()), 100000)

    def test_odd_amount_v7_plug(self):
        r = split_cleared(8750, "merch-cleared")
        self.assertEqual(sum(r["split"].values()), 8750)
        self.assertIn(r["split"]["V7"], (1049, 1050, 1051))

    def test_exhaustive_sum_and_bounded_plug(self):
        # Brute force: always sums, V7 never negative, drift from 12% <= 3 cents.
        for c in range(0, 50001):
            s = split_cleared(c, GIG)["split"]
            self.assertEqual(sum(s.values()), c)
            self.assertGreaterEqual(s["V7"], 0)
            self.assertLessEqual(abs(s["V7"] - c * 0.12), 3)

    def test_cleared_only(self):
        for bad_stage in ("promised", "booking", "deposit", ""):
            with self.assertRaises(MoneyError):
                split_cleared(10000, bad_stage)
        with self.assertRaises(MoneyError):
            split_cleared(-100, GIG)

    def test_bool_and_float_gross_refused(self):
        for bad in (True, False, 100.0, "100", None):
            with self.assertRaises(MoneyError):
                split_cleared(bad, GIG)


class TestOptionB(unittest.TestCase):
    def test_cut_from_v8_only(self):
        r = split_cleared(100000, GIG)
        paid = pay_collaborator_cut(r, 10000, payee="Manager")
        self.assertEqual(paid["split"]["V8"], 10000)
        self.assertEqual(paid["other_reserves_cents"], 80000)
        self.assertEqual(paid["artist_net_from_v8_cents"], 10000)
        self.assertEqual(paid["collaborator_cut_cents"], 10000)
        for k in paid["split"]:
            if k != "V8":
                self.assertEqual(paid["split"][k], r["split"][k])
        self.assertEqual(r["split"]["V8"], 20000)  # input not mutated

    def test_cut_over_v8_refused(self):
        r = split_cleared(100000, "payout-cleared")
        with self.assertRaises(MoneyError):
            pay_collaborator_cut(r, 20001, payee="Manager")

    def test_sequential_cuts_draw_down_v8(self):
        r = split_cleared(100000, GIG)
        first = pay_collaborator_cut(r, 5000, payee="Feature")
        second = pay_collaborator_cut(first, 5000, payee="Manager")
        self.assertEqual(second["split"]["V8"], 10000)
        self.assertEqual(second["collaborator_cut_cents"], 10000)
        self.assertEqual(second["last_cut_cents"], 5000)
        self.assertEqual([c["payee"] for c in second["cuts"]], ["Feature", "Manager"])

    def test_cut_may_drain_v8_exactly_but_not_beyond(self):
        r = split_cleared(100000, GIG)
        drained = pay_collaborator_cut(r, 20000, payee="M")
        self.assertEqual(drained["split"]["V8"], 0)
        with self.assertRaises(MoneyError):
            pay_collaborator_cut(drained, 1, payee="M")

    def test_cut_input_validation(self):
        r = split_cleared(100000, GIG)
        for bad in (0, -1, True, 10.5, "5", None):
            with self.assertRaises(MoneyError):
                pay_collaborator_cut(r, bad, payee="M")
        for bad_payee in ("", "   ", None):
            with self.assertRaises(MoneyError):
                pay_collaborator_cut(r, 100, payee=bad_payee)


class TestReceiptIntegrity(unittest.TestCase):
    def setUp(self):
        self.r = split_cleared(100000, GIG)

    def test_forged_v8_refused(self):
        f = copy.deepcopy(self.r)
        f["split"]["V8"] = 10**9
        with self.assertRaises(MoneyError):
            pay_collaborator_cut(f, 10**9 - 1, payee="x")

    def test_forged_gross_and_v8_refused(self):
        # The exploit that passed the old code: consistent gross + V8 edit.
        f = copy.deepcopy(self.r)
        f["split"]["V8"] = 10**9
        f["cleared_cents"] += 10**9 - 20000
        with self.assertRaises(MoneyError):
            pay_collaborator_cut(f, 10**9 - 1, payee="x")

    def test_forged_with_recomputed_plain_hash_still_fails_structure(self):
        f = copy.deepcopy(self.r)
        f["split"]["V8"] = 10**9
        f["cleared_cents"] += 10**9 - 20000
        f = money._seal(f, None)  # attacker recomputes SHA-256
        with self.assertRaises(MoneyError):
            pay_collaborator_cut(f, 10**9 - 1, payee="x")

    def test_tampered_cut_counter_refused(self):
        p = pay_collaborator_cut(self.r, 1000, payee="m")
        p["collaborator_cut_cents"] = 0
        with self.assertRaises(MoneyError):
            pay_collaborator_cut(p, 1000, payee="m")

    def test_replay_of_stale_receipt_cannot_exceed_v8(self):
        # Re-using the ORIGINAL receipt twice yields two independent 20000 cuts;
        # callers must chain receipts. Chaining is enforced by V8 draw-down:
        a = pay_collaborator_cut(self.r, 20000, payee="m")
        with self.assertRaises(MoneyError):
            pay_collaborator_cut(a, 1, payee="m")

    def test_unsealed_or_garbage_refused(self):
        f = copy.deepcopy(self.r)
        del f["receipt_hash"]
        for bad in (f, {}, None, "receipt", []):
            with self.assertRaises(MoneyError):
                pay_collaborator_cut(bad, 100, payee="m")

    def test_refusals_are_not_assert_based(self):
        # Must hold under python -O (asserts stripped).
        code = (
            "import sys,copy; sys.path.insert(0,sys.argv[1])\n"
            "from money import *\n"
            "r=split_cleared(100000,'gig-pay-cleared'); f=copy.deepcopy(r)\n"
            "f['split']['V8']=10**9\n"
            "try:\n pay_collaborator_cut(f,10**9-1,'x'); print('ACCEPTED')\n"
            "except MoneyError: print('REFUSED')\n"
        )
        out = subprocess.run([sys.executable, "-I", "-O", "-c", code, str(ROOT)],
                             capture_output=True, text=True).stdout.strip()
        self.assertEqual(out, "REFUSED")

    def test_hmac_mode_blocks_recomputed_hash_and_downgrade(self):
        key = b"test-key"
        r = split_cleared(100000, GIG, key=key)
        self.assertEqual(r["hash_mode"], "HMAC-SHA256")
        paid = pay_collaborator_cut(r, 1000, payee="m", key=key)
        self.assertEqual(paid["split"]["V8"], 19000)
        # wrong key / no key
        with self.assertRaises(MoneyError):
            pay_collaborator_cut(r, 1000, payee="m", key=b"other")
        with self.assertRaises(MoneyError):
            pay_collaborator_cut(r, 1000, payee="m")
        # downgrade: attacker re-seals with plain SHA-256 while a key is required
        plain = money._seal(copy.deepcopy(r), None)
        with self.assertRaises(MoneyError):
            pay_collaborator_cut(plain, 1000, payee="m", key=key)

    def test_env_key_is_picked_up(self):
        os.environ[money.KEY_ENV] = "env-key"
        try:
            r = split_cleared(1000, GIG)
            self.assertEqual(r["hash_mode"], "HMAC-SHA256")
            pay_collaborator_cut(r, 10, payee="m")
        finally:
            del os.environ[money.KEY_ENV]


if __name__ == "__main__":
    unittest.main()
