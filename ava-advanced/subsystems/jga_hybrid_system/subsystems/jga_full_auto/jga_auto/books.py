"""Books: invoices + SHA-256 receipts.

Every finished job ends invoiced, receipted, and ledger-ready. A receipt
is a hash of the invoice payload, so a delivered file set can be checked
later without trusting anyone's word for it.

11VT receipt-only allocation: on a delivered job, and ONLY on cleared
payments (the 35% deposit and the 65% final balance), the invoice
payload also binds the 11-vault reserve splits. Those splits are
internal reserve targets in a ledger receipt. They move NO bank funds,
open NO sub-accounts, and are NOT statutory tax liability.
"""
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from . import config
from .allocator_11vt import allocate_cleared_payment


@dataclass
class Invoice:
    customer: str
    package: str
    price_cents: int
    deposit_cents: int
    balance_cents: int
    receipt_sha256: str = ""
    deposit_11vt_split: Optional[Dict[str, Any]] = None
    final_11vt_split: Optional[Dict[str, Any]] = None

    def receipt_payload(self) -> bytes:
        return json.dumps({
            "business": config.BUSINESS_NAME,
            "customer": self.customer,
            "package": self.package,
            "price_cents": self.price_cents,
            "deposit_cents": self.deposit_cents,
            "balance_cents": self.balance_cents,
            "deposit_11vt_split": self.deposit_11vt_split,
            "final_11vt_split": self.final_11vt_split,
        }, sort_keys=True).encode("utf-8")


def build_invoice(job) -> Invoice:
    if job.state not in ("DONE", "FOLLOW_UP"):
        raise ValueError("invoice only closes on a delivered job")
    # Cleared-payments-only gate: a split must never be computed on
    # money that has not actually cleared, even if state somehow says DONE.
    if not getattr(job, "deposit_cleared", False):
        raise ValueError("11VT split refused: deposit has not cleared")
    if not getattr(job, "final_paid", False):
        raise ValueError("11VT split refused: final balance has not cleared")
    deposit_split = allocate_cleared_payment(
        job.deposit_cents, "DEPOSIT_CLEARED_35", getattr(job, "id", "CURRENT_JOB")
    )
    final_split = allocate_cleared_payment(
        job.price_cents - job.deposit_cents, "FINAL_PAID_65", getattr(job, "id", "CURRENT_JOB")
    )
    inv = Invoice(
        customer=job.customer,
        package=job.package,
        price_cents=job.price_cents,
        deposit_cents=job.deposit_cents,
        balance_cents=job.price_cents - job.deposit_cents,
        deposit_11vt_split=deposit_split,
        final_11vt_split=final_split,
    )
    inv.receipt_sha256 = hashlib.sha256(inv.receipt_payload()).hexdigest()
    return inv
