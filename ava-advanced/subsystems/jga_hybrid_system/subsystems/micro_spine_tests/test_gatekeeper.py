"""Tests for the BCT Gatekeeper (Option 2), all four stages."""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ed25519
from bct_gatekeeper import (Gatekeeper, build_frame, expected_vault_amounts,
                            TYPE_HEARTBEAT, TYPE_VAULT_TX)
from micro_spine import MicroSpine

SECRET = b"gatekeeper-test-secret-16+!"
NODE = b"OASIS-PAVILION-0"  # exactly 16 bytes
OTHER_NODE = b"OASIS-THINKBOOK0"  # 16 bytes, not in registry


def vault_body(cleared=7500, stage="DEPOSIT_CLEARED_35", job="JOB-1"):
    return json.dumps({
        "job_id": job,
        "payment_stage": stage,
        "cleared_amount_cents": cleared,
        "vaults": expected_vault_amounts(cleared),
        "banking_execution": "NONE_LEDGER_RECEIPT_ONLY",
    }).encode()


class GatekeeperTest(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        td = Path(self._td.name)
        self.spine = MicroSpine(td / "spine.bin", SECRET)
        self.sk, self.pk = ed25519.generate_keypair()
        self.gk = Gatekeeper(self.spine, {NODE: self.pk},
                             td / "state.json")

    def tearDown(self):
        self._td.cleanup()

    def _snapshot(self):
        p = self.spine.filepath
        return p.read_bytes(), self.spine.record_count, self.spine.last_hash

    def test_valid_heartbeat_passes(self):
        frame = build_frame(self.sk, NODE, TYPE_HEARTBEAT, 1, b"HEARTBEAT")
        res = self.gk.process(frame)
        self.assertTrue(res.ok, res)
        self.assertEqual(self.spine.record_count, 1)
        self.assertIsNotNone(res.pocket_hash)

    def test_valid_vault_tx_passes(self):
        frame = build_frame(self.sk, NODE, TYPE_VAULT_TX, 1, vault_body())
        res = self.gk.process(frame)
        self.assertTrue(res.ok, res)
        self.assertEqual(self.spine.record_count, 1)

    def _assert_reject_no_mutation(self, frame, code):
        before = self._snapshot()
        res = self.gk.process(frame)
        self.assertFalse(res.ok, res)
        self.assertEqual(res.code, code)
        self.assertEqual(self._snapshot(), before)

    def test_bad_magic_rejects(self):
        frame = bytearray(build_frame(self.sk, NODE, TYPE_HEARTBEAT, 1, b""))
        frame[0] = ord("X")
        self._assert_reject_no_mutation(bytes(frame), "STAGE1_BAD_MAGIC")

    def test_replay_sequence_rejects(self):
        self.assertTrue(self.gk.process(
            build_frame(self.sk, NODE, TYPE_HEARTBEAT, 5, b"")).ok)
        self._assert_reject_no_mutation(
            build_frame(self.sk, NODE, TYPE_HEARTBEAT, 5, b""),
            "STAGE1_REPLAY_SEQUENCE")
        # A replay after restart is still blocked via persisted state.
        gk2 = Gatekeeper(self.spine, {NODE: self.pk},
                         Path(self._td.name) / "state.json")
        res = gk2.process(build_frame(self.sk, NODE, TYPE_HEARTBEAT, 5, b""))
        self.assertFalse(res.ok)
        self.assertEqual(res.code, "STAGE1_REPLAY_SEQUENCE")

    def test_old_timestamp_rejects(self):
        old = int(time.time() * 1000) - 600_000  # 10 minutes ago
        frame = build_frame(self.sk, NODE, TYPE_HEARTBEAT, 1, b"",
                            timestamp_ms=old)
        self._assert_reject_no_mutation(frame, "STAGE1_TIMESTAMP_OUT_OF_WINDOW")

    def test_unknown_node_rejects(self):
        sk2, _ = ed25519.generate_keypair()
        frame = build_frame(sk2, OTHER_NODE, TYPE_HEARTBEAT, 1, b"")
        self._assert_reject_no_mutation(frame, "STAGE2_UNKNOWN_NODE")

    def test_bad_signature_rejects_and_seq_not_burned(self):
        frame = bytearray(build_frame(self.sk, NODE, TYPE_HEARTBEAT, 1, b""))
        frame[-1] ^= 0x01  # flip a body byte after signing (empty body -> use header sig byte instead)
        # For an empty body, flip the last signature byte instead:
        frame = bytearray(build_frame(self.sk, NODE, TYPE_HEARTBEAT, 1, b"HEARTBEAT"))
        frame[40] ^= 0x01  # inside the 64-byte signature field
        self._assert_reject_no_mutation(bytes(frame), "STAGE2_BAD_SIGNATURE")
        # Same sequence with a correct signature still passes (not burned).
        res = self.gk.process(build_frame(self.sk, NODE, TYPE_HEARTBEAT, 1, b"HEARTBEAT"))
        self.assertTrue(res.ok, res)

    def test_unbalanced_vault_rejects(self):
        body = json.loads(vault_body())
        body["vaults"]["V1_FED_TAX_RESERVE"] += 100
        frame = build_frame(self.sk, NODE, TYPE_VAULT_TX, 1,
                            json.dumps(body).encode())
        self._assert_reject_no_mutation(frame, "STAGE3_VALIDATION_FAILED")

    def test_vault_claiming_bank_movement_rejects(self):
        body = json.loads(vault_body())
        body["banking_execution"] = "BLUEVINE_TRANSFER"
        frame = build_frame(self.sk, NODE, TYPE_VAULT_TX, 1,
                            json.dumps(body).encode())
        self._assert_reject_no_mutation(frame, "STAGE3_VALIDATION_FAILED")

    def test_unknown_type_rejects(self):
        frame = build_frame(self.sk, NODE, 0x9999, 1, b"")
        self._assert_reject_no_mutation(frame, "STAGE1_UNKNOWN_TYPE")


if __name__ == "__main__":
    unittest.main()
