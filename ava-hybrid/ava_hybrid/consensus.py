"""Dual-proposal consensus: one model is a single point of hallucination.

Groundbreaking agents should not trust one neural output. This module
requires TWO independent proposals (two models, two prompts, two
temperatures -- independence is the caller's job to guarantee, and
this module does not pretend to check it) plus the symbolic arbiter:
  1. Symbolic engine must allow BOTH proposals.
  2. Both proposals must agree on the ACTION (not just the wording).
  3. If either fails, or they disagree, the result is DEFER -- never
     "pick the first" or "pick the prettier one".
A single-model system can be confidently wrong. A dual system that
must agree, and must pass hard rules, is wrong far less often, and
when it is uncertain it says so instead of acting.
"""
from dataclasses import dataclass


@dataclass
class ConsensusResult:
    status: str  # AGREED or DEFERRED
    action: str | None = None
    reason: str = ""


class DualConsensus:
    def __init__(self, symbolic_engine):
        self.symbolic = symbolic_engine

    def decide(self, proposal_a: dict, proposal_b: dict,
               committed_ids: set | None = None) -> ConsensusResult:
        va = self.symbolic.check(proposal_a, committed_ids)
        vb = self.symbolic.check(proposal_b, committed_ids)
        if not va.allowed:
            return ConsensusResult("DEFERRED", None, f"A blocked: {va.violations}")
        if not vb.allowed:
            return ConsensusResult("DEFERRED", None, f"B blocked: {vb.violations}")
        if proposal_a.get("action") != proposal_b.get("action"):
            return ConsensusResult("DEFERRED", None, "PROPOSALS_DISAGREE")
        return ConsensusResult("AGREED", proposal_a["action"], "DUAL_AGREE_AND_SYMBOLIC_PASS")
