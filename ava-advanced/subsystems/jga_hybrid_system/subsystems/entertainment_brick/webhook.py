"""Webhook verification and reconciliation.

A payment processor saying "succeeded" is NOT, by itself, cleared money.
This module requires, before anything is recorded:

1. A valid HMAC-SHA256 signature over "<timestamp>.<payload>" (Stripe-style
   header "t=<unix>,v1=<hex>"), with the timestamp within 300 seconds.
   The secret comes from the caller / environment, never from this file,
   and is never logged.
2. An event status that actually means cleared ("succeeded" / "cleared").
   Pending, failed, or unknown statuses are refused, not recorded.
3. Idempotency: a duplicate event id, or a duplicate external_ref already
   in the ledger, cannot double-credit. The second delivery returns
   {"duplicate": True} and records nothing.

This is a verifier for webhooks you receive, not a live Stripe client:
no network call, no credentials, and no payment is sent from here.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time

from core import GateError
from ledger import LedgerError

CLEARED_STATUSES = ("succeeded", "cleared")
TIMESTAMP_TOLERANCE_SECONDS = 300


class WebhookError(ValueError):
    pass


def verify_signature(payload: bytes, signature_header: str, secret: str,
                      now: int | None = None) -> None:
    """Raise WebhookError unless the signature header verifies."""
    if not secret:
        raise WebhookError("webhook secret is required")
    if not signature_header:
        raise WebhookError("missing signature header")
    parts = {}
    for piece in signature_header.split(","):
        if "=" in piece:
            k, v = piece.split("=", 1)
            parts[k.strip()] = v.strip()
    try:
        timestamp = int(parts["t"])
        claimed = parts["v1"]
    except (KeyError, ValueError):
        raise WebhookError("malformed signature header") from None
    now = int(time.time()) if now is None else now
    if abs(now - timestamp) > TIMESTAMP_TOLERANCE_SECONDS:
        raise WebhookError("webhook timestamp outside tolerance")
    signed = f"{timestamp}.".encode() + payload
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, claimed):
        raise WebhookError("webhook signature mismatch")


def sign_for_test(payload: bytes, secret: str, timestamp: int) -> str:
    """Test helper only: build a valid header for a given payload."""
    signed = f"{timestamp}.".encode() + payload
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


class WebhookProcessor:
    """Verified webhook -> ledger, with duplicate deliveries ignored."""

    def __init__(self, brick, secret: str):
        self.brick = brick
        self.secret = secret
        self.seen_event_ids: set[str] = set()

    def process(self, event_id: str, payload: bytes, signature_header: str,
                now: int | None = None) -> dict:
        if event_id in self.seen_event_ids:
            return {"duplicate": True, "entry": None}
        verify_signature(payload, signature_header, self.secret, now=now)
        try:
            event = json.loads(payload.decode())
        except (ValueError, UnicodeDecodeError) as e:
            raise WebhookError(f"webhook payload is not JSON: {e}") from e
        if event.get("status") not in CLEARED_STATUSES:
            raise WebhookError(
                f"event status {event.get('status')!r} is not cleared; not recorded")
        external_ref = event.get("external_ref") or event.get("id")
        if not external_ref:
            raise WebhookError("webhook event has no external_ref")
        try:
            entry = self.brick.record_cleared(
                external_ref,
                event["cleared_cents"],
                event["stage"],
                booking_id=event.get("booking_id"),
            )
        except (LedgerError, GateError, KeyError, TypeError) as e:
            # Duplicate external_ref in the ledger = duplicate delivery:
            # reconciliation, not a new credit.
            if "already recorded" in str(e):
                self.seen_event_ids.add(event_id)
                return {"duplicate": True, "entry": None}
            raise WebhookError(f"webhook event rejected: {e}") from e
        self.seen_event_ids.add(event_id)
        return {"duplicate": False, "entry": entry}
