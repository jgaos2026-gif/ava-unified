"""Deferring gateway: the LLM never gets the last word.

Every draft answer is checked BEFORE it becomes memory or action.
Any failed check -> DEFER with a receipt, never a bluffed answer.
Checks (John's hybrid-v2 rules):
  UNKNOWN_FIELD        - a field the system does not know is claimed as known
  MISSING_SOURCE       - a factual claim with no source record
  CAPABILITY_OUTSIDE_GRANT - an action outside the granted capability set
  DIGEST_MISMATCH      - content digest does not match the source digest
  TOKEN_OVERRUN        - actual tokens exceed estimate by more than 5%
  UNGROUNDED_CLAIM     - claim not present in any committed memory/source
"""
from dataclasses import dataclass

TOKEN_OVERRUN_LIMIT = 0.05


@dataclass
class GatewayResult:
    allowed: bool
    reason: str = "OK"
    receipt: dict = None


class Gateway:
    def __init__(self, granted_capabilities, memory):
        self.granted = set(granted_capabilities)
        self.memory = memory

    def check(self, draft: dict) -> GatewayResult:
        def defer(reason, detail=""):
            return GatewayResult(False, reason, {"deferred": reason, "detail": detail})

        if draft.get("unknown_fields"):
            return defer("UNKNOWN_FIELD", str(draft["unknown_fields"]))
        if draft.get("capability") and draft["capability"] not in self.granted:
            return defer("CAPABILITY_OUTSIDE_GRANT", draft["capability"])
        if draft.get("digest") and draft.get("source_digest") \
                and draft["digest"] != draft["source_digest"]:
            return defer("DIGEST_MISMATCH")
        est = draft.get("token_estimate") or 0
        act = draft.get("token_actual")
        if est and act and (act - est) / est > TOKEN_OVERRUN_LIMIT:
            return defer("TOKEN_OVERRUN", f"{act} vs est {est}")
        claims = draft.get("claims") or []
        sources = draft.get("sources") or []
        if claims and not sources:
            return defer("MISSING_SOURCE")
        for claim in claims:
            grounded = any(claim in r.claim for r in self.memory.records.values()
                           if r.state == "COMMIT") or claim in sources
            if not grounded:
                return defer("UNGROUNDED_CLAIM", claim)
        return GatewayResult(True, "OK", {"allowed": True})
