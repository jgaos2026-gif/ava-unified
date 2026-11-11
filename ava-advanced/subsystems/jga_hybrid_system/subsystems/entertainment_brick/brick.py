"""Brick: one object that owns artists, bookings, messages, expenses, releases
and the ledger, with tamper-evident save/load.

Persistence trust level matches money.py: without a key the file hash is plain
SHA-256 (detects corruption and naive edits, not a determined forger); with
JGA_RECEIPT_KEY / key= the whole file is HMAC-sealed. Either way, load does not
trust stored state: bookings replay their history through the real gates and
every receipt is re-verified and re-derived.
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
import tempfile
import threading

import money
from core import (Artist, Booking, ExpenseTracker, GateError, MessageLog,
                  _restore_counter)
from ledger import Ledger
from music import Release
from publisher import Publisher, PublishError
from secretary import PERSONALITIES, Secretary
from tiers import TIERS, Subscription, normalize_tier

STORE_VERSION = 1


class StoreError(ValueError):
    pass


class Brick:
    def __init__(self, key=None):
        self._key = money.resolve_key(key)
        self._lock = threading.RLock()
        self.artists: dict[str, Artist] = {}
        self.bookings: dict[str, Booking] = {}
        self.releases: dict[str, Release] = {}
        self.log = MessageLog()
        self.expenses = ExpenseTracker()
        self.ledger = Ledger(self.bookings, key=self._key)
        self.publisher = Publisher(self.releases, self.artists)
        self._secretaries: dict[str, dict] = {}   # artist_id -> {personality, name}
        self.subscriptions: dict[str, Subscription] = {}
        self._tiers: dict[str, str] = {}  # artist_id -> tier (when assigned)

    # ---- tiers + billing ledger (no payment processor; see tiers.py) ----
    def set_tier(self, artist_id: str, tier: str) -> str:
        if artist_id not in self.artists:
            raise GateError(f"unknown artist {artist_id!r}")
        self._tiers[artist_id] = normalize_tier(tier)
        return self._tiers[artist_id]

    def tier_for(self, artist_id: str) -> str:
        sub = self.subscriptions.get(artist_id)
        if sub is not None:
            return sub.effective_tier()
        return self._tiers.get(artist_id)

    def _check_tier_cap(self, artist: Artist, kind: str) -> None:
        tier = self.tier_for(artist.artist_id)
        if tier is None:
            return  # tier not assigned yet: legacy, uncapped
        cap = TIERS[tier]["max_active_bookings" if kind == "booking" else "max_releases"]
        if cap is None:
            return
        if kind == "booking":
            active = sum(
                1 for b in self.bookings.values()
                if b.artist.artist_id == artist.artist_id
                and b.state.value not in ("REJECTED", "CANCELLED"))
            if active >= cap:
                raise GateError(f"{tier} tier allows {cap} active bookings; this would be {active + 1}")
        else:
            count = sum(1 for r in self.releases.values() if r.artist == artist.name)
            if count >= cap:
                raise GateError(f"{tier} tier allows {cap} release prep(s); this would be {count + 1}")

    def subscribe(self, artist_id: str, tier: str, period: str = "monthly") -> Subscription:
        if artist_id not in self.artists:
            raise GateError(f"unknown artist {artist_id!r}")
        sub = Subscription(artist_id, tier, period)
        self.subscriptions[artist_id] = sub
        self._tiers[artist_id] = sub.tier
        return sub

    def record_subscription_payment(self, artist_id: str, amount_cents: int, ref: str = "") -> Subscription:
        sub = self.subscriptions.get(artist_id)
        if sub is None:
            raise GateError(f"no subscription for {artist_id!r}")
        return sub.record_payment(amount_cents, ref)

    def mark_subscription_overdue(self, artist_id: str) -> Subscription:
        sub = self.subscriptions.get(artist_id)
        if sub is None:
            raise GateError(f"no subscription for {artist_id!r}")
        return sub.mark_overdue()

    # ---- profile vault ----
    def add_artist(self, name, discipline, **kw) -> Artist:
        a = Artist(name, discipline, **kw)
        self.artists[a.artist_id] = a
        return a

    def search(self, discipline: str, location: str = "") -> list[Artist]:
        return [a for a in self.artists.values() if a.matches(discipline, location)]

    # ---- secretary (drafts only; see secretary.py) ----
    def set_secretary(self, artist_id: str, personality: str, name: str = "Secretary") -> Secretary:
        if artist_id not in self.artists:
            raise GateError(f"unknown artist {artist_id!r}")
        sec = Secretary(personality, name)           # validates the choice
        self._secretaries[artist_id] = {"personality": sec.personality, "name": sec.name}
        return sec

    def secretary_for(self, artist_id: str) -> Secretary:
        if artist_id not in self.artists:
            raise GateError(f"unknown artist {artist_id!r}")
        c = self._secretaries.get(artist_id)
        return Secretary(c["personality"], c["name"]) if c else Secretary()

    # ---- tenant isolation + key rotation ----
    def get_booking_for(self, artist_id: str, booking_id: str) -> Booking:
        """Artist A cannot read Artist B's booking, even with a valid id."""
        b = self.bookings.get(booking_id)
        if b is None:
            raise GateError(f"unknown booking {booking_id!r}")
        if b.artist.artist_id != artist_id:
            raise GateError("booking belongs to another artist")
        return b

    def approve_booking(self, artist_id: str, booking_id: str, token: str) -> Booking:
        """Tenant-checked approval: the artist id, the booking's artist,
        and the auth token must all agree, or nothing happens."""
        b = self.get_booking_for(artist_id, booking_id)
        artist = self.artists[artist_id]
        return b.approve(artist, token=token)

    def rotate_artist_token(self, artist_id: str, old_token: str) -> str:
        """Key rotation: the current token is required to mint a new one;
        the old token stops working immediately after rotation."""
        artist = self.artists.get(artist_id)
        if artist is None:
            raise GateError(f"unknown artist {artist_id!r}")
        if not hmac.compare_digest(str(old_token), artist.auth_token):
            raise GateError("current token does not match; rotation refused")
        artist.auth_token = secrets.token_hex(16)
        return artist.auth_token

    # ---- booking loop ----
    def offer(self, artist_id: str, buyer: str, title: str, rate_cents: int, date=None,
              start_time=None, end_time=None, buffer_minutes: int = 0) -> Booking:
        artist = self.artists.get(artist_id)
        if artist is None:
            raise GateError(f"unknown artist {artist_id!r}")
        with self._lock:
            self._check_tier_cap(artist, "booking")
            b = Booking(artist, buyer, title, rate_cents, date,
                        start_time=start_time, end_time=end_time,
                        buffer_minutes=buffer_minutes)
            self.bookings[b.id] = b
            self.log.register(b)
        return b

    def message(self, ref_id: str, sender: str, body: str):
        return self.log.add(ref_id, sender, body)

    # ---- music ----
    def add_release(self, title: str, artist: str, **kw) -> Release:
        # Tier cap by artist name, matching how releases are keyed here.
        for a in self.artists.values():
            if a.name == artist:
                self._check_tier_cap(a, "release")
        r = Release(title, artist, **kw)
        self.releases[r.id] = r
        self.log.register(r.id)   # submissions can carry messages too
        return r

    # ---- money ----
    def record_cleared(self, external_ref, cleared_cents, stage, booking_id=None):
        return self.ledger.record(external_ref, cleared_cents, stage, booking_id)

    def pay_cut(self, entry_id, cut_cents, payee):
        return self.ledger.pay_cut(entry_id, cut_cents, payee)

    def summary(self) -> dict:
        t = self.ledger.vault_totals()
        t["expenses_by_category_cents"] = self.expenses.total_by_category()
        t["bookings_by_state"] = {}
        for b in self.bookings.values():
            t["bookings_by_state"][b.state.value] = t["bookings_by_state"].get(b.state.value, 0) + 1
        t["releases_distributor_ready"] = sum(r.distributor_ready() for r in self.releases.values())
        return t

    # ---- persistence ----
    def to_dict(self) -> dict:
        return {
            "version": STORE_VERSION,
            "artists": [{"artist_id": a.artist_id, "name": a.name, "discipline": a.discipline,
                         "style": a.style, "location": a.location, "available": a.available,
                         "rate_floor_cents": a.rate_floor_cents,
                         "auth_token": a.auth_token} for a in self.artists.values()],
            "tiers": dict(self._tiers),
            "subscriptions": [s.to_dict() for s in self.subscriptions.values()],
            "bookings": [b.to_dict() for b in self.bookings.values()],
            "releases": [r.to_dict() for r in self.releases.values()],
            "messages": [{"booking_id": m.booking_id, "sender": m.sender, "body": m.body}
                         for m in self.log.messages],
            "expenses": [{"category": e.category, "amount_cents": e.amount_cents, "note": e.note}
                         for e in self.expenses.expenses],
            "ledger": self.ledger.to_dict(),
            "publish_jobs": [j.to_dict() for j in self.publisher.jobs.values()],
            "secretaries": {k: dict(v) for k, v in self._secretaries.items()},
        }

    def save(self, path: str) -> None:
        doc = money.seal(self.to_dict(), self._key)
        directory = os.path.dirname(os.path.abspath(path))
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".brick-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(doc, f, sort_keys=True, indent=1)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)      # atomic: a crash never leaves a half-written store
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    @classmethod
    def load_production(cls, path: str, key) -> "Brick":
        """Production load: a key is mandatory. Plain-SHA256 stores are
        refused automatically by money.verify when a key is configured,
        so a downgraded/unsealed store cannot be loaded as production."""
        if not key:
            raise StoreError("production load requires a receipt key (JGA_RECEIPT_KEY)")
        return cls.load(path, key=key)

    @classmethod
    def load(cls, path: str, key=None) -> "Brick":
        try:
            with open(path) as f:
                doc = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise StoreError(f"cannot read store: {e}") from e
        brick = cls(key=key)
        try:
            money.verify(doc, brick._key)
            if doc.get("version") != STORE_VERSION:
                raise StoreError(f"unsupported store version {doc.get('version')!r}")
            for a in doc["artists"]:
                art = Artist(a["name"], a["discipline"], a["style"], a["location"],
                             a["available"], a["rate_floor_cents"])
                art.artist_id = a["artist_id"]
                # Old stores have no token: mint one on load (old tokens
                # did not exist, so nothing is invalidated by this).
                art.auth_token = a.get("auth_token") or secrets.token_hex(16)
                if a["artist_id"] in brick.artists:
                    raise StoreError("duplicate artist id")
                brick.artists[art.artist_id] = art
            for d in doc["bookings"]:
                artist = brick.artists.get(d["artist_id"])
                if artist is None or d["id"] in brick.bookings:
                    raise StoreError(f"booking {d.get('id')} has unknown artist or duplicate id")
                b = Booking._restore(d, artist)
                brick.bookings[b.id] = b
                brick.log.register(b)
            for d in doc["releases"]:
                r = Release.from_dict(d)
                if r.id in brick.releases:
                    raise StoreError("duplicate release id")
                brick.releases[r.id] = r
                brick.log.register(r.id)
            for m in doc["messages"]:
                brick.log.add(m["booking_id"], m["sender"], m["body"])
            for e in doc["expenses"]:
                brick.expenses.add(e["category"], e["amount_cents"], e["note"])
            brick.ledger.load(doc["ledger"])
            brick.publisher.load(doc.get("publish_jobs", []))
            for aid, tier in doc.get("tiers", {}).items():
                if aid in brick.artists:
                    brick._tiers[aid] = normalize_tier(tier)
            for d in doc.get("subscriptions", []):
                sub = Subscription.from_dict(d)
                if sub.artist_id in brick.artists:
                    brick.subscriptions[sub.artist_id] = sub
                    brick._tiers[sub.artist_id] = sub.tier
            for aid, c in doc.get("secretaries", {}).items():   # optional: older stores lack it
                brick.set_secretary(aid, c["personality"], c["name"])
        except StoreError:
            raise
        except (money.MoneyError, GateError, PublishError, ValueError, KeyError, TypeError) as e:
            raise StoreError(f"store rejected: {e}") from e
        _restore_counter("art", brick.artists)
        _restore_counter("book", brick.bookings)
        _restore_counter("rel", brick.releases)
        return brick
