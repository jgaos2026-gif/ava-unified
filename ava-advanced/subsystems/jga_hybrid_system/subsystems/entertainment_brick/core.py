"""Entertainment Brick core: profile, booking with approval gate, messages.

Stdlib only. No money, no payout, no external calls.
A booking is never confirmed without explicit artist approval.

Identity note: approval accepts an artist auth_token (constant-time compare,
persisted in the 0600 store), which survives save/load. Without a token, the
legacy object-identity check applies. A token is a credential: the app layer
must deliver it to the artist over a secure channel and never log it.
"""
from __future__ import annotations

import hmac as _hmac
import secrets as _secrets
import threading as _threading
from dataclasses import dataclass, field
from datetime import date as _date, datetime, timezone
from enum import Enum

# One lock for the confirm/cancel date+time check-and-book step, so two
# confirms racing in a real server cannot both slip through the same slot.
_BOOKING_LOCK = _threading.RLock()

EXPENSE_CATEGORIES = (
    "travel", "taxes", "advertising", "pay", "wardrobe", "cds", "online",
)


class BookingState(str, Enum):
    OFFER = "OFFER"
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class GateError(ValueError):
    """Raised when an approval gate blocks an action."""


def _is_cents(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


_COUNTERS = {"book": 0, "art": 0, "rel": 0}


def _next_id(prefix: str) -> str:
    _COUNTERS[prefix] += 1
    return f"{prefix}-{_COUNTERS[prefix]:03d}"


def _restore_counter(prefix: str, ids) -> None:
    """After loading a store, make sure new ids never collide with loaded ones."""
    top = max((int(i.split("-")[1]) for i in ids), default=0)
    _COUNTERS[prefix] = max(_COUNTERS[prefix], top)


def _norm_date(d):
    if d is None:
        return None
    if isinstance(d, _date) and not isinstance(d, datetime):
        return d.isoformat()
    if isinstance(d, str):
        try:
            return _date.fromisoformat(d).isoformat()
        except ValueError:
            pass
    raise GateError("date must be an ISO date (YYYY-MM-DD) or None")


def _norm_time(t):
    """HH:MM as minutes since midnight, or None. Validates the format."""
    if t is None:
        return None
    if isinstance(t, str):
        parts = t.split(":")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            h, m = int(parts[0]), int(parts[1])
            if 0 <= h < 24 and 0 <= m < 60:
                return h * 60 + m
    raise GateError(f"time must be HH:MM, got {t!r}")


def _fmt_time(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}" if minutes is not None else None


@dataclass
class Artist:
    name: str
    discipline: str  # e.g. "music", "acting", "dance", "theatre", "film"
    style: str = ""
    location: str = ""
    available: bool = True
    rate_floor_cents: int = 0
    artist_id: str = field(default="", init=False)
    auth_token: str = field(default="", init=False, repr=False, compare=False)
    _confirmed_dates: set = field(default_factory=set, init=False, repr=False, compare=False)
    _confirmed_intervals: dict = field(default_factory=dict, init=False, repr=False, compare=False)

    def __post_init__(self):
        if not self.name or not self.discipline:
            raise GateError("artist needs a name and a discipline")
        if not isinstance(self.available, bool):
            raise GateError("available must be a bool")
        self.artist_id = _next_id("art")
        # Key-token identity: survives a save/load (the token is stored in
        # the 0600 store), unlike object identity, which breaks on load.
        # Treat this token like a password: never log it, never ship it
        # in a package. Rotation = set a new token; old tokens then fail.
        self.auth_token = _secrets.token_hex(16)
        if not _is_cents(self.rate_floor_cents) or self.rate_floor_cents < 0:
            raise GateError("rate floor must be a non-negative integer number of cents")

    def matches(self, discipline: str, location: str = "") -> bool:
        if self.discipline != discipline or not self.available:
            return False
        return not location or location == self.location


class Booking:
    """OFFER -> DRAFT -> APPROVED (artist) -> CONFIRMED. State is read-only
    from outside; every transition is logged in `history` with actor + time.
    """

    _ALLOWED = {
        (BookingState.OFFER, BookingState.DRAFT),
        (BookingState.DRAFT, BookingState.APPROVED),
        (BookingState.APPROVED, BookingState.CONFIRMED),
        (BookingState.CONFIRMED, BookingState.CANCELLED),
        (BookingState.OFFER, BookingState.REJECTED),
        (BookingState.DRAFT, BookingState.REJECTED),
        (BookingState.APPROVED, BookingState.REJECTED),
    }

    def __init__(self, artist: Artist, buyer: str, title: str, rate_cents: int,
                 date=None, start_time=None, end_time=None, buffer_minutes: int = 0):
        if not buyer or not title:
            raise GateError("booking needs a buyer and a title")
        if not artist.available:
            raise GateError(f"{artist.name} is not available for new bookings")
        self.date = _norm_date(date)
        self.start_time = _norm_time(start_time)
        self.end_time = _norm_time(end_time)
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise GateError("end_time must be after start_time")
        if not isinstance(buffer_minutes, int) or buffer_minutes < 0:
            raise GateError("buffer_minutes must be a non-negative integer")
        self.buffer_minutes = buffer_minutes
        if not _is_cents(rate_cents) or rate_cents < 0:
            raise GateError("rate must be a non-negative integer number of cents")
        if rate_cents < artist.rate_floor_cents:
            raise GateError("rate below artist rate floor")
        # Id is assigned only after validation, so failed constructions don't burn ids.
        self.id = _next_id("book")
        self.artist = artist
        self.buyer = buyer
        self.title = title
        self._rate_cents = rate_cents
        self._state = BookingState.OFFER
        self.history: list[dict] = []

    # -- read-only views (direct assignment raises AttributeError) --
    @property
    def state(self) -> BookingState:
        return self._state

    @property
    def rate_cents(self) -> int:
        return self._rate_cents

    def to_dict(self) -> dict:
        return {
            "id": self.id, "artist_id": self.artist.artist_id, "buyer": self.buyer,
            "title": self.title, "rate_cents": self._rate_cents, "date": self.date,
            "start_time": _fmt_time(self.start_time),
            "end_time": _fmt_time(self.end_time),
            "buffer_minutes": self.buffer_minutes,
            "state": self._state.value, "history": [dict(h) for h in self.history],
        }

    @classmethod
    def _restore(cls, d: dict, artist: Artist) -> "Booking":
        """Rebuild a booking from storage WITHOUT trusting its state: the stored
        history is replayed through the same transition + actor rules."""
        if d.get("artist_id") != artist.artist_id:
            raise GateError("stored booking does not belong to this artist")
        if not _is_cents(d.get("rate_cents")) or d["rate_cents"] < 0:
            raise GateError("stored rate invalid")
        b = object.__new__(cls)
        b.id, b.artist, b.buyer, b.title = d["id"], artist, d["buyer"], d["title"]
        b.date = _norm_date(d.get("date"))
        b.start_time = _norm_time(d.get("start_time"))
        b.end_time = _norm_time(d.get("end_time"))
        b.buffer_minutes = d.get("buffer_minutes", 0)
        b._rate_cents = d["rate_cents"]
        b._state = BookingState.OFFER
        b.history = []
        art, buy = f"artist:{artist.name}", f"buyer:{d['buyer']}"
        expect_actor = {
            BookingState.DRAFT: {"system"}, BookingState.CONFIRMED: {"system"},
            BookingState.APPROVED: {art}, BookingState.REJECTED: {art, buy},
            BookingState.CANCELLED: {art, buy},
        }
        for h in d.get("history", []):
            frm, to = BookingState(h["from"]), BookingState(h["to"])
            if frm != b._state or (frm, to) not in cls._ALLOWED:
                raise GateError(f"stored history of {b.id} has an illegal transition")
            if h["actor"] not in expect_actor[to]:
                raise GateError(f"stored history of {b.id}: {to.value} by {h['actor']!r} not allowed")
            if not h.get("at"):
                raise GateError(f"stored history of {b.id} missing timestamp")
            b.history.append(dict(h))
            b._state = to
        if b._state != BookingState(d["state"]):
            raise GateError(f"stored state of {b.id} does not match its history")
        if b._state == BookingState.CONFIRMED and b.date:
            if b.date in artist._confirmed_dates:
                raise GateError(f"stored bookings double-book {artist.name} on {b.date}")
            artist._confirmed_dates.add(b.date)
            artist._confirmed_intervals.setdefault(b.date, []).append(
                (b.start_time, b.end_time, b.buffer_minutes, b.id))
        return b

    def _go(self, new: BookingState, actor: str) -> None:
        self.history.append({
            "from": self._state.value, "to": new.value, "actor": actor,
            "at": datetime.now(timezone.utc).isoformat(),
        })
        self._state = new

    def _party(self, by) -> str:
        if by is self.artist:
            return f"artist:{self.artist.name}"
        if isinstance(by, str) and by and by == self.buyer:
            return f"buyer:{self.buyer}"
        raise GateError(f"booking {self.id}: actor is not a party to this booking")

    def _check_floor(self) -> None:
        # Floor is live: raising it after the offer blocks approval/confirmation.
        if self._rate_cents < self.artist.rate_floor_cents:
            raise GateError(f"booking {self.id}: rate below artist rate floor")

    def reprice(self, new_rate_cents: int):
        if self._state not in (BookingState.OFFER, BookingState.DRAFT):
            raise GateError(f"cannot reprice from {self._state}")
        if not _is_cents(new_rate_cents) or new_rate_cents < 0:
            raise GateError("rate must be a non-negative integer number of cents")
        if new_rate_cents < self.artist.rate_floor_cents:
            raise GateError("rate below artist rate floor")
        self._rate_cents = new_rate_cents
        return self

    def to_draft(self):
        if self._state != BookingState.OFFER:
            raise GateError(f"cannot draft from {self._state}")
        self._go(BookingState.DRAFT, "system")
        return self

    def approve(self, by: Artist, token: str = None):
        """Artist approval. Only the booking's own artist may approve.

        With a token, identity is the artist's auth_token (constant-time
        compare), so approval survives a save/load. Without a token, the
        legacy object-identity check applies (by must be the same object).
        """
        if token is not None:
            if not _hmac.compare_digest(str(token), self.artist.auth_token):
                raise GateError(f"booking {self.id}: approval token does not match")
        elif by is not self.artist:
            raise GateError(f"booking {self.id}: only the booked artist can approve")
        if self._state != BookingState.DRAFT:
            raise GateError(f"cannot approve from {self._state}")
        self._check_floor()
        actor = f"artist:{self.artist.name}" if token is not None else self._party(by)
        self._go(BookingState.APPROVED, actor)
        return self

    def reject(self, by):
        """Pre-confirmation decline by either party. Confirmed bookings must
        use cancel()."""
        who = self._party(by)
        if self._state not in (BookingState.OFFER, BookingState.DRAFT, BookingState.APPROVED):
            raise GateError(f"cannot reject from {self._state}")
        self._go(BookingState.REJECTED, who)
        return self

    def cancel(self, by):
        who = self._party(by)
        if self._state != BookingState.CONFIRMED:
            raise GateError(f"cannot cancel from {self._state}; only confirmed bookings cancel")
        with _BOOKING_LOCK:
            self._go(BookingState.CANCELLED, who)
            if self.date in self.artist._confirmed_intervals:
                self.artist._confirmed_intervals[self.date] = [
                    iv for iv in self.artist._confirmed_intervals[self.date]
                    if iv[3] != self.id
                ]
                if not self.artist._confirmed_intervals[self.date]:
                    self.artist._confirmed_dates.discard(self.date)
        return self

    def confirm(self):
        # The approval gate: confirmation requires an approved draft.
        if self._state != BookingState.APPROVED:
            raise GateError(
                f"booking {self.id} cannot confirm from {self._state}: "
                "artist approval required"
            )
        self._check_floor()
        with _BOOKING_LOCK:
            if self.date:
                if self.start_time is None or self.end_time is None:
                    if self.date in self.artist._confirmed_dates:
                        raise GateError(
                            f"booking {self.id}: {self.artist.name} already has a "
                            f"confirmed booking on {self.date}"
                        )
                else:
                    for (s, e, buf, bid) in self.artist._confirmed_intervals.get(self.date, []):
                        if s is None or e is None:
                            raise GateError(
                                f"booking {self.id}: {self.artist.name} already has a "
                                f"confirmed booking on {self.date}"
                            )
                        lo = self.start_time - self.buffer_minutes
                        hi = self.end_time + self.buffer_minutes
                        if lo < e + buf and s - buf < hi:
                            raise GateError(
                                f"booking {self.id}: overlaps confirmed booking "
                                f"{bid} on {self.date}"
                            )
            self._go(BookingState.CONFIRMED, "system")
            if self.date:
                self.artist._confirmed_dates.add(self.date)
                self.artist._confirmed_intervals.setdefault(self.date, []).append(
                    (self.start_time, self.end_time, self.buffer_minutes, self.id))
        return self


@dataclass
class Message:
    booking_id: str
    sender: str
    body: str


class MessageLog:
    """Every message belongs to a REGISTERED booking or submission. No orphans.

    Pass a Booking to add() (auto-registers) or register a submission id first.
    """

    def __init__(self):
        self.messages: list[Message] = []
        self._known: set[str] = set()

    def register(self, ref) -> str:
        ref_id = ref.id if isinstance(ref, Booking) else ref
        if not isinstance(ref_id, str) or not ref_id:
            raise GateError("booking or submission id must be a non-empty string")
        self._known.add(ref_id)
        return ref_id

    def add(self, ref, sender: str, body: str) -> Message:
        if isinstance(ref, Booking):
            ref_id = self.register(ref)
        else:
            ref_id = ref
        if not ref_id:
            raise GateError("message requires a booking or submission id")
        if ref_id not in self._known:
            raise GateError(f"unknown booking or submission id: {ref_id!r}")
        if not sender or not body:
            raise GateError("message requires a sender and a body")
        msg = Message(booking_id=ref_id, sender=sender, body=body)
        self.messages.append(msg)
        return msg

    def for_booking(self, booking_id: str) -> list[Message]:
        return [m for m in self.messages if m.booking_id == booking_id]


@dataclass
class Expense:
    category: str
    amount_cents: int
    note: str = ""

    def __post_init__(self):
        if self.category not in EXPENSE_CATEGORIES:
            raise GateError(f"unknown expense category: {self.category}")
        if not _is_cents(self.amount_cents):
            raise GateError("expense amount must be an integer number of cents")
        if self.amount_cents < 0:
            raise GateError("expense amount cannot be negative")


class ExpenseTracker:
    def __init__(self):
        self.expenses: list[Expense] = []

    def add(self, category: str, amount_cents: int, note: str = "") -> Expense:
        expense = Expense(category, amount_cents, note)
        self.expenses.append(expense)
        return expense

    def total_by_category(self) -> dict[str, int]:
        totals = {c: 0 for c in EXPENSE_CATEGORIES}
        for e in self.expenses:
            totals[e.category] += e.amount_cents
        return totals
