"""Job pipeline state machine with Amendment 13 gates enforced in code.

A job can only move forward through the legal transitions, and the gates
are checks, not comments:
  - no drafting before a CLEARED deposit,
  - no clean files before final payment AND client approval,
  - no revision beyond the package limit.
"""
from dataclasses import dataclass, field

from . import config


class GateError(Exception):
    """Raised when a transition would violate a business gate."""


STATES = (
    "INTAKE", "SCOPED", "AWAITING_DEPOSIT", "DRAFTING", "PROOF_SENT",
    "REVISING", "AWAITING_FINAL", "DELIVERING", "DONE", "FOLLOW_UP",
)


@dataclass
class Job:
    customer: str
    package: str
    brief: str
    state: str = "INTAKE"
    price_cents: int = 0
    deposit_cleared: bool = False
    final_paid: bool = False
    client_approved: bool = False
    revisions_used: int = 0
    drafts: list = field(default_factory=list)
    proofs: list = field(default_factory=list)

    @property
    def revision_limit(self) -> int:
        return config.REVISION_LIMITS.get(self.package, 0)

    @property
    def deposit_cents(self) -> int:
        return self.price_cents * config.DEPOSIT_PERCENT // 100

    @property
    def clean_files_releasable(self) -> bool:
        """Clean files leave ONLY after final payment + client approval."""
        return self.final_paid and self.client_approved

    def _move(self, expected, nxt):
        if self.state != expected:
            raise GateError(f"cannot move from {self.state}: expected {expected}")
        self.state = nxt

    def scope(self):
        self._move("INTAKE", "SCOPED")
        if self.package not in config.PACKAGE_PRICES:
            raise GateError(f"unknown package: {self.package}")
        self.price_cents = config.PACKAGE_PRICES[self.package]
        self.state = "AWAITING_DEPOSIT"
        return self

    def mark_deposit_cleared(self):
        if self.state != "AWAITING_DEPOSIT":
            raise GateError(f"cannot clear deposit from {self.state}")
        self.deposit_cleared = True
        self.state = "DRAFTING"
        return self

    def submit_draft(self, draft):
        if self.state != "DRAFTING":
            raise GateError(f"cannot draft from {self.state}")
        if not self.deposit_cleared:
            raise GateError("deposit gate: no production before cleared deposit")
        self.drafts.append(draft)
        self.state = "PROOF_SENT"
        return self

    def client_decision(self, approved: bool):
        """Client approval gate. Approved -> final payment stage.
        Not approved -> revision loop, if revisions remain."""
        if self.state != "PROOF_SENT":
            raise GateError(f"cannot decide from {self.state}")
        if approved:
            self.client_approved = True
            self.state = "AWAITING_FINAL"
        else:
            if self.revisions_used >= self.revision_limit:
                raise GateError("revision limit reached; needs owner exception review")
            self.state = "REVISING"
        return self

    def revise(self, draft):
        if self.state != "REVISING":
            raise GateError(f"cannot revise from {self.state}")
        self.revisions_used += 1
        self.drafts.append(draft)
        self.state = "PROOF_SENT"
        return self

    def mark_final_paid(self):
        if self.state != "AWAITING_FINAL":
            raise GateError(f"cannot take final payment from {self.state}")
        self.final_paid = True
        self.state = "DELIVERING"
        return self

    def deliver_clean_files(self):
        if self.state != "DELIVERING":
            raise GateError(f"cannot deliver from {self.state}")
        if not self.clean_files_releasable:
            raise GateError("release gate: clean files need final payment + approval")
        self.state = "DONE"
        return self

    def follow_up(self):
        self._move("DONE", "FOLLOW_UP")
        return self
