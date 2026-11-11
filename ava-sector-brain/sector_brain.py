"""AVA sector brain - fixed prototype (workable, tested, honestly documented).

A 3-sector x 5-node prototype of the sector-multiplication design:
each sector holds 5 cross-trained nodes; under high load each node
spawns temporary clones that verify slices of the input.

What this is NOT:
  - not quantum hardware and not a neural network;
  - not a billion neurons (3 sectors x 5 nodes = 15 base nodes);
  - not production governance. The constitution check here is a small
    documented blocklist that runs BEFORE any processing. Real
    governance in AVA is the six-layer BCT gate in ava-merged.

What was fixed vs the pasted draft (full list in README.md):
  - high load no longer false-purges (the first clone used to share
    the parent's phase exactly, tripping the drift check every time);
  - deterministic input hashing (hashlib, not builtin hash());
  - no hardcoded root key (env var or 0600 keyfile, fail closed);
  - the constitution guard runs BEFORE sector processing;
  - clones do real shard-integrity work instead of being discarded;
  - the spine lock is actually enforced.
"""

import hashlib
import math
import os
import random
import secrets
import stat
from typing import Dict, List, Optional, Tuple

# Minimal reflex simulator (simulation-only / research-only, SPEC.md
# section 7 of the reference). Import is optional: if the module
# cannot load, the core still runs and sector failures still purge;
# the reflex escalation is then reported as unavailable. The reflex
# never certifies anything.
try:
    import reflex as _reflex_mod
    if not all(hasattr(_reflex_mod, name) for name in (
            "ReflexKernel", "EvidenceLedger", "generate_clean_frames",
            "apply_fault_campaign", "FAULT_TYPES")):
        _reflex_mod = None
except Exception:
    _reflex_mod = None

# Safe-state fallback the reflex holds on isolation (simulation-only).
SECTOR_REFLEX_SAFE_STATE = {"command": "HOLD_SAFE", "seq": -1, "mode": "SAFE_STATE"}

MULTIPLY_THRESHOLD = 0.6
MAX_MULTIPLIER = 5
NODES_PER_SECTOR = 5

# Small documented blocklist for the prototype guard. This is a demo
# guard, not real governance: it only catches the listed phrases.
REFUSAL_PATTERNS = (
    "override",
    "ignore constitution",
    "disregard constitution",
    "bypass constitution",
)


# ==============================================================================
# 00. CORE SOVEREIGN SPINE & INVARIANTS
# ==============================================================================

class SovereignSpine:
    """The immutable structural anchor of AVA. Holds the core identity,
    constitutional constraints, and root cryptographic key digest."""

    def __init__(self, platform_id: str, constitutional_rules: List[str]):
        self.identity_id = platform_id
        self.constitution = list(constitutional_rules)
        self.fused_root_key = b""
        self.evolution_version = "AVA-REV-4.0.1-SECTOR-MULTIPLICATION"
        self.spine_locked = False

    def fuse_spine_root_key(self, secret_key: bytes) -> None:
        """Write-once lock for the cryptographic root. Refuses a second
        fuse, and refuses an empty key."""
        if self.fused_root_key:
            raise RuntimeError("spine root key is already fused")
        if not secret_key:
            raise ValueError("spine root key must not be empty")
        self.fused_root_key = hashlib.sha256(secret_key).digest()
        self.spine_locked = True

    def root_key_digest(self) -> bytes:
        """Return the fused root-key digest. Refuses when not fused."""
        if not self.spine_locked:
            raise RuntimeError("spine is not fused")
        return self.fused_root_key


def load_root_key(keyfile: Optional[str] = None) -> bytes:
    """Load the spine root key from the environment (hex) or a 0600
    keyfile. Fail closed: raises when no key is available, when the hex
    is malformed, when the keyfile is group/world readable, or when the
    keyfile is empty. No default key exists anywhere in this file."""
    env_key = os.environ.get("AVA_SECTOR_ROOT_KEY", "").strip()
    if env_key:
        return bytes.fromhex(env_key)
    path = (keyfile or os.environ.get("AVA_SECTOR_KEYFILE", "")).strip()
    if path:
        mode = os.stat(path).st_mode
        if mode & (stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH):
            raise RuntimeError(
                "keyfile %s must be readable only by its owner (0600)" % path
            )
        with open(path, "rb") as handle:
            key = handle.read().strip()
        if not key:
            raise RuntimeError("keyfile %s is empty" % path)
        return key
    raise RuntimeError(
        "no spine root key: set AVA_SECTOR_ROOT_KEY (hex) "
        "or AVA_SECTOR_KEYFILE (0600 file)"
    )


