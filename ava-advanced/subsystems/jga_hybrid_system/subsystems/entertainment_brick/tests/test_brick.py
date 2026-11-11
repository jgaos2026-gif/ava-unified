import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import (Artist, Booking, BookingState, ExpenseTracker, GateError,
                  MessageLog)
from music import Release


def confirmed(artist=None):
    artist = artist or Artist("Test Artist", "music", rate_floor_cents=5000)
    return Booking(artist, "Venue", "Gig", 10000).to_draft().approve(artist).confirm()


class TestBookingGate(unittest.TestCase):
    def test_confirm_requires_approval(self):
        artist = Artist("Test Artist", "music", location="Peoria", rate_floor_cents=5000)
        booking = Booking(artist, "Venue", "Gig", 10000).to_draft()
        with self.assertRaises(GateError):
            booking.confirm()
        booking.approve(artist).confirm()
        self.assertEqual(booking.state, BookingState.CONFIRMED)

    def test_rate_floor_blocks_low_offer(self):
        artist = Artist("Test Artist", "music", rate_floor_cents=5000)
        with self.assertRaises(GateError):
            Booking(artist, "Venue", "Cheap gig", 100)

    def test_reject_stops_booking(self):
        artist = Artist("Test Artist", "music")
        booking = Booking(artist, "Venue", "Gig", 10000).reject(artist)
        with self.assertRaises(GateError):
            booking.confirm()

    # --- fix 2: approval identity ---
    def test_only_booked_artist_can_approve(self):
        artist = Artist("A", "music")
        other = Artist("B", "music")
        b = Booking(artist, "Venue", "Gig", 100).to_draft()
        for impostor in (other, "Venue", None):
            with self.assertRaises(GateError):
                b.approve(impostor)
        self.assertEqual(b.state, BookingState.DRAFT)
        with self.assertRaises(TypeError):
            b.approve()  # actor is mandatory

    def test_history_records_actor(self):
        b = confirmed()
        self.assertEqual([h["to"] for h in b.history],
                         ["DRAFT", "APPROVED", "CONFIRMED"])
        self.assertEqual(b.history[1]["actor"], "artist:Test Artist")
        self.assertTrue(all(h["at"] for h in b.history))

    # --- fix 3: reject / cancel ---
    def test_reject_blocked_after_confirm_and_when_terminal(self):
        b = confirmed()
        with self.assertRaises(GateError):
            b.reject(b.artist)
        o = Booking(Artist("A", "music"), "V", "G", 1)
        o.reject("V")
        with self.assertRaises(GateError):
            o.reject("V")  # no double reject

    def test_cancel_only_from_confirmed_by_party(self):
        a = Artist("A", "music")
        b = Booking(a, "V", "G", 100)
        with self.assertRaises(GateError):
            b.cancel(a)  # not confirmed yet
        b.to_draft().approve(a).confirm()
        with self.assertRaises(GateError):
            b.cancel("stranger")
        b.cancel("V")
        self.assertEqual(b.state, BookingState.CANCELLED)
        with self.assertRaises(GateError):
            b.confirm()

    def test_state_is_read_only(self):
        b = Booking(Artist("A", "music"), "V", "G", 100)
        with self.assertRaises(AttributeError):
            b.state = BookingState.CONFIRMED
        with self.assertRaises(AttributeError):
            b.rate_cents = 1

    # --- fix 4: floor holds after construction ---
    def test_reprice_respects_floor_and_state(self):
        a = Artist("A", "music", rate_floor_cents=5000)
        b = Booking(a, "V", "G", 10000)
        with self.assertRaises(GateError):
            b.reprice(1)
        b.reprice(6000)
        self.assertEqual(b.rate_cents, 6000)
        b.to_draft().approve(a).confirm()
        with self.assertRaises(GateError):
            b.reprice(9000)  # locked after approval

    def test_raised_floor_blocks_approve_and_confirm(self):
        a = Artist("A", "music", rate_floor_cents=1000)
        b = Booking(a, "V", "G", 2000).to_draft()
        a.rate_floor_cents = 5000
        with self.assertRaises(GateError):
            b.approve(a)
        a.rate_floor_cents = 1000
        b.approve(a)
        a.rate_floor_cents = 5000
        with self.assertRaises(GateError):
            b.confirm()

    def test_bad_rate_types_and_floor(self):
        a = Artist("A", "music")
        for bad in (True, 1.5, -1, "100", None):
            with self.assertRaises(GateError):
                Booking(a, "V", "G", bad)
        with self.assertRaises(GateError):
            Artist("A", "music", rate_floor_cents=-5)

    def test_failed_construction_does_not_burn_ids(self):
        a = Artist("A", "music", rate_floor_cents=5000)
        first = Booking(a, "V", "G", 5000)
        with self.assertRaises(GateError):
            Booking(a, "V", "G", 1)
        second = Booking(a, "V", "G", 5000)
        self.assertEqual(int(second.id[5:]), int(first.id[5:]) + 1)


