"""Decision making: think of possible outcomes, pick the best for the
CURRENT GOAL's outcome.

John's ruling, 2026-10-29: "best" is measured against the outcome of
the current goal -- not the easiest present step, not a generic future,
not Ava's own preference. If the goal changes, the scoring changes.
If there is no stated current goal, the engine DEFERS instead of
inventing one.

Loop (problem solving, tree roots, braid both ways):
  1. SB688 in-screen: purify / screen the problem and candidates
     (gateway: unknown field, missing source, capability outside grant).
  2. Root branching: each candidate action branches into possible
     outcomes, like roots of a tree.
  3. Forward simulation: each outcome is scored ONLY against the
     current goal (goal_score 0-1), weighted by its probability, minus
     a harm penalty. Immediate reward is NOT a separate score -- it
     only counts if it also serves the goal's future outcome.
  4. Hard constraints first: a candidate that fails a constitutional
     or trust check is skipped, however high it scores. Emotion is
     ignored here (see emotion.py).
  5. SB689 Mobius return: the chosen candidate is re-checked from the
     flipped side -- backward pass: does this outcome, traced back to
     the roots, still lead to the goal if the key assumption is
     inverted? If the flipped score drops below the threshold, DEFER.
  6. SB712 out-screen: gateway check on the chosen decision.
  7. Validation pocket: the decision is loaded into a pocket as
     SIMULATION / DECISION, never as a committed fact. A simulation
     that later verifies may become memory through the normal
     OBSERVED->...->COMMIT pipeline. Until then it stays labeled.

Proof level of every output here: SIMULATION, by construction.
"""
from dataclasses import dataclass, field
import hashlib
import random

from .reflex import (
    FAULT_TYPES,
    EvidenceLedger,
    ReflexKernel,
    apply_fault_campaign,
    generate_clean_frames,
)

# Minimal reflex simulator (simulation-only / research-only, SPEC.md
# section 7 of the reference). The reflex NEVER re-decides what the
# gateway deferred: a deferral becomes detect -> isolate -> safe-state
# -> signal, then escalation. The gateway's reason stands untouched.
REFLEX_SAFE_STATE = {"command": "HOLD_SAFE", "seq": -1, "mode": "SAFE_STATE"}

# Deterministic mapping: gateway deferral reason -> synthetic fault type
# injected into the reflex stream. The mapping is a simulation label,
# not a claim about what caused the deferral.
GATEWAY_DEFERRAL_FAULTS = {
    "DIGEST_MISMATCH": "bit_corruption",
    "TOKEN_OVERRUN": "delayed_responses",
    "UNKNOWN_FIELD": "impossible_values",
    "MISSING_SOURCE": "dropped_frames",
    "UNGROUNDED_CLAIM": "stale_replay",
    "CAPABILITY_OUTSIDE_GRANT": "conflicting_control",
}


def escalate_gateway_deferral(reason: str, seed_source: str) -> dict:
    """Run the minimal reflex on a synthetic stream seeded from the
    deferral, and return a simulation-only escalation receipt. The
    gateway's deferral is recorded, never re-decided: the receipt's
    trust state is QUARANTINED and certified is always False."""
    fault_type = GATEWAY_DEFERRAL_FAULTS.get(reason, "packet_reordering")
    seed = int(hashlib.sha256(str(seed_source).encode("utf-8")).hexdigest()[:8], 16)
    clean = generate_clean_frames(20, seed)
    frames, fault_log = apply_fault_campaign(clean, [fault_type], seed)
    rng = random.Random(seed)
    kernel = ReflexKernel(dict(REFLEX_SAFE_STATE))
    ledger = EvidenceLedger()
    first_isolation = None
    for frame in frames:
        outcome = kernel.process_frame(frame, rng)
        ledger.append("reflex_transition", {
            "seq": frame.seq, "decision": outcome.decision,
            "reason": outcome.reason, "trust_state": outcome.trust_state,
            "fault_type": frame.fault_type, "fault_id": frame.fault_id})
        if outcome.decision == "ISOLATE" and first_isolation is None:
            first_isolation = outcome
    detected = (first_isolation.reason if first_isolation is not None
                else "UNDETECTED_INJECTED_FAULT")
    return {
        "simulation_only": True,
        "research_only": True,
        "gateway_reason": reason,
        "fault_type": fault_type,
        "detected": detected,
        "decision": "ISOLATE",
        "trust_state": "QUARANTINED",
        "safe_state": dict(REFLEX_SAFE_STATE),
        "signal": "ESCALATED_TO_FULL_GOVERNANCE",
        "certified": False,
        "ledger_entries": len(ledger),
        "ledger_chain_verified": ledger.verify_chain(),
        "note": ("Simulation-only reflex escalation: the gateway deferral "
                 "stands as decided; the reflex only isolated, fell back "
                 "to the safe state, and signalled for full governance "
                 "review. No medical claim is made."),
    }


@dataclass
class Goal:
    """The current goal. Its outcome is the only measuring stick."""
    name: str
    outcome: str  # what "done" looks like, in plain words


@dataclass
class Outcome:
    description: str
    probability: float  # 0-1, caller's estimate, never presented as fact
    goal_score: float   # 0-1: how well this outcome serves the current goal
    harm: float = 0.0   # 0-1: trust / cost / contradiction harm if it happens


