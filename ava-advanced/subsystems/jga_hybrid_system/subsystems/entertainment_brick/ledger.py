"""Receipt ledger: wires cleared money to bookings and chains receipts.

Receipt-only. No bank movement. The ledger is the ONLY supported way to take
cuts, because it holds the single current ("head") receipt per cleared event,
so a stale receipt can never be replayed for a second cut.

Rules
- Every cleared event needs a unique external_ref (e.g. the processor's
  transaction id). Re-recording the same ref is refused (no double counting).
- gig-pay-cleared must reference a CONFIRMED booking, and the cumulative
  cleared gig pay for that booking may not exceed the agreed rate.
- merch-cleared / payout-cleared may stand alone or reference a booking.
"""
from __future__ import annotations

import money
from core import BookingState, GateError


class LedgerError(ValueError):
    pass


class Ledger:
    def __init__(self, bookings: dict, key=None):
        self._bookings = bookings          # shared with Brick: id -> Booking
        self._key = money.resolve_key(key)
        self.entries: dict[str, dict] = {}
        self._refs: set[str] = set()

    def _new_id(self) -> str:
        return f"led-{len(self.entries) + 1:04d}"

    def record(self, external_ref: str, cleared_cents: int, stage: str,
               booking_id: str | None = None) -> dict:
        if not isinstance(external_ref, str) or not external_ref.strip():
            raise LedgerError("external_ref is required")
        external_ref = external_ref.strip()
        if external_ref in self._refs:
            raise LedgerError(f"external_ref {external_ref!r} already recorded")
        if booking_id is not None:
            b = self._bookings.get(booking_id)
            if b is None:
                raise LedgerError(f"unknown booking {booking_id!r}")
        if stage == "gig-pay-cleared":
            if booking_id is None:
                raise LedgerError("gig-pay-cleared must reference a booking")
            if b.state != BookingState.CONFIRMED:
                raise LedgerError(f"booking {booking_id} is {b.state.value}; gig pay clears only against CONFIRMED")
            already = sum(e["receipts"][0]["cleared_cents"] for e in self.entries.values()
                          if e["booking_id"] == booking_id and e["stage"] == stage)
            if isinstance(cleared_cents, int) and not isinstance(cleared_cents, bool) \
                    and already + cleared_cents > b.rate_cents:
                raise LedgerError(
                    f"cleared gig pay {already + cleared_cents} would exceed booking rate {b.rate_cents}")
        receipt = money.split_cleared(cleared_cents, stage, key=self._key)
        entry = {"id": self._new_id(), "external_ref": external_ref,
                 "booking_id": booking_id, "stage": stage, "receipts": [receipt]}
        self.entries[entry["id"]] = entry
        self._refs.add(external_ref)
        return entry

    def head(self, entry_id: str) -> dict:
        try:
            return self.entries[entry_id]["receipts"][-1]
        except KeyError:
            raise LedgerError(f"unknown ledger entry {entry_id!r}") from None

    def pay_cut(self, entry_id: str, cut_cents: int, payee: str) -> dict:
        new = money.pay_collaborator_cut(self.head(entry_id), cut_cents, payee, key=self._key)
        self.entries[entry_id]["receipts"].append(new)
        return new

    def vault_totals(self) -> dict:
        totals = {f"V{i}": 0 for i in range(1, 12)}
        gross = cuts = 0
        for e in self.entries.values():
            h = e["receipts"][-1]
            gross += h["cleared_cents"]
            cuts += h.get("collaborator_cut_cents", 0)
            for k, v in h["split"].items():
                totals[k] += v
        assert sum(totals.values()) + cuts == gross
        return {"gross_cents": gross, "collaborator_cuts_cents": cuts, "vaults": totals}

    # -- persistence --
    def to_dict(self) -> dict:
        return {"entries": [dict(e, receipts=[dict(r) for r in e["receipts"]])
                            for e in self.entries.values()]}

    def load(self, d: dict) -> None:
        self.entries.clear()
        self._refs.clear()
        for e in d.get("entries", []):
            receipts = e["receipts"]
            if not receipts:
                raise LedgerError(f"entry {e.get('id')} has no receipts")
            prev = None
            for r in receipts:
                money.verify(r, self._key)
                money.verify_receipt_structure(r)
                if prev is None:
                    if r.get("cuts"):
                        raise LedgerError(f"entry {e['id']}: first receipt already has cuts")
                else:
                    ok = (r["cleared_cents"] == prev["cleared_cents"] and r["stage"] == prev["stage"]
                          and r["cuts"][:-1] == prev.get("cuts", []) and len(r["cuts"]) == len(prev.get("cuts", [])) + 1)
                    if not ok:
                        raise LedgerError(f"entry {e['id']}: receipt chain is broken")
                prev = r
            if receipts[0]["stage"] != e["stage"]:
                raise LedgerError(f"entry {e['id']}: stage mismatch")
            if e["external_ref"] in self._refs:
                raise LedgerError(f"duplicate external_ref {e['external_ref']!r} in store")
            if e["booking_id"] is not None and e["booking_id"] not in self._bookings:
                raise LedgerError(f"entry {e['id']} references unknown booking")
            self._refs.add(e["external_ref"])
            self.entries[e["id"]] = {"id": e["id"], "external_ref": e["external_ref"],
                                     "booking_id": e["booking_id"], "stage": e["stage"],
                                     "receipts": [dict(r) for r in receipts]}
        # cap re-check: cumulative gig pay per booking
        per = {}
        for e in self.entries.values():
            if e["stage"] == "gig-pay-cleared":
                per[e["booking_id"]] = per.get(e["booking_id"], 0) + e["receipts"][0]["cleared_cents"]
        for bid, total in per.items():
            if total > self._bookings[bid].rate_cents:
                raise LedgerError(f"stored gig pay for {bid} exceeds its rate")
