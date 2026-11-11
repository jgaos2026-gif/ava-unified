import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import money
from brick import Brick, StoreError
from core import BookingState, GateError


def populated(key=None):
    br = Brick(key=key)
    a = br.add_artist("A", "music", location="Peoria", rate_floor_cents=1000)
    b = br.offer(a.artist_id, "Venue", "Gig", 100000, "2026-12-01")
    b.to_draft().approve(a).confirm()
    br.message(b.id, "Venue", "load-in at 6")
    r = br.add_release("Song", "A", metadata_complete=True, isrc="USRC17607839",
                       upc="036000291452", artwork_ready=True)
    br.message(r.id, "A", "submitting")
    br.expenses.add("travel", 2500, "gas")
    e = br.record_cleared("tx1", 100000, "gig-pay-cleared", b.id)
    br.pay_cut(e["id"], 4000, "Manager")
    return br, a, b


class TestStore(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "brick.json")

    def tearDown(self):
        self.dir.cleanup()

    def edit(self, fn, key=None, reseal=True):
        """Tamper with the saved file; optionally recompute the plain hash."""
        with open(self.path) as f:
            doc = json.load(f)
        fn(doc)
        if reseal:
            doc = money.seal({k: v for k, v in doc.items() if k not in ("receipt_hash", "hash_mode")}, key)
        with open(self.path, "w") as f:
            json.dump(doc, f)

    def test_roundtrip_preserves_everything(self):
        br, a, b = populated()
        br.save(self.path)
        self.assertEqual(oct(os.stat(self.path).st_mode & 0o777), "0o600")
        l = Brick.load(self.path)
        self.assertEqual(l.to_dict(), br.to_dict())
        self.assertEqual(l.bookings[b.id].state, BookingState.CONFIRMED)
        self.assertEqual(l.ledger.vault_totals(), br.ledger.vault_totals())
        self.assertEqual(len(l.log.for_booking(b.id)), 1)
        # loaded gates still work: double-booking and cut chaining
        la = l.artists[a.artist_id]
        b2 = l.offer(la.artist_id, "V2", "G2", 5000, "2026-12-01").to_draft().approve(la)
        with self.assertRaises(GateError):
            b2.confirm()
        self.assertEqual(l.ledger.head("led-0001")["split"]["V8"], 16000)

    def test_ids_do_not_collide_after_load(self):
        br, a, b = populated()
        br.save(self.path)
        l = Brick.load(self.path)
        nb = l.offer(a.artist_id, "V", "G", 5000)
        self.assertNotIn(nb.id, br.bookings)
        self.assertEqual(len({*l.bookings}), 2)

    def test_plain_edit_detected(self):
        br, a, b = populated(); br.save(self.path)
        self.edit(lambda d: d["expenses"][0].update(amount_cents=1), reseal=False)
        with self.assertRaises(StoreError):
            Brick.load(self.path)

    def test_forged_confirmed_booking_rejected_even_if_hash_recomputed(self):
        br, a, b = populated(); br.save(self.path)
        def forge(d):
            d["bookings"].append({"id": "book-777", "artist_id": a.artist_id, "buyer": "X",
                                  "title": "Fake", "rate_cents": 1, "date": None,
                                  "state": "CONFIRMED", "history": []})
        self.edit(forge)
        with self.assertRaises(StoreError):
            Brick.load(self.path)

    def test_forged_approval_by_buyer_rejected(self):
        br, a, b = populated(); br.save(self.path)
        def forge(d):
            for h in d["bookings"][0]["history"]:
                if h["to"] == "APPROVED":
                    h["actor"] = "buyer:Venue"
        self.edit(forge)
        with self.assertRaises(StoreError):
            Brick.load(self.path)

    def test_skipped_transition_rejected(self):
        br, a, b = populated(); br.save(self.path)
        self.edit(lambda d: d["bookings"][0]["history"].pop(1))
        with self.assertRaises(StoreError):
            Brick.load(self.path)

    def test_forged_receipt_rejected_even_if_hash_recomputed(self):
        br, a, b = populated(); br.save(self.path)
        def forge(d):
            r = d["ledger"]["entries"][0]["receipts"][-1]
            r["split"]["V8"] += 50000
            r["cleared_cents"] += 50000
            r.pop("receipt_hash"); r.pop("hash_mode")
            d["ledger"]["entries"][0]["receipts"][-1] = money.seal(r, None)
        self.edit(forge)
        with self.assertRaises(StoreError):
            Brick.load(self.path)

    def test_dropped_cut_history_rejected(self):
        br, a, b = populated(); br.save(self.path)
        def forge(d):
            d["ledger"]["entries"][0]["receipts"].pop()   # silently un-pay the cut
        self.edit(forge)
        l = Brick.load(self.path)   # a shorter valid chain IS a valid chain...
        self.assertEqual(l.ledger.head("led-0001").get("collaborator_cut_cents", 0), 0)
        # ...which is exactly why a keyless file hash is not authentication:
        # see test_hmac_blocks_recomputed_seal below.

    def test_hmac_blocks_recomputed_seal(self):
        key = b"k"
        br, a, b = populated(key); br.save(self.path)
        Brick.load(self.path, key=key)
        with self.assertRaises(StoreError):
            Brick.load(self.path)                      # no key
        with self.assertRaises(StoreError):
            Brick.load(self.path, key=b"wrong")
        # attacker edits and re-seals with plain SHA-256 (downgrade) -> refused
        self.edit(lambda d: d["ledger"]["entries"][0]["receipts"].pop(), key=None)
        with self.assertRaises(StoreError):
            Brick.load(self.path, key=key)

    def test_missing_corrupt_and_wrong_version(self):
        with self.assertRaises(StoreError):
            Brick.load(os.path.join(self.dir.name, "nope.json"))
        with open(self.path, "w") as f:
            f.write("{not json")
        with self.assertRaises(StoreError):
            Brick.load(self.path)
        br, *_ = populated(); br.save(self.path)
        self.edit(lambda d: d.update(version=99))
        with self.assertRaises(StoreError):
            Brick.load(self.path)

    def test_save_is_atomic_no_temp_left_behind(self):
        br, *_ = populated(); br.save(self.path); br.save(self.path)
        self.assertEqual(os.listdir(self.dir.name), ["brick.json"])


if __name__ == "__main__":
    unittest.main()
