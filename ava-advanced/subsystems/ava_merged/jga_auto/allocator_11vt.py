"""
11VT Receipt-Only Allocation Module for JGA Full-Auto / System B.

Calculates internal reserve targets per cleared payment.
DOES NOT MOVE BANK FUNDS. DOES NOT SUBSTITUTE FOR TAX FILINGS.
DOES NOT OPEN SUB-ACCOUNTS. DOES NOT CLAIM BLUEVINE MOVES MONEY.

Policy, enforced in code:
  - Trigger on cleared payments ONLY: a 35% deposit event or a 65%
    final-balance event, never on a full contract price before funds
    exist. build_invoice() additionally requires deposit_cleared and
    final_paid before any split is computed.
  - Percentages are INTERNAL RESERVE TARGETS, not statutory tax
    liability, not a reasonable-salary determination, and not a
    filing. Tax, salary, and filing decisions still need a CPA /
    attorney and the actual statutory calculation.
  - V10 is INTERNAL_CAPITAL_RESERVE only. No succession trust is
    assumed, referenced, or relied on until an attorney executes
    the instruments.
  - V7 (Daily OPEX) absorbs penny-rounding deltas, so a split always
    balances to the cleared amount, and V7 is not always exactly 12%.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict

# Allocation percentages totaling exactly 1.000
VAULT_TARGETS: Dict[str, Dict[str, Any]] = {
    "V1_FED_TAX_RESERVE": {"name": "Federal Tax Target", "rate": Decimal("0.150")},
    "V2_STATE_TAX_RESERVE": {"name": "State Tax Target", "rate": Decimal("0.075")},
    "V3_GATEWAY_FEES": {"name": "Platform & Gateway Fees", "rate": Decimal("0.035")},
    "V4_CHARGEBACK_BUFFER": {"name": "Dispute & Chargeback Buffer", "rate": Decimal("0.050")},
    "V5_STATUTORY_RESERVE": {"name": "Corporate Maintenance Reserve", "rate": Decimal("0.020")},
    "V6_COGS_PRODUCTION": {"name": "Direct COGS & Compute", "rate": Decimal("0.150")},
    "V7_DAILY_OPEX": {"name": "Daily OPEX (Rounding Plug)", "rate": Decimal("0.120")},
    "V8_OWNER_W2_RESERVE": {"name": "Owner W-2 Salary Reserve Target", "rate": Decimal("0.200")},
    "V9_RD_COMPUTE": {"name": "R&D & Compute Scaling", "rate": Decimal("0.100")},
    "V10_CAPITAL_RESERVE": {"name": "Internal Capital Reserve", "rate": Decimal("0.080")},
    "V11_CIVIC_RESERVE": {"name": "Civic & Giving Reserve", "rate": Decimal("0.020")},
}

ALLOWED_STAGES = ("DEPOSIT_CLEARED_35", "FINAL_PAID_65")


def cent_round(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def allocate_cleared_payment(amount_cents: int, payment_stage: str, job_id: str) -> Dict[str, Any]:
    """
    Splits an actual cleared payment (cents) across 11 reserve vaults.
    Penny deltas from rounding are absorbed by V7 (OPEX).
    """
    if payment_stage not in ALLOWED_STAGES:
        raise ValueError(
            f"11VT split refused: stage must be one of {ALLOWED_STAGES}, got {payment_stage!r}. "
            "Never split a contract price before funds clear.")
    if amount_cents < 0:
        raise ValueError("11VT split refused: cleared amount cannot be negative")
    total_gross = Decimal(amount_cents) / Decimal(100)
    vault_allocations = {}
    total_allocated = Decimal("0.00")

    for v_id, meta in VAULT_TARGETS.items():
        cut = cent_round(total_gross * meta["rate"])
        vault_allocations[v_id] = {
            "name": meta["name"],
            "target_pct": str(meta["rate"] * 100) + "%",
            "amount_cents": int(cut * 100),
            "amount_formatted": f"${cut:.2f}"
        }
        total_allocated += cut

    # Rounding delta plug applied to V7
    delta = total_gross - total_allocated
    if delta != Decimal("0.00"):
        v7_adjusted = Decimal(vault_allocations["V7_DAILY_OPEX"]["amount_cents"]) / Decimal(100) + delta
        vault_allocations["V7_DAILY_OPEX"]["amount_cents"] = int(v7_adjusted * 100)
        vault_allocations["V7_DAILY_OPEX"]["amount_formatted"] = f"${v7_adjusted:.2f}"
        vault_allocations["V7_DAILY_OPEX"]["plug_delta_applied"] = f"${delta:.2f}"
        total_allocated += delta

    return {
        "job_id": job_id,
        "payment_stage": payment_stage,  # 'DEPOSIT_CLEARED_35' or 'FINAL_PAID_65'
        "cleared_amount_cents": amount_cents,
        "cleared_formatted": f"${total_gross:.2f}",
        "banking_execution": "NONE_LEDGER_RECEIPT_ONLY",
        "tax_disclaimer": "INTERNAL_RESERVE_TARGETS_NOT_STATUTORY_TAX_LIABILITY",
        "legal_notice": "INTERNAL_RESERVE_TARGETS_NOT_STATUTORY_TAX_LIABILITY",
        "v7_plug_notice": "ABSORBS_PENNY_ROUNDING_DELTAS",
        "balanced": (total_gross == total_allocated),
        "vaults": vault_allocations
    }
