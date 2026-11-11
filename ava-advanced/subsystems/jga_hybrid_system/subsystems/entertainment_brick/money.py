"""Entertainment Brick money module — Option B (John's ruling, 2026-11-02).

Rule: split the FULL cleared gross with the 11-way split (11VT), then pay
any collaborator/manager cut OUT OF V8 (artist/owner pay reserve) only.
Other reserves are never reduced by a collaborator cut.

Receipt-only. No bank movement, no payment execution, no sub-accounts.
A "cut payment" here is a receipted allocation, not money sent anywhere.

Cleared-only stages (music, replacing Brick 1 deposit/final stages):
  gig-pay-cleared, merch-cleared, payout-cleared
Any other stage, or a negative amount, is refused.

Receipt integrity
-----------------
Every receipt carries `receipt_hash`. `pay_collaborator_cut` VERIFIES the
incoming receipt (hash, structure, and a full recomputation of the split from
the gross) before touching it, and raises MoneyError on any mismatch.

Trust level: with no key configured the hash is plain SHA-256 — it catches
accidental or naive tampering, but anyone can recompute it, so it is NOT
authentication. Set JGA_RECEIPT_KEY (or pass key=) to seal receipts with
HMAC-SHA256; once a key is configured, unsealed receipts are refused
(no downgrade).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from decimal import Decimal, ROUND_HALF_UP

# V7's 12% is a TARGET rate, not a fixed amount: split_cleared computes
# V7 as the residual (gross minus the other ten vaults), so the split always
# sums exactly to the gross. Calling it both "12%" and "plug" without this
# note was the documentation bug; the code was already the plug.
RATES = {
    "V1": Decimal("0.15"),
    "V2": Decimal("0.075"),
    "V3": Decimal("0.035"),
    "V4": Decimal("0.05"),
    "V5": Decimal("0.02"),
    "V6": Decimal("0.15"),
    "V7": Decimal("0.12"),
    "V8": Decimal("0.20"),
    "V9": Decimal("0.10"),
    "V10": Decimal("0.08"),
    "V11": Decimal("0.02"),
}
assert sum(RATES.values()) == Decimal("1")  # import-time config check

CLEARED_STAGES = ("gig-pay-cleared", "merch-cleared", "payout-cleared")

BANKING_EXECUTION = "NONE_LEDGER_RECEIPT_ONLY"
TAX_DISCLAIMER = "INTERNAL_RESERVE_TARGETS_NOT_STATUTORY_TAX_LIABILITY"
V7_PLUG_NOTICE = "ABSORBS_PENNY_ROUNDING_DELTAS"
COLLABORATOR_RULE = "OPTION_B_SPLIT_GROSS_PAY_FROM_V8"

KEY_ENV = "JGA_RECEIPT_KEY"
MODE_SHA = "SHA256"
MODE_HMAC = "HMAC-SHA256"


class MoneyError(ValueError):
    pass


def _is_cents(x) -> bool:
    """True int only: bool is an int subclass and must not pass."""
    return isinstance(x, int) and not isinstance(x, bool)


def _cents(amount: Decimal) -> int:
    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


# ---- sealing / verification -------------------------------------------------

def _resolve_key(key):
    if key is None:
        env = os.environ.get(KEY_ENV)
        return env.encode() if env else None
    if isinstance(key, str):
        key = key.encode()
    if not isinstance(key, (bytes, bytearray)) or not key:
        raise MoneyError("receipt key must be non-empty bytes or str")
    return bytes(key)


def _digest(body: dict, key) -> str:
    payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    if body.get("hash_mode") == MODE_HMAC:
        return hmac.new(key, payload, hashlib.sha256).hexdigest()
    return hashlib.sha256(payload).hexdigest()


def _seal(receipt: dict, key) -> dict:
    receipt = dict(receipt)
    receipt.pop("receipt_hash", None)
    receipt["hash_mode"] = MODE_HMAC if key else MODE_SHA
    receipt["receipt_hash"] = _digest(receipt, key)
    return receipt


def _verify(receipt, key) -> None:
    if not isinstance(receipt, dict):
        raise MoneyError("receipt must be a dict")
    claimed = receipt.get("receipt_hash")
    mode = receipt.get("hash_mode")
    if not isinstance(claimed, str) or mode not in (MODE_SHA, MODE_HMAC):
        raise MoneyError("receipt is unsealed: missing receipt_hash/hash_mode")
    if key and mode != MODE_HMAC:
        raise MoneyError("receipt key configured but receipt is not HMAC-sealed")
    if mode == MODE_HMAC and not key:
        raise MoneyError("receipt is HMAC-sealed but no key is configured")
    body = {k: v for k, v in receipt.items() if k != "receipt_hash"}
    if not hmac.compare_digest(claimed, _digest(body, key)):
        raise MoneyError("receipt hash mismatch: receipt was altered or forged")


def _verify_structure(receipt: dict) -> None:
    """Re-derive the split from the gross; refuse any receipt that disagrees."""
    stage, gross = receipt.get("stage"), receipt.get("cleared_cents")
    if stage not in CLEARED_STAGES or not _is_cents(gross) or gross < 0:
        raise MoneyError("receipt has invalid stage or gross")
    split = receipt.get("split")
    if not isinstance(split, dict) or set(split) != set(RATES):
        raise MoneyError("receipt split must contain exactly V1..V11")
    if not all(_is_cents(v) and v >= 0 for v in split.values()):
        raise MoneyError("receipt split values must be non-negative integer cents")
    cuts = receipt.get("cuts", [])
    if not isinstance(cuts, list) or not all(
        isinstance(c, dict) and _is_cents(c.get("cents")) and c["cents"] > 0 for c in cuts
    ):
        raise MoneyError("receipt cuts malformed")
    cut_total = sum(c["cents"] for c in cuts)
    if receipt.get("collaborator_cut_cents", 0) != cut_total:
        raise MoneyError("receipt cumulative cut does not match cut history")
    original = split_cleared(gross, stage)["split"]
    for vault, cents in split.items():
        expected = original[vault] - (cut_total if vault == "V8" else 0)
        if cents != expected:
            raise MoneyError(f"receipt {vault} does not match the 11VT split of its gross")


# ---- public API -------------------------------------------------------------

def split_cleared(cleared_cents: int, stage: str, key=None) -> dict:
    """Split a cleared amount across all 11 vaults. V7 absorbs rounding."""
    if stage not in CLEARED_STAGES:
        raise MoneyError(f"stage not cleared: {stage!r}; cleared stages are {CLEARED_STAGES}")
    if not _is_cents(cleared_cents) or cleared_cents < 0:
        raise MoneyError("cleared amount must be a non-negative integer number of cents")

    total = Decimal(cleared_cents)
    split = {}
    for vault, rate in RATES.items():
        if vault == "V7":
            continue
        split[vault] = _cents(total * rate)
    # V7 plug: whatever remains, so the split always sums exactly.
    split["V7"] = cleared_cents - sum(split.values())
    if split["V7"] < 0:
        raise MoneyError("rounding plug went negative; split rejected")

    ordered = {k: split[k] for k in [f"V{i}" for i in range(1, 12)]}
    if sum(ordered.values()) != cleared_cents:
        raise MoneyError("split does not sum to gross")
    return _seal({
        "cleared_cents": cleared_cents,
        "stage": stage,
        "split": ordered,
        "cuts": [],
        "banking_execution": BANKING_EXECUTION,
        "tax_disclaimer": TAX_DISCLAIMER,
        "v7_plug_notice": V7_PLUG_NOTICE,
        "collaborator_rule": COLLABORATOR_RULE,
    }, _resolve_key(key))


def pay_collaborator_cut(split_receipt: dict, cut_cents: int, payee: str, key=None) -> dict:
    """Pay a collaborator/manager cut out of V8 only (Option B).

    The incoming receipt is verified first (hash + full recomputation).
    Other reserves are unchanged. The cut must be positive, name a payee, and
    not exceed the current V8 balance. Returns a new receipt; the input is
    not mutated.
    """
    key = _resolve_key(key)
    _verify(split_receipt, key)
    _verify_structure(split_receipt)

    if not _is_cents(cut_cents) or cut_cents <= 0:
        raise MoneyError("cut must be a positive integer number of cents")
    if not isinstance(payee, str) or not payee.strip():
        raise MoneyError("a collaborator cut requires a named payee")
    v8 = split_receipt["split"]["V8"]
    if cut_cents > v8:
        raise MoneyError(f"cut {cut_cents} exceeds V8 balance {v8}; refused")

    split = dict(split_receipt["split"])
    split["V8"] = v8 - cut_cents
    cuts = list(split_receipt.get("cuts", [])) + [{"payee": payee.strip(), "cents": cut_cents}]
    cumulative_cut = sum(c["cents"] for c in cuts)
    receipt = {
        "cleared_cents": split_receipt["cleared_cents"],
        "stage": split_receipt["stage"],
        "split": split,
        "cuts": cuts,
        "collaborator_cut_cents": cumulative_cut,
        "last_cut_cents": cut_cents,
        "collaborator_payee": payee.strip(),
        "artist_net_from_v8_cents": split["V8"],
        "other_reserves_cents": sum(v for k, v in split.items() if k != "V8"),
        "banking_execution": BANKING_EXECUTION,
        "tax_disclaimer": TAX_DISCLAIMER,
        "v7_plug_notice": V7_PLUG_NOTICE,
        "collaborator_rule": COLLABORATOR_RULE,
    }
    # Accounting identity: other reserves + V8 after cut + cumulative cut = gross.
    if (receipt["other_reserves_cents"] + receipt["artist_net_from_v8_cents"]
            + cumulative_cut != receipt["cleared_cents"]):
        raise MoneyError("accounting identity violated; receipt rejected")
    return _seal(receipt, key)


# Public helpers reused by ledger/store (same sealing scheme everywhere).
resolve_key = _resolve_key
seal = _seal
verify = _verify
verify_receipt_structure = _verify_structure
is_cents = _is_cents