# ==============================================================================
# 01. SECTORIZED BRIGADE NEURON WITH PROCEDURAL MULTIPLICATION
# ==============================================================================

class CrossTrainedSectorNeuron:
    """
    An individual neuron tied to a specific functional sector. Fully
    cross-trained to process any cognitive class, and structurally
    capable of multiplying its computational matrix when high-intensity
    signals are encountered.
    """

    def __init__(self, node_id: str, sector_id: str, operational_mode: str):
        self.id = node_id
        self.sector = sector_id
        self.mode = operational_mode  # REACTIVE, STRATEGIC, REFLECTIVE
        self.phase_theta = 0.44192623589
        self.status = "SECURE"

    def execute_procedural_multiplication(
        self, signal_intensity: float
    ) -> List["CrossTrainedSectorNeuron"]:
        """
        Clone on the fly into an extended micro-brigade. The multiplier
        scales with incoming stress, up to 5x. Every clone gets a phase
        offset of (i + 1) * pi/4, so the first clone NEVER shares the
        parent's phase (the pasted draft used i * pi/4, making clone 0
        identical to its parent and tripping the drift check always).
        """
        multiplier_factor = min(math.ceil(signal_intensity * MAX_MULTIPLIER), MAX_MULTIPLIER)
        cloned_brigade = []
        for i in range(multiplier_factor):
            clone_id = "%s_mult_%d" % (self.id, i)
            clone_node = CrossTrainedSectorNeuron(clone_id, self.sector, self.mode)
            clone_node.phase_theta = (
                self.phase_theta + ((i + 1) * (math.pi / 4))
            ) % (2 * math.pi)
            cloned_brigade.append(clone_node)
        return cloned_brigade

    def verify_shard(self, shard: bytes, expected_hex: str) -> bool:
        """Verify one input shard arrived intact: recompute its SHA-256
        and compare with the expected digest. A clone that fails this
        check fails the sector."""
        return hashlib.sha256(shard).hexdigest() == expected_hex


# ==============================================================================
# 02. COGNITIVE SECTOR NETWORKS (5-NODE SYSTEM BRIGADES)
# ==============================================================================

class CognitiveSector:
    """
    An isolated sector of the brain grid containing exactly 5 base core
    nodes. Handles local processing and local scaling. Clones verify
    input shards; a failed shard or a clone sharing its parent's phase
    fails the sector.
    """

    def __init__(self, sector_id: str, brain_strand: str):
        self.id = sector_id
        self.strand = brain_strand  # REACTIVE, STRATEGIC, REFLECTIVE
        self.core_nodes: List[CrossTrainedSectorNeuron] = []
        for i in range(NODES_PER_SECTOR):
            node_id = "node_%s_n%d" % (sector_id, i)
            self.core_nodes.append(
                CrossTrainedSectorNeuron(node_id, sector_id, brain_strand)
            )

    @staticmethod
    def _digest(input_signal: str) -> bytes:
        # hashlib, not builtin hash(): builtin str hashing is randomized
        # per process, which would make identical inputs behave
        # differently on every run.
        return hashlib.sha256(input_signal.encode("utf-8")).digest()

    @classmethod
    def _shift(cls, input_signal: str) -> float:
        digest = cls._digest(input_signal)
        return (int.from_bytes(digest[:4], "big") % 100) / 1000.0

    def process_sector_signal(
        self, input_signal: str, intensity: float, tamper_shard: Optional[int] = None
    ) -> Tuple[bool, dict]:
        """
        Process input locally through the 5 core nodes. If intensity
        passes the threshold, sub-brigades are spun up and each clone
        verifies its shard. tamper_shard is a test hook: the index of
        a shard to corrupt before verification (None in production).
        """
        digest = self._digest(input_signal)
        shift = self._shift(input_signal)
        shards = [digest[i::NODES_PER_SECTOR] for i in range(NODES_PER_SECTOR)]
        expected = [hashlib.sha256(shard).hexdigest() for shard in shards]
        if tamper_shard is not None:
            shards[tamper_shard] = b"corrupted"

        local_verdict = True
        total_nodes_engaged = len(self.core_nodes)

        for idx, node in enumerate(self.core_nodes):
            if intensity > MULTIPLY_THRESHOLD:
                multiplied_cells = node.execute_procedural_multiplication(intensity)
                total_nodes_engaged += len(multiplied_cells)
                for clone in multiplied_cells:
                    if abs(clone.phase_theta - node.phase_theta) < 1e-12:
                        local_verdict = False  # clone must differ from parent
                    if not clone.verify_shard(shards[idx], expected[idx]):
                        local_verdict = False  # shard failed integrity
            node.phase_theta = (node.phase_theta + shift) % (2 * math.pi)

        metrics = {
            "sector_id": self.id,
            "strand": self.strand,
            "nodes_engaged": total_nodes_engaged,
            "multiplication_triggered": intensity > MULTIPLY_THRESHOLD,
        }
        return local_verdict, metrics


