import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import money as moneymod
from brick import Brick, StoreError
from core import BookingState, GateError
from secretary import PERSONALITIES, Secretary, choices


def world():
    br = Brick()
    a = br.add_artist("A", "music", rate_floor_cents=5000)
    b = br.offer(a.artist_id, "Venue", "Gig", 123456, "2026-12-01")
    return br, a, b


class TestSecretary(unittest.TestCase):
    def test_choices_listed(self):
        keys = {c["key"] for c in choices()}
        self.assertEqual(keys, set(PERSONALITIES))
        self.assertTrue(all(c["sample"] and c["label"] for c in choices()))

    def test_unknown_personality_or_name_refused(self):
        for bad in ("pirate", "", None):
            with self.assertRaises(GateError):
                Secretary(bad)
        with self.assertRaises(GateError):
            Secretary("warm", name="  ")

    def test_every_voice_carries_identical_facts(self):
        br, a, b = world()
        for p in PERSONALITIES:
            t = Secretary(p).offer(b).text
            for fact in (b.id, "Venue", "Gig", "2026-12-01", "$1,234.56", "$50.00", "OFFER"):
                self.assertIn(fact, t, (p, fact))
            self.assertIn("Nothing is confirmed until you approve", t)

    def test_voices_actually_differ(self):
        br, a, b = world()
        texts = {Secretary(p).offer(b).text for p in PERSONALITIES}
        self.assertEqual(len(texts), len(PERSONALITIES))

    def test_confirmed_wording_only_for_confirmed_booking(self):
        br, a, b = world()
        for p in PERSONALITIES:
            with self.assertRaises(GateError):
                Secretary(p).confirmed(b)          # still an OFFER
        b.to_draft().approve(a)
        with self.assertRaises(GateError):
            Secretary("hype").confirmed(b)         # approved, not confirmed
        b.confirm()
        self.assertIn("CONFIRMED", Secretary("hype").confirmed(b).text)
        with self.assertRaises(GateError):
            Secretary("warm").rejected(b)
        b.cancel("Venue")
        self.assertIn("CANCELLED", Secretary("blunt").cancelled(b).text)

    def test_drafting_never_changes_state_or_logs(self):
        br, a, b = world()
        sec = Secretary("hype")
        sec.offer(b); sec.decision_prompt(b); sec.brief(br)
        self.assertEqual(b.state, BookingState.OFFER)
        self.assertEqual(br.log.messages, [])
        self.assertEqual(b.history, [])

    def test_send_is_explicit_and_needs_a_ref(self):
        br, a, b = world()
        sec = Secretary("warm")
        d = sec.offer(b)
        d.send(br.log, "secretary")
        self.assertEqual(len(br.log.for_booking(b.id)), 1)
        with self.assertRaises(GateError):
            sec.brief(br).send(br.log, "secretary")   # no booking -> would be an orphan

    def test_decision_prompt_lists_choices_but_only_while_pending(self):
        br, a, b = world()
        t = Secretary("blunt").decision_prompt(b).text
        for n in ("1)", "2)", "3)"):
            self.assertIn(n, t)
        b.to_draft()
        self.assertIn("Approve", Secretary("blunt").decision_prompt(b).text)
        b.approve(a)
        with self.assertRaises(GateError):
            Secretary("blunt").decision_prompt(b)

    def test_payment_and_release_and_brief_facts(self):
        br, a, b = world()
        b.to_draft().approve(a).confirm()
        e = br.record_cleared("tx-9", 100000, "gig-pay-cleared", b.id)
        br.pay_cut(e["id"], 4000, "Manager")
        r = br.add_release("Song", "A", metadata_complete=True, isrc="USRC17607839")
        for p in PERSONALITIES:
            s = Secretary(p)
            pay = s.payment(br.ledger, e["id"]).text
            for fact in ("tx-9", "$1,000.00", "$160.00", "$40.00", "no money was moved"):
                self.assertIn(fact, pay, (p, fact))
            self.assertIn("NOT ready", s.release_status(r).text)
            self.assertIn("UPC missing", s.release_status(r).text)
            self.assertIn("1 confirmed", s.brief(br).text)

    def test_choice_persists_and_old_stores_still_load(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "b.json")
            br, a, b = world()
            self.assertEqual(br.secretary_for(a.artist_id).personality, "professional")  # default
            br.set_secretary(a.artist_id, "hype", "Dee")
            br.save(path)
            l = Brick.load(path)
            s = l.secretary_for(a.artist_id)
            self.assertEqual((s.personality, s.name), ("hype", "Dee"))
            # store written before this feature (no "secretaries" key)
            import json
            doc = json.load(open(path)); doc.pop("secretaries")
            doc = moneymod.seal({k: v for k, v in doc.items() if k not in ("receipt_hash", "hash_mode")}, None)
            json.dump(doc, open(path, "w"))
            self.assertEqual(Brick.load(path).secretary_for(a.artist_id).personality, "professional")
            # forged personality (hash recomputed) is refused at load
            doc = json.load(open(path)); doc["secretaries"] = {a.artist_id: {"personality": "evil", "name": "x"}}
            doc = moneymod.seal({k: v for k, v in doc.items() if k not in ("receipt_hash", "hash_mode")}, None)
            json.dump(doc, open(path, "w"))
            with self.assertRaises(StoreError):
                Brick.load(path)

    def test_set_secretary_unknown_artist_or_choice(self):
        br, a, b = world()
        with self.assertRaises(GateError):
            br.set_secretary("art-999", "warm")
        with self.assertRaises(GateError):
            br.set_secretary(a.artist_id, "pirate")


if __name__ == "__main__":
    unittest.main()