@dataclass
class Candidate:
    action: str
    outcomes: list = field(default_factory=list)
    capability: str = "read"
    constitutional_ok: bool = True
    trust_ok: bool = True

    def expected_goal_value(self) -> float:
        """Probability-weighted goal score, minus harm. Future, not present."""
        return sum(o.probability * o.goal_score - o.probability * o.harm
                   for o in self.outcomes)


@dataclass
class Decision:
    action: str | None
    status: str  # CHOSEN or DEFERRED
    reason: str = ""
    score: float = 0.0
    proof_level: str = "SIMULATION"
    pocket: dict = field(default_factory=dict)
    # Simulation-only reflex escalation receipt, set only when a gateway
    # deferral occurred during this decide() call. The gateway's
    # decision stands; this receipt only records detect -> isolate ->
    # safe-state -> signal + escalation. None when no deferral happened.
    reflex: dict | None = None


class DecisionEngine:
    def __init__(self, gateway=None, mobius_threshold: float = 0.5,
                 ledger=None):
        self.gateway = gateway
        self.mobius_threshold = mobius_threshold
        # Optional append-only ledger receiving REFLEX_ESCALATION
        # entries (ava_hybrid.ledger.Ledger). Escalation never depends
        # on it: without a ledger the receipt still travels on the
        # returned Decision and on self.last_reflex.
        self.ledger = ledger
        self.last_reflex = None

    def _escalate_if_deferred(self, deferrals, goal):
        """Build the reflex receipt for the first gateway deferral, if
        any; record it on the engine and the ledger. Returns the
        receipt, or None when no gateway deferral happened."""
        if not deferrals:
            return None
        reason, seed_source = deferrals[0]
        receipt = escalate_gateway_deferral(reason, seed_source)
        self.last_reflex = receipt
        if self.ledger is not None:
            self.ledger.append("REFLEX_ESCALATION", {
                "gateway_reason": reason,
                "goal": goal.name if goal is not None else None,
                "fault_type": receipt["fault_type"],
                "detected": receipt["detected"],
                "trust_state": receipt["trust_state"],
                "simulation_only": True,
                "research_only": True,
                "certified": False,
            })
        return receipt

    def _sb688_screen(self, candidate: Candidate):
        """Entry screen. Returns a defer reason, or None."""
        if self.gateway is None:
            return None
        r = self.gateway.check({"capability": candidate.capability,
                                "claims": [], "sources": ["goal"]})
        return None if r.allowed else r.reason

    def _mobius_return(self, candidate: Candidate, flipped_scores: dict) -> bool:
        """SB689 figure-8 return: flipped second pass must still hold.
        flipped_scores maps action -> re-scored goal value with the key
        assumption inverted. Missing entry = no second pass = no pass."""
        flipped = flipped_scores.get(candidate.action)
        if flipped is None:
            return False
        return flipped >= self.mobius_threshold

    def decide(self, goal: Goal | None, candidates: list,
               flipped_scores: dict | None = None) -> Decision:
        if goal is None:
            return Decision(None, "DEFERRED", "NO_CURRENT_GOAL")
        if not candidates:
            return Decision(None, "DEFERRED", "NO_CANDIDATES")
        flipped_scores = flipped_scores or {}
        # Gateway deferrals seen during this call, as (reason, action).
        # They are recorded for the reflex, never re-decided.
        deferrals = []

        # Branch + score, hard constraints first.
        ranked = []
        for c in candidates:
            if not c.constitutional_ok:
                continue
            if not c.trust_ok:
                continue
            reason = self._sb688_screen(c)
            if reason:
                deferrals.append((reason, c.action))
                continue
            ranked.append((c.expected_goal_value(), c))
        if not ranked:
            return Decision(None, "DEFERRED", "NO_CANDIDATE_PASSES_GATES",
                            reflex=self._escalate_if_deferred(deferrals, goal))
        ranked.sort(key=lambda t: t[0], reverse=True)

        # Best for the current goal's outcome, not the easiest step.
        for score, chosen in ranked:
            # SB689 Mobius return: flipped pass must agree.
            if not self._mobius_return(chosen, flipped_scores):
                continue
            # SB712 out-screen.
            if self.gateway is not None:
                r = self.gateway.check({"capability": chosen.capability,
                                        "claims": [], "sources": ["goal"]})
                if not r.allowed:
                    deferrals.append((r.reason, chosen.action))
                    continue
            # Validation pocket: decision loaded, labeled SIMULATION.
            pocket = {
                "goal": goal.name, "goal_outcome": goal.outcome,
                "action": chosen.action, "score": round(score, 3),
                "proof_level": "SIMULATION",
                "outcomes": [{"description": o.description,
                              "probability": o.probability,
                              "goal_score": o.goal_score} for o in chosen.outcomes],
            }
            return Decision(chosen.action, "CHOSEN", "BEST_FOR_CURRENT_GOAL",
                            round(score, 3), "SIMULATION", pocket,
                            reflex=self._escalate_if_deferred(deferrals, goal))
        return Decision(None, "DEFERRED", "MOBIUS_RETURN_DISAGREES",
                        reflex=self._escalate_if_deferred(deferrals, goal))
