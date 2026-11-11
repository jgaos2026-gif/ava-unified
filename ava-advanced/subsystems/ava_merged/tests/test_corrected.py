"""Corrected NextGen tests — stdlib unittest, no live servers needed
except the live smoke test (run separately, see README).

These tests prove the three critical fixes:
1. Vault: a secret stored under one process state decrypts after a
   simulated restart (re-derived key from the same PIN), and a wrong
   PIN cannot decrypt it.
2. Allocator: the REAL 11-way allocator is in this package (11 vaults,
   balanced, receipt-only, stage-gated) — not the pasted 70/30 version.
3. Embedding: similar texts score higher than unrelated texts, and
   embedding is deterministic (same text, same vector).
"""
import hashlib
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["VAULT_DATA_DIR"] = tempfile.mkdtemp(prefix="ava_vault_test_")
TEST_PIN = __import__("secrets").token_hex(16)  # random per run, never a real PIN
os.environ["AVA_VAULT_PIN_HASH"] = hashlib.sha256(TEST_PIN.encode()).hexdigest()

from fastapi.testclient import TestClient  # noqa: E402

from jga_auto.allocator_11vt import allocate_cleared_payment  # noqa: E402
from services.embedding_braid import embed_text  # noqa: E402
from services.private_vault import app as vault_app  # noqa: E402


class TestAllocator(unittest.TestCase):
    def test_real_11vt(self):
        r = allocate_cleared_payment(575000, "DEPOSIT_CLEARED_35", "JOB-TEST")
        self.assertTrue(r["balanced"])
        self.assertEqual(r["banking_execution"], "NONE_LEDGER_RECEIPT_ONLY")
        self.assertEqual(len(r["vaults"]), 11)
        self.assertEqual(sum(v["amount_cents"] for v in r["vaults"].values()),
                         575000)

    def test_stage_gated(self):
        with self.assertRaises(ValueError):
            allocate_cleared_payment(575000, "CONTRACT_PRICE", "JOB-TEST")

    def test_no_pasted_70_30_fields(self):
        r = allocate_cleared_payment(575000, "DEPOSIT_CLEARED_35", "JOB-TEST")
        self.assertNotIn("operating_ledger_cents", r["vaults"])


class TestVaultPersistence(unittest.TestCase):
    def test_store_survives_restart_and_wrong_pin_fails(self):
        c = TestClient(vault_app)
        h = {"X-AVA-VAULT-PIN": TEST_PIN}
        self.assertEqual(c.post("/store", json={"key": "k1", "secret_payload": "s3cret"},
                                headers=h).status_code, 200)
        # Simulated restart: a fresh TestClient re-derives the key
        # from the same PIN + the stored salt.
        c2 = TestClient(vault_app)
        got = c2.get("/retrieve/k1", headers=h)
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.json()["secret_payload"], "s3cret")
        wrong = c2.get("/retrieve/k1",
                       headers={"X-AVA-VAULT-PIN": "wrong-pin"})
        self.assertEqual(wrong.status_code, 401)

    def test_locked_without_env_hash(self):
        saved = os.environ.pop("AVA_VAULT_PIN_HASH", None)
        try:
            c = TestClient(vault_app)
            self.assertEqual(c.get("/retrieve/k1",
                                   headers={"X-AVA-VAULT-PIN": TEST_PIN}).status_code,
                             503)
        finally:
            if saved:
                os.environ["AVA_VAULT_PIN_HASH"] = saved


class TestEmbeddingHonesty(unittest.TestCase):
    def test_similar_beats_unrelated_and_deterministic(self):
        a = embed_text("minimalist typography layout design")
        b = embed_text("minimalist typography layout")
        c = embed_text("quantum plasma reactor coolant")
        import numpy as np
        self.assertGreater(float(np.dot(a, b)), float(np.dot(a, c)))
        self.assertAlmostEqual(float(np.dot(a, embed_text(
            "minimalist typography layout design"))), 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
