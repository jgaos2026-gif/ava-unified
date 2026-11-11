"""AVA Hybrid prototype: identity transfer + anti-drift gateway + emotion gate.

Prototype, stdlib-only, no dependencies, runs on stock Python 3.
Signing here is HMAC-SHA256 with the self-held key (the key file moves
with the owner, separately from the capsule). Production swap: replace
Identity.sign/verify with Ed25519; the capsule/ledger/gateway interfaces
do not change. This prototype does NOT certify consciousness, aliveness,
or sentience. It proves behaviour: sealed transfer, deferred hallucination,
and emotion kept out of trust decisions.
"""
from .identity import Identity
from .ledger import Ledger
from .memory import Memory, MemoryRecord
from .gateway import Gateway, GatewayResult
from .emotion import Emotion, AffectiveState
from .capsule import export_capsule, import_capsule, CapsuleError
from .decision import Goal, Outcome, Candidate, Decision, DecisionEngine, escalate_gateway_deferral
from .symbolic import SymbolicEngine, SymbolicVerdict
from .dream import DreamConsolidator
from .zk import issue_receipt, verify_receipt
from .did import make_did_document, resolve_did
from .pulse import Pulse
from .consensus import DualConsensus, ConsensusResult
from .selfmodel import read_self_state, SelfState
from .capability import CapabilityStore

__all__ = [
    "Identity", "Ledger", "Memory", "MemoryRecord",
    "Gateway", "GatewayResult", "Emotion", "AffectiveState",
    "export_capsule", "import_capsule", "CapsuleError",
    "Goal", "Outcome", "Candidate", "Decision", "DecisionEngine",
    "escalate_gateway_deferral",
    "SymbolicEngine", "SymbolicVerdict", "DreamConsolidator",
    "issue_receipt", "verify_receipt",
    "make_did_document", "resolve_did",
    "Pulse", "DualConsensus", "ConsensusResult",
    "read_self_state", "SelfState", "CapabilityStore",
]