class TestMessagesAndExpenses(unittest.TestCase):
    def test_message_needs_booking(self):
        log = MessageLog()
        with self.assertRaises(GateError):
            log.add("", "buyer", "hello")
        log.register("book-001")
        log.add("book-001", "buyer", "hello")
        self.assertEqual(len(log.for_booking("book-001")), 1)

    # --- fix 5: no orphans ---
    def test_unknown_id_refused_and_booking_autoregisters(self):
        log = MessageLog()
        with self.assertRaises(GateError):
            log.add("nonexistent-xyz", "x", "hi")
        b = Booking(Artist("A", "music"), "V", "G", 1)
        log.add(b, "V", "hi")
        self.assertEqual(len(log.for_booking(b.id)), 1)
        with self.assertRaises(GateError):
            log.add(b, "", "no sender")

    def test_expense_categories(self):
        tracker = ExpenseTracker()
        tracker.add("travel", 25000, "gas")
        tracker.add("cds", 10000, "pressing")
        totals = tracker.total_by_category()
        self.assertEqual(totals["travel"], 25000)
        self.assertEqual(totals["cds"], 10000)
        with self.assertRaises(GateError):
            tracker.add("rent", 100)

    # --- fix 6: type holes ---
    def test_expense_rejects_float_bool_negative(self):
        t = ExpenseTracker()
        for bad in (1.5, True, -1, "5", None):
            with self.assertRaises(GateError):
                t.add("travel", bad)
        self.assertEqual(t.total_by_category()["travel"], 0)


class TestScheduling(unittest.TestCase):
    def test_double_booking_blocked_and_cancel_frees_date(self):
        a = Artist("A", "music")
        b1 = Booking(a, "V1", "G1", 100, "2026-12-01").to_draft().approve(a).confirm()
        b2 = Booking(a, "V2", "G2", 100, "2026-12-01").to_draft().approve(a)
        with self.assertRaises(GateError):
            b2.confirm()
        b1.cancel("V1")
        b2.confirm()
        self.assertEqual(b2.state, BookingState.CONFIRMED)

    def test_different_dates_and_undated_ok(self):
        a = Artist("A", "music")
        for d in ("2026-12-01", "2026-12-02", None, None):
            Booking(a, "V", "G", 1, d).to_draft().approve(a).confirm()

    def test_bad_date_refused(self):
        for bad in ("12/01/2026", "2026-13-40", 5, "tomorrow"):
            with self.assertRaises(GateError):
                Booking(Artist("A", "music"), "V", "G", 1, bad)

    def test_unavailable_artist_cannot_be_offered(self):
        with self.assertRaises(GateError):
            Booking(Artist("A", "music", available=False), "V", "G", 1)


class TestReleasePrep(unittest.TestCase):
    def test_not_ready_until_all_fields_present(self):
        release = Release("Song", "Test Artist", metadata_complete=True, isrc="USRC17607839")
        self.assertFalse(release.distributor_ready())
        release.upc = "036000291452"
        release.artwork_ready = True
        self.assertTrue(release.distributor_ready())

    def test_malformed_identifiers_block_ready(self):
        r = Release("S", "A", True, "USX1", "12345", True)
        self.assertFalse(r.distributor_ready())
        self.assertEqual(len(r.problems()), 2)
        r.isrc, r.upc = "US-RC1-76-07839", "036000291453"  # good ISRC, bad check digit
        self.assertEqual(r.problems(), ["UPC/EAN invalid (length or check digit)"])
        r.upc = "4006381333931"                             # valid EAN-13
        self.assertTrue(r.distributor_ready())

    def test_release_needs_title_and_artist(self):
        with self.assertRaises(ValueError):
            Release("", "A")


if __name__ == "__main__":
    unittest.main()
