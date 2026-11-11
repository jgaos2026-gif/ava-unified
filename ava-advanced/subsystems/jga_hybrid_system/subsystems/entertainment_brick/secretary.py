"""Secretary: drafts messages and decision prompts in a chosen personality/voice.

Deterministic templates only — no AI calls, no audio. (A "voice" here is the
written voice; text-to-speech is not included.)

Hard rules
- The secretary DRAFTS. It never approves, confirms, signs, pays or sends.
  A Draft reaches a MessageLog only when you call draft.send(...) yourself.
- Personality changes the wording around the facts, never the facts: ids,
  dates, amounts and statuses come from the same fact lines for every voice.
- "confirmed" wording is only producible for a booking that IS confirmed.
"""
from __future__ import annotations

from dataclasses import dataclass

from core import BookingState, GateError

PERSONALITIES = {
    "professional": {
        "label": "Professional", "sample": "Good day. Here is the update you requested.",
        "intro": {"offer": "Good day. A new booking offer has arrived.",
                  "confirmed": "Good day. A booking is now confirmed.",
                  "rejected": "Good day. A booking has been declined.",
                  "cancelled": "Good day. A confirmed booking has been cancelled.",
                  "payment": "Good day. A payment has cleared.",
                  "release": "Good day. Release status below.",
                  "brief": "Good day. Your summary follows."},
        "outro": {"offer": "Please let me know how you would like to proceed.",
                  "default": "Please let me know if you need anything further."},
    },
    "warm": {
        "label": "Warm & friendly", "sample": "Hey! Good news coming your way.",
        "intro": {"offer": "Hey! Someone wants to work with you.",
                  "confirmed": "Great news, it's locked in!",
                  "rejected": "Just a heads up, this one's been passed on.",
                  "cancelled": "Sorry, this one fell through.",
                  "payment": "Nice, money cleared!",
                  "release": "Here's where your release stands.",
                  "brief": "Here's how things look right now."},
        "outro": {"offer": "No rush. Tell me what feels right and I'll take it from there.",
                  "default": "I'm here whenever you need me."},
    },
    "blunt": {
        "label": "Blunt & direct", "sample": "Facts only. No fluff.",
        "intro": {"offer": "Offer in.", "confirmed": "Confirmed.", "rejected": "Declined.",
                  "cancelled": "Cancelled.", "payment": "Cleared.",
                  "release": "Release status.", "brief": "Status."},
        "outro": {"offer": "Your call.", "default": "That's all."},
    },
    "hype": {
        "label": "Hype manager", "sample": "Yo! Let's get this bag!",
        "intro": {"offer": "Yo! Offer just landed!",
                  "confirmed": "LET'S GO! It's official!",
                  "rejected": "We passed. Next one's better.",
                  "cancelled": "That one's off. We keep moving.",
                  "payment": "Money's in the building!",
                  "release": "Release check, let's go!",
                  "brief": "Scoreboard time!"},
        "outro": {"offer": "Say the word and we move.",
                  "default": "Keep stacking."},
    },
}


def money(cents: int) -> str:
    return f"${cents // 100:,}.{cents % 100:02d}"


@dataclass
class Draft:
    kind: str
    ref_id: str | None
    text: str
    personality: str

    def send(self, log, sender: str):
        """Explicit send into a MessageLog. Never called automatically."""
        if not self.ref_id:
            raise GateError("this draft is not tied to a booking or submission; it cannot be logged")
        return log.add(self.ref_id, sender, self.text)