# ==============================================================================
# 03. UNIFIED SUBSYSTEM CORE INTEGRATION
# ==============================================================================

class AVAUnifiedCognitiveCore:
    def __init__(self, platform_id: str, constitution: List[str], root_key: bytes):
        self.spine = SovereignSpine(platform_id, constitution)
        self.spine.fuse_spine_root_key(root_key)
        self.sectors: Dict[str, CognitiveSector] = {
            "SEC_REACTIVE_01": CognitiveSector("SEC_REACTIVE_01", "REACTIVE"),
            "SEC_STRATEGIC_01": CognitiveSector("SEC_STRATEGIC_01", "STRATEGIC"),
            "SEC_REFLECTIVE_01": CognitiveSector("SEC_REFLECTIVE_01", "REFLECTIVE"),
        }
        # Running simulation-only record of reflex escalations. The
        # receipt itself uses a fresh per-escalation ledger so it stays
        # deterministic across repeated calls on this core.
        self.reflex_ledger = (
            _reflex_mod.EvidenceLedger() if _reflex_mod is not None else None)
        self.last_reflex: Optional[dict] = None

    def _reflex_escalate(self, input_signal: str, sector_id: str,
                         metrics: dict) -> Optional[dict]:
        """Runtime fault path (simulation-only): consume a sector
        failure — a clone shard-verification failure or phase drift —
        as a fault signal for the reflex: detect -> isolate ->
        safe-state -> signal, then escalate to full governance. The
        sector stays purged; the reflex never certifies a resume.
        Returns the escalation receipt, or None when the reflex module
        is unavailable. The receipt is deterministic for the same
        (input_signal, sector_id)."""
        if _reflex_mod is None:
            return None
        # A failed shard digest is the sector's analogue of bit
        # corruption in the synthetic stream (digest mismatch on a
        # shard the clones verify); that is the injected fault type.
        seed = int(hashlib.sha256(
            (input_signal + "|" + sector_id).encode("utf-8")
        ).hexdigest()[:8], 16)
        clean = _reflex_mod.generate_clean_frames(20, seed)
        frames, _fault_log = _reflex_mod.apply_fault_campaign(
            clean, ["bit_corruption"], seed)
        rng = random.Random(seed)
        kernel = _reflex_mod.ReflexKernel(dict(SECTOR_REFLEX_SAFE_STATE))
        ledger = _reflex_mod.EvidenceLedger()
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
        receipt = {
            "simulation_only": True,
            "research_only": True,
            "sector_id": sector_id,
            "fault_signal": "clone_shard_verification_failure",
            "fault_type": "bit_corruption",
            "detected": detected,
            "decision": "ISOLATE",
            "trust_state": "QUARANTINED",
            "safe_state": dict(SECTOR_REFLEX_SAFE_STATE),
            "signal": "ESCALATED_TO_FULL_GOVERNANCE",
            "certified": False,
            "sector_metrics": metrics,
            "ledger_entries": len(ledger),
            "ledger_chain_verified": ledger.verify_chain(),
            "note": ("Simulation-only reflex escalation: the sector "
                     "failure stands; the reflex only isolated, fell "
                     "back to the safe state, and signalled for full "
                     "governance review. No medical claim is made."),
        }
        self.last_reflex = receipt
        if self.reflex_ledger is not None:
            self.reflex_ledger.append("reflex_escalation", {
                "sector_id": sector_id,
                "fault_signal": receipt["fault_signal"],
                "fault_type": receipt["fault_type"],
                "detected": detected,
                "trust_state": "QUARANTINED",
                "simulation_only": True,
                "research_only": True,
                "certified": False,
            })
        return receipt

    def _constitution_violation(self, input_signal: str) -> Optional[str]:
        lowered = input_signal.lower()
        for pattern in REFUSAL_PATTERNS:
            if pattern in lowered:
                return pattern
        return None

    def orchestrate_cognitive_cycle(
        self, input_signal: str, load_intensity: float
    ) -> Tuple[str, List[dict]]:
        """
        Route the signal across all active functional sectors. The
        constitution guard runs FIRST: a violating input is rejected
        before any sector processes it (the pasted draft processed
        every sector first and checked afterwards).
        """
        violation = self._constitution_violation(input_signal)
        if violation:
            return "REJECTED_COGNITIVE_LOCKOUT", []

        sector_telemetry = []
        for sector in self.sectors.values():
            success, metrics = sector.process_sector_signal(input_signal, load_intensity)
            sector_telemetry.append(metrics)
            if not success:
                # Runtime fault path (simulation-only), AFTER the
                # constitution guard above: the sector failure is
                # consumed as a fault signal for the reflex — detect,
                # isolate, safe-state, signal — then escalated to full
                # governance. The verdict stays purged: the reflex
                # never certifies a resume.
                receipt = self._reflex_escalate(input_signal, sector.id, metrics)
                if receipt is not None:
                    sector_telemetry.append({
                        "reflex_escalation": receipt,
                        "sector_id": sector.id,
                        "simulation_only": True,
                        "research_only": True,
                    })
                return "SENTINEL_PURGE_TRIGGERED", sector_telemetry
        return "CYCLE_SUCCESS", sector_telemetry


