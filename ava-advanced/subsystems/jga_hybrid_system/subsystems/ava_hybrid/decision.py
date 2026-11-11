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


class DecisionEngine:
    def __init__(self, gateway=None, mobius_threshold: float = 0.5):
        self.gateway = gateway
        self.mobius_threshold = mobius_threshold

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

        # Branch + score, hard constraints first.
        ranked = []
        for c in candidates:
            if not c.constitutional_ok:
                continue
            if not c.trust_ok:
                continue
            reason = self._sb688_screen(c)
            if reason:
                continue
            ranked.append((c.expected_goal_value(), c))
        if not ranked:
            return Decision(None, "DEFERRED", "NO_CANDIDATE_PASSES_GATES")
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
                            round(score, 3), "SIMULATION", pocket)
        return Decision(None, "DEFERRED", "MOBIUS_RETURN_DISAGREES")
