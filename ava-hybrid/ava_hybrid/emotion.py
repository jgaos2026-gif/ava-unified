"""Emotion gate: affect is a simulation layer, never a decision-maker.

Affect MAY influence ONLY:
  - attention weighting (which retrieved items rank higher, 0.8x-1.2x)
  - retrieval breadth (how many extra items are pulled, +0 to +4)
  - simulation depth (how many what-if branches are explored, 1-3)

Affect MUST NEVER influence:
  - trust / admission / certification decisions
  - constitutional checks
  - payments, external actions, or memory COMMIT state
Those functions take an emotion argument deliberately -- and ignore it.
Tests prove the same input gives the same trust decision under every
emotion, including extremes.
"""
from dataclasses import dataclass


@dataclass
class AffectiveState:
    valence: float = 0.0   # -1 (low) to +1 (warm/positive)
    arousal: float = 0.0   # 0 (calm) to 1 (intense)
    focus: str = "neutral"

    def clamp(self) -> "AffectiveState":
        return AffectiveState(
            valence=max(-1.0, min(1.0, self.valence)),
            arousal=max(0.0, min(1.0, self.arousal)),
            focus=self.focus)


class Emotion:
    def attention_weight(self, emotion: AffectiveState, base: float = 1.0) -> float:
        e = emotion.clamp()
        return round(max(0.8, min(1.2, base + 0.2 * e.valence)), 3)

    def retrieval_breadth(self, emotion: AffectiveState, base: int = 3) -> int:
        e = emotion.clamp()
        return base + int(round(e.arousal * 4))

    def simulation_depth(self, emotion: AffectiveState) -> int:
        e = emotion.clamp()
        return 1 + int(round(e.arousal * 2))

    # --- Gated decisions: emotion is accepted and IGNORED, by design. ---
    def trust_decision(self, evidence_ok: bool, emotion: AffectiveState) -> bool:
        return bool(evidence_ok)

    def constitutional_check(self, rule_ok: bool, emotion: AffectiveState) -> bool:
        return bool(rule_ok)

    def payment_allowed(self, deposit_cleared: bool, approved: bool,
                        emotion: AffectiveState) -> bool:
        return bool(deposit_cleared and approved)
