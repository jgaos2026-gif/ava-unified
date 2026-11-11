"""Tier definitions and subscription billing ledger.

Tiers were decided by John 2026-11-02; this module is the first code that
enforces them. Only caps that were actually decided are enforced:
Try is capped (3 active bookings, 1 release prep). Paid tiers have no
booking/release cap in the design, so none is invented here.

Billing is a LEDGER, not a payment processor: it records subscriptions,
payments and lapses. No Stripe call, no card charge, no credentials live
here. A real charge needs a verified Stripe account and credentials in
the vault, which is a separate integration, not a code change.

Lapse rule: data is never deleted. A past-due/suspended subscription
falls back to Try gating for NEW bookings/releases; confirmed bookings
already made stand, and the artist can always read their own data.
"""
from __future__ import annotations

from core import GateError

TIERS = {
    "try": {
        "name": "Try", "monthly_cents": 0, "yearly_cents": 0,
        "max_active_bookings": 3, "max_releases": 1,
    },
    "starter": {
        "name": "Starter", "monthly_cents": 1900, "yearly_cents": 19000,
        "max_active_bookings": None, "max_releases": None,
    },
    "pro": {
        "name": "Pro", "monthly_cents": 4900, "yearly_cents": 49000,
        "max_active_bookings": None, "max_releases": None,
    },
    "full_label": {
        "name": "Full Label", "monthly_cents": 12900, "yearly_cents": 129000,
        "max_active_bookings": None, "max_releases": None,
    },
}


def normalize_tier(tier: str) -> str:
    t = (tier or "").strip().lower().replace(" ", "_").replace("-", "_")
    if t in ("full", "label", "all_in"):
        t = "full_label"
    if t not in TIERS:
        raise GateError(f"unknown tier {tier!r}; tiers are {sorted(TIERS)}")
    return t


class Subscription:
    def __init__(self, artist_id: str, tier: str, period: str = "monthly"):
        self.artist_id = artist_id
        self.tier = normalize_tier(tier)
        self.period = period if period in ("monthly", "yearly") else "monthly"
        self.status = "active"  # active | past_due | suspended
        self.payments: list[dict] = []

    @property
    def price_cents(self) -> int:
        return TIERS[self.tier]["yearly_cents" if self.period == "yearly" else "monthly_cents"]

    def record_payment(self, amount_cents: int, ref: str = "") -> "Subscription":
        if amount_cents != self.price_cents:
            raise GateError(
                f"payment {amount_cents} does not match {self.tier} price {self.price_cents}")
        self.payments.append({"amount_cents": amount_cents, "ref": ref})
        self.status = "active"
        return self

    def mark_overdue(self) -> "Subscription":
        self.status = "past_due"
        return self

    def suspend(self) -> "Subscription":
        self.status = "suspended"
        return self

    def effective_tier(self) -> str:
        """Lapsed subscriptions fall back to Try gating for NEW work."""
        return "try" if self.status in ("past_due", "suspended") else self.tier

    def to_dict(self) -> dict:
        return {"artist_id": self.artist_id, "tier": self.tier,
                "period": self.period, "status": self.status,
                "payments": list(self.payments)}

    @classmethod
    def from_dict(cls, d: dict) -> "Subscription":
        s = cls(d["artist_id"], d["tier"], d.get("period", "monthly"))
        s.status = d.get("status", "active")
        s.payments = list(d.get("payments", []))
        return s