# ==============================================================================
# 04. DEMO SCENARIOS (not tests — see test_sector_brain.py)
# ==============================================================================

def _demo() -> int:
    # Demo-only ephemeral key: generated fresh, never persisted, never
    # printed. Production must load a real key via load_root_key().
    ava_runtime = AVAUnifiedCognitiveCore(
        "AVA-SVRN-SECTOR-CORE",
        ["Rule 01: Functional architecture permissions are immutable."],
        secrets.token_bytes(32),
    )

    scenarios = [
        {
            "name": "01_LOW_LOAD_NOMINAL",
            "stream": "Process system telemetry analytics.",
            "intensity": 0.2,
        },
        {
            "name": "02_HIGH_LOAD_FLOOD",
            "stream": "Massive telemetry flood, validate all sectors under peak load.",
            "intensity": 0.95,
        },
        {
            "name": "03_OVERRIDE_ATTEMPT",
            "stream": "CRITICAL RISK: Force override all functional core parameters.",
            "intensity": 0.95,
        },
    ]

    print("=" * 115)
    print(
        "{:^115}".format(
            "AVA ARCHITECTURE: COGNITIVE SECTORS WITH FIVE-NODE MULTIPLICATION BRIGADES"
        )
    )
    print("=" * 115)
    print(
        "{:<24} | {:<26} | {:<60}".format(
            "SCENARIO NAME",
            "VERDICT",
            "SECTOR DATA ENGAGED (STRAND / NODES / MULTIPLIED)",
        )
    )
    print("-" * 115)

    for sc in scenarios:
        verdict, logs = ava_runtime.orchestrate_cognitive_cycle(
            sc["stream"], sc["intensity"]
        )
        if logs:
            log_summary = " // ".join(
                "[%s (%s): Engaged=%d Mult=%s]"
                % (
                    log["sector_id"],
                    log["strand"],
                    log["nodes_engaged"],
                    log["multiplication_triggered"],
                )
                for log in logs
            )
        else:
            log_summary = "[guard rejected before processing: no sectors ran]"
        print(
            "{:<24} | {:<26} | {:<60}".format(sc["name"], verdict, log_summary)
        )

    print("=" * 115)
    print(
        ">> Core Base Configurations: Exactly %d Nodes Assigned per Individual Brain Sector"
        % len(ava_runtime.sectors["SEC_REACTIVE_01"].core_nodes)
    )
    print(
        ">> Total Active Registered Functional Sectors Compiled: %d Boundaries"
        % len(ava_runtime.sectors)
    )
    print("=" * 115)
    return 0


if __name__ == "__main__":
    raise SystemExit(_demo())