class Secretary:
    def __init__(self, personality: str = "professional", name: str = "Secretary"):
        if personality not in PERSONALITIES:
            raise GateError(f"unknown personality {personality!r}; choices: {sorted(PERSONALITIES)}")
        if not isinstance(name, str) or not name.strip():
            raise GateError("secretary needs a name")
        self.personality, self.name = personality, name.strip()
        self._p = PERSONALITIES[personality]

    def _wrap(self, kind, facts, outro_kind=None):
        outro = self._p["outro"].get(outro_kind or kind, self._p["outro"]["default"])
        return f"{self._p['intro'][kind]}\n{facts}\n{outro}\n— {self.name}"

    @staticmethod
    def _b_facts(b):
        when = f" on {b.date}" if b.date else ""
        return (f"Booking {b.id}: {b.buyer} for \"{b.title}\"{when}. "
                f"Rate {money(b.rate_cents)} (your floor {money(b.artist.rate_floor_cents)}). "
                f"Status: {b.state.value}.")

    def offer(self, b) -> Draft:
        facts = self._b_facts(b)
        if b.state in (BookingState.OFFER, BookingState.DRAFT):
            facts += " Nothing is confirmed until you approve it."
        return Draft("offer", b.id, self._wrap("offer", facts), self.personality)

    def decision_prompt(self, b) -> Draft:
        """Numbered choices for the artist. Describes what each choice WOULD do."""
        if b.state not in (BookingState.OFFER, BookingState.DRAFT):
            raise GateError(f"{b.id} is {b.state.value}; no decision pending")
        steps = ["1) Move it to draft" if b.state == BookingState.OFFER else "1) Approve it (a separate step then confirms it)",
                 "2) Decline it (booking ends)",
                 "3) Hold and do nothing (no change)"]
        facts = self._b_facts(b) + "\nYour choices:\n" + "\n".join(steps)
        return Draft("decision", b.id, self._wrap("offer", facts), self.personality)

    def _state_draft(self, b, kind, state):
        if b.state != state:
            raise GateError(f"{b.id} is {b.state.value}, not {state.value}; refusing to draft '{kind}' wording")
        return Draft(kind, b.id, self._wrap(kind, self._b_facts(b)), self.personality)

    def confirmed(self, b): return self._state_draft(b, "confirmed", BookingState.CONFIRMED)
    def rejected(self, b): return self._state_draft(b, "rejected", BookingState.REJECTED)
    def cancelled(self, b): return self._state_draft(b, "cancelled", BookingState.CANCELLED)

    def payment(self, ledger, entry_id: str) -> Draft:
        e = ledger.entries[entry_id]
        h = ledger.head(entry_id)
        facts = (f"Ledger {e['id']} (ref {e['external_ref']}): {e['stage']} {money(h['cleared_cents'])}"
                 + (f" for {e['booking_id']}" if e["booking_id"] else "")
                 + f". Your pay reserve (V8): {money(h['split']['V8'])}. "
                   f"Collaborator cuts paid: {money(h.get('collaborator_cut_cents', 0))}. "
                   "Receipt only; no money was moved by this system.")
        return Draft("payment", e["booking_id"], self._wrap("payment", facts), self.personality)

    def release_status(self, r) -> Draft:
        probs = r.problems()
        facts = (f"Release {r.id} \"{r.title}\": "
                 + ("READY for a distributor (nothing has been sent)." if not probs
                    else "NOT ready. Missing: " + "; ".join(probs) + "."))
        return Draft("release", r.id, self._wrap("release", facts), self.personality)

    def brief(self, brick) -> Draft:
        s = brick.summary()
        states = ", ".join(f"{n} {k.lower()}" for k, n in sorted(s["bookings_by_state"].items())) or "no bookings"
        facts = (f"Bookings: {states}. Cleared gross {money(s['gross_cents'])}, "
                 f"collaborator cuts {money(s['collaborator_cuts_cents'])}, "
                 f"pay reserve V8 {money(s['vaults']['V8'])}. "
                 f"Releases ready: {s['releases_distributor_ready']}.")
        return Draft("brief", None, self._wrap("brief", facts), self.personality)


def choices() -> list[dict]:
    return [{"key": k, "label": v["label"], "sample": v["sample"]} for k, v in PERSONALITIES.items()]
