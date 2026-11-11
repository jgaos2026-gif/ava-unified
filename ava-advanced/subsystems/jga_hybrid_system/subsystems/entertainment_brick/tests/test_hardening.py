import json
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brick import Brick
from core import GateError
from webhook import WebhookError, WebhookProcessor, sign_for_test

SECRET = "test-webhook-secret"


def _setup():
    br = Brick()
    a = br.add_artist("Artist A", "music", rate_floor_cents=1000)
    b = br.add_artist("Artist B", "music", rate_floor_cents=1000)
    booking = br.offer(a.artist_id, "Venue", "Gig", 10000, "2026-12-05")
    booking.to_draft().approve(a).confirm()
    return br, a, b, booking


def _payload(event_id, status="succeeded", ref="wh-1", cents=10000):
    return json.dumps({
        "id": event_id, "status": status, "external_ref": ref,
        "cleared_cents": cents, "stage": "gig-pay-cleared",
    }).encode()


class TestWebhook(unittest.TestCase):
    def test_verified_webhook_records_once(self):
        br, a, _, booking = _setup()
        proc = WebhookProcessor(br, SECRET)
        payload = _payload("evt-1")
        # booking_id is required for gig-pay-cleared; add it to the event.
        event = json.loads(payload)
        event["booking_id"] = booking.id
        payload = json.dumps(event).encode()
        now = int(time.time())
        header = sign_for_test(payload, SECRET, now)
        first = proc.process("evt-1", payload, header, now=now)
        self.assertFalse(first["duplicate"])
        second = proc.process("evt-1", payload, header, now=now)
        self.assertTrue(second["duplicate"])
        # A different event id with the same external_ref also cannot double-credit.
        third = proc.process("evt-2", payload, header, now=now)
        self.assertTrue(third["duplicate"])
        self.assertEqual(len(br.ledger.entries), 1)

    def test_bad_signature_stale_and_pending_refused(self):
        br, a, _, booking = _setup()
        proc = WebhookProcessor(br, SECRET)
        now = int(time.time())
        payload = _payload("evt-9")
        good = sign_for_test(payload, SECRET, now)
        with self.assertRaises(WebhookError):
            proc.process("evt-9", payload, "t=1,v1=deadbeef", now=now)
        with self.assertRaises(WebhookError):
            proc.process("evt-9", payload, sign_for_test(payload, SECRET, now - 10000), now=now)
        pending = _payload("evt-10", status="pending")
        with self.assertRaises(WebhookError):
            proc.process("evt-10", pending, sign_for_test(pending, SECRET, now), now=now)
        self.assertEqual(len(br.ledger.entries), 0)


class TestTenantAndRotation(unittest.TestCase):
    def test_artist_a_cannot_approve_or_read_b(self):
        br, a, b, _ = _setup()
        booking_b = br.offer(b.artist_id, "Venue", "B Gig", 10000, "2026-12-06")
        booking_b.to_draft()
        with self.assertRaises(GateError):
            br.get_booking_for(a.artist_id, booking_b.id)
        with self.assertRaises(GateError):
            br.approve_booking(a.artist_id, booking_b.id, token=a.auth_token)
        # B's own token works.
        br.approve_booking(b.artist_id, booking_b.id, token=b.auth_token)

    def test_token_rotation_invalidates_old_token(self):
        br, a, _, _ = _setup()
        booking = br.offer(a.artist_id, "Venue", "Gig 2", 10000, "2026-12-07")
        booking.to_draft()
        old = a.auth_token
        new = br.rotate_artist_token(a.artist_id, old)
        self.assertNotEqual(new, old)
        with self.assertRaises(GateError):
            booking.approve(a, token=old)
        booking.approve(a, token=new)
        with self.assertRaises(GateError):
            br.rotate_artist_token(a.artist_id, old)


if __name__ == "__main__":
    unittest.main()
