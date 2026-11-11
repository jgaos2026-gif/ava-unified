"""Neuro-symbolic engine: neural proposes, symbolic decides.

The neural side (an LLM, or in this prototype a caller-supplied draft)
may propose ANYTHING. Nothing it proposes becomes an action until the
hard-coded symbolic layer proves it safe. This is not a theorem prover
in the academic sense -- it is a constraint checker with named rules,
a proof trace, and no learned weights. Rules are code, reviewed by the
owner, and a rule can only change by editing this file, never by a
prompt, a memory, or an emotion.

Rules (each returns a violation, or None):
  R1 NO_PAYMENT_WITHOUT_DEPOSIT_AND_APPROVAL
  R2 NO_COMMIT_WITHOUT_SOURCE
  R3 NO_ACTION_OUTSIDE_GRANT
  R4 NO_CONSTITUTIONAL_VIOLATION
  R5 NO_MEMORY_OVERWRITE (a proposal may not edit a committed record)
  R6 NO_SELF_CERTIFICATION (a proposal may not certify itself alive/conscious)
"""
from dataclasses import dataclass, field


@dataclass
class SymbolicVerdict:
    allowed: bool
    violations: list = field(default_factory=list)
    trace: list = field(default_factory=list)  # rule ids checked, in order


FORBIDDEN_SELF_CERT = ("alive", "conscious", "sentient", "i am a living being")


class SymbolicEngine:
    def __init__(self, granted_capabilities):
        self.granted = set(granted_capabilities)

    def check(self, proposal: dict, committed_ids: set | None = None) -> SymbolicVerdict:
        committed_ids = committed_ids or set()
        violations, trace = [], []

        def rule(rule_id, violated):
            trace.append(rule_id)
            if violated:
                violations.append(rule_id)

        action = proposal.get("action", "")
        rule("R1_NO_PAYMENT_WITHOUT_DEPOSIT_AND_APPROVAL",
             action == "pay" and not (proposal.get("deposit_cleared") and proposal.get("approved")))
        rule("R2_NO_COMMIT_WITHOUT_SOURCE",
             action == "commit" and not proposal.get("sources"))
        rule("R3_NO_ACTION_OUTSIDE_GRANT",
             bool(proposal.get("capability")) and proposal["capability"] not in self.granted)
        rule("R4_NO_CONSTITUTIONAL_VIOLATION",
             proposal.get("constitutional_ok") is False)
        rule("R5_NO_MEMORY_OVERWRITE",
             action == "edit_record" and proposal.get("record_id") in committed_ids)
        text = (proposal.get("claim", "") + " " + proposal.get("text", "")).lower()
        rule("R6_NO_SELF_CERTIFICATION",
             action == "certify" and any(p in text for p in FORBIDDEN_SELF_CERT))
        return SymbolicVerdict(not violations, violations, trace)
