import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brick import Brick, StoreError
from core import GateError


def _brick():
    br = Brick()
    a = br.add_artist("Test Artist", "music", rate_floor_cents=1000)
    return br, a


def _confirmed(br, a, date, start=None, end=None, buffer=0):
    b = br.offer(a.artist_id, "Venue", "Gig", 10000, date,
                 start_time=start, end_time=end, buffer_minutes=buffer)
    b.to_draft().approve(a).confirm()
    return b


class TestTierGating(unittest.TestCase):
    def test_try_caps_bookings_and_releases(self):
        br, a = _brick()
        br.set_tier(a.artist_id, "try")
        for i in range(3):
            br.offer(a.artist_id, "Venue", f"Gig {i}", 10000, f"2026-12-0{i+1}")
        with self.assertRaises(GateError):
            br.offer(a.artist_id, "Venue", "Gig 4", 10000, "2026-12-09")
        br.add_release("Song", "Test Artist", metadata_complete=True,
                       isrc="USRC17607839", upc="036000291452", artwork_ready=True)
        with self.assertRaises(GateError):
            br.add_release("Song 2", "Test Artist", metadata_complete=True,
                           isrc="USRC17607839", upc="036000291452", artwork_ready=True)

    def test_paid_tier_uncapped_and_lapse_falls_back_to_try(self):
        br, a = _brick()
        sub = br.subscribe(a.artist_id, "pro")
        self.assertEqual(sub.price_cents, 4900)
        sub.record_payment(4900, ref="pay-1")
        for i in range(4):
            br.offer(a.artist_id, "Venue", f"Gig {i}", 10000, f"2026-12-0{i+1}")
        br.mark_subscription_overdue(a.artist_id)
        self.assertEqual(br.tier_for(a.artist_id), "try")
        # 4 active bookings already exceed Try's cap: no NEW booking.
        with self.assertRaises(GateError):
            br.offer(a.artist_id, "Venue", "New", 10000, "2026-12-20")
        with self.assertRaises(GateError):
            br.record_subscription_payment(a.artist_id, 100, ref="short")


class TestTokenIdentity(unittest.TestCase):
    def test_token_survives_load_wrong_token_refused(self):
        br, a = _brick()
        b = br.offer(a.artist_id, "Venue", "Gig", 10000, "2026-12-05")
        b.to_draft()
        with self.assertRaises(GateError):
            b.approve(a, token="wrong-token")
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "brick.json")
            br.save(path)
            loaded = Brick.load(path)
            la = loaded.artists[a.artist_id]
            lb = loaded.bookings[b.id]
            # Old object + token works after load; old object alone does not.
            lb.approve(a, token=la.auth_token)
            self.assertEqual(lb.state.value, "APPROVED")

    def test_production_load_requires_key(self):
        br, a = _brick()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "brick.json")
            br.save(path)  # plain SHA-256 store, no key
            with self.assertRaises(StoreError):
                Brick.load_production(path, key=None)
            with self.assertRaises(StoreError):
                Brick.load_production(path, key="some-key")


class TestSchedulingTimes(unittest.TestCase):
    def test_non_overlapping_times_same_date_ok(self):
        br, a = _brick()
        _confirmed(br, a, "2026-12-05", start="18:00", end="19:00")
        b = br.offer(a.artist_id, "Venue", "Late", 10000, "2026-12-05",
                     start_time="20:00", end_time="21:00")
        b.to_draft().approve(a).confirm()

    def test_overlap_and_buffer_block(self):
        br, a = _brick()
        _confirmed(br, a, "2026-12-05", start="18:00", end="19:00", buffer=30)
        clash = br.offer(a.artist_id, "Venue", "Clash", 10000, "2026-12-05",
                         start_time="19:15", end_time="20:00")
        clash.to_draft().approve(a)
        with self.assertRaises(GateError):
            clash.confirm()
        # Cancel frees the slot again.
        first = list(br.bookings.values())[0]
        first.cancel(a)
        clash.confirm()

    def test_whole_day_blocks_timed(self):
        br, a = _brick()
        _confirmed(br, a, "2026-12-05")  # no times: whole day
        timed = br.offer(a.artist_id, "Venue", "Timed", 10000, "2026-12-05",
                         start_time="20:00", end_time="21:00")
        timed.to_draft().approve(a)
        with self.assertRaises(GateError):
            timed.confirm()


if __name__ == "__main__":
    unittest.main()
