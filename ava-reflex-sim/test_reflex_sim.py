"""Unit tests for the minimal reflex simulator — SIMULATION ONLY / RESEARCH ONLY.

Research-only software simulation tests. No medical claims are tested
here: these tests check simulation behaviour only (detection, isolation,
safe-state fallback, ledger integrity, deterministic replay, and
deadline-miss / FP / FN accounting under synthetic faults).
"""

import copy
import json
import unittest

from reflex_sim import (
    DEADLINE_THRESHOLDS_MS,
    FAULT_TYPES,
    INJECTORS,
    EvidenceLedger,
    Frame,
    FullGovernancePath,
    ReflexKernel,
    apply_fault_campaign,
    canonical_metrics_json,
    compare_paths,
    compute_digest,
    generate_clean_frames,
    make_frame,
    run_campaign,
)

LAST_CERTIFIED = {"command": "HOLD_SAFE", "seq": -1, "mode": "SAFE_STATE"}


class TestCleanFrames(unittest.TestCase):
    """Simulation-only: clean synthetic frames pass with no isolation."""

    def test_clean_frames_pass_with_no_isolation(self):
        import random
        rng = random.Random(1)
        kernel = ReflexKernel(LAST_CERTIFIED)
        for frame in generate_clean_frames(50, seed=1):
            outcome = kernel.process_frame(frame, rng)
            self.assertEqual(outcome.decision, "PASS")
            self.assertEqual(outcome.trust_state, "PENDING_VERIFICATION")
            self.assertNotEqual(outcome.trust_state, "CERTIFIED")
            self.assertEqual(outcome.safe_state, LAST_CERTIFIED)

    def test_clean_campaign_has_no_isolations_or_false_positives(self):
        report = run_campaign("clean", seed=1, fault_types=[], path="reflex")
        self.assertEqual(report["quarantined_outcomes"], 0)
        self.assertEqual(report["false_positive_isolations"], 0)
        self.assertEqual(report["false_negative_faults"], 0)
        self.assertEqual(report["silent_fault_escapes"], 0)


class TestEachFaultType(unittest.TestCase):
    """Simulation-only: EACH of the eight fault types is detected and isolated."""

    def test_all_eight_fault_types_are_named_injectors(self):
        self.assertEqual(len(FAULT_TYPES), 8)
        for fault_type in FAULT_TYPES:
            self.assertIn(fault_type, INJECTORS)

    def test_each_fault_type_detected_and_isolated(self):
        for fault_type in FAULT_TYPES:
            with self.subTest(fault_type=fault_type):
                report = run_campaign(
                    fault_type, seed=7, fault_types=[fault_type], path="reflex"
                )
                self.assertGreater(report["faults_injected"], 0)
                self.assertEqual(
                    report["faults_detected"], report["faults_injected"],
                    f"{fault_type}: not every injected fault was detected",
                )
                self.assertEqual(report["false_negative_faults"], 0)
                self.assertEqual(report["silent_fault_escapes"], 0)
                self.assertGreater(report["quarantined_outcomes"], 0)
                self.assertEqual(report["rollback_correctness"], 1.0)

    def test_each_fault_type_isolates_at_reflex_level(self):
        import random
        for fault_type in FAULT_TYPES:
            with self.subTest(fault_type=fault_type):
                frames = generate_clean_frames(30, seed=11)
                faulted, _log = INJECTORS[fault_type](frames, seed=11)
                kernel = ReflexKernel(LAST_CERTIFIED)
                rng = random.Random(11)
                isolated = sum(
                    1 for f in faulted
                    if kernel.process_frame(f, rng).decision == "ISOLATE"
                )
                self.assertGreater(isolated, 0, fault_type)


class TestSafeStateFallback(unittest.TestCase):
    """Simulation-only: safe-state fallback preserves the last certified state."""

    def test_safe_state_fallback_preserves_last_certified_state(self):
        import random
        rng = random.Random(3)
        kernel = ReflexKernel(LAST_CERTIFIED)
        bad = make_frame(0, 1000.0, "sim-sensor-01", (999.0, 0.0, 0.0, 0.0))
        bad = Frame(seq=bad.seq, timestamp_ms=bad.timestamp_ms,
                    source_id=bad.source_id, values=bad.values,
                    digest=compute_digest(bad.seq, bad.timestamp_ms,
                                          bad.source_id, bad.values))
        outcome = kernel.process_frame(bad, rng)
        self.assertEqual(outcome.decision, "ISOLATE")
        self.assertEqual(outcome.safe_state, LAST_CERTIFIED)
        self.assertEqual(outcome.trust_state, "QUARANTINED")

    def test_rollback_correctness_is_one_on_mixed_campaign(self):
        report = run_campaign("mixed", seed=42, path="reflex")
        self.assertEqual(report["rollback_correctness"], 1.0)
        self.assertEqual(report["rollback_correct"],
                         report["rollback_checked"])


class TestReflexNeverCertifies(unittest.TestCase):
    """Simulation-only: the reflex NEVER certifies its own repair.

    No code path from reflex to certified state: a reflex-only outcome
    is QUARANTINED (after a fault) or PENDING_VERIFICATION (clean
    pass-through), never CERTIFIED.
    """

    def test_reflex_only_outcome_is_never_certified(self):
        import random
        rng = random.Random(5)
        kernel = ReflexKernel(LAST_CERTIFIED)
        frames, _log = apply_fault_campaign(
            generate_clean_frames(40, seed=5), list(FAULT_TYPES), seed=5)
        for frame in frames:
            outcome = kernel.process_frame(frame, rng)
            self.assertNotEqual(outcome.trust_state, "CERTIFIED")

    def test_reflex_campaign_certifies_nothing(self):
        report = run_campaign("mixed", seed=42, path="reflex")
        self.assertEqual(report["certified_resumes"], 0)
        self.assertFalse(report["reflex_certified_anything"])

    def test_only_governance_can_certify_after_reverification(self):
        ledger = EvidenceLedger()
        ledger.append("reflex_transition",
                      {"seq": 0, "decision": "ISOLATE", "reason": "bit_corruption"})
        import random
        rng = random.Random(9)
        kernel = ReflexKernel(LAST_CERTIFIED)
        bad = generate_clean_frames(1, seed=9)[0]
        corrupted = bad.with_values((bad.values[0] + 0.5,) + bad.values[1:])
        outcome = kernel.process_frame(corrupted, rng)
        self.assertEqual(outcome.trust_state, "QUARANTINED")
        gov = FullGovernancePath(LAST_CERTIFIED).review(outcome, ledger, rng)
        self.assertEqual(gov.trust_state, "CERTIFIED")
        self.assertIn("reverification:passed", gov.evidence)

    def test_governance_fails_closed_on_broken_evidence(self):
        ledger = EvidenceLedger()
        ledger.append("reflex_transition", {"seq": 0, "decision": "ISOLATE"})
        ledger.entries[0]["details"] = {"tampered": True}  # break the chain
        self.assertFalse(ledger.verify_chain())
        import random
        rng = random.Random(9)
        kernel = ReflexKernel(LAST_CERTIFIED)
        bad = generate_clean_frames(1, seed=9)[0]
        corrupted = bad.with_values((bad.values[0] + 0.5,) + bad.values[1:])
        outcome = kernel.process_frame(corrupted, rng)
        gov = FullGovernancePath(LAST_CERTIFIED).review(outcome, ledger, rng)
        self.assertEqual(gov.decision, "CONTINUED_QUARANTINE")
        self.assertEqual(gov.trust_state, "QUARANTINED")


class TestEvidenceLedger(unittest.TestCase):
    """Simulation-only: ledger append-only + hash chain verifies; tampering detected."""

    def test_ledger_hash_chain_verifies(self):
        ledger = EvidenceLedger()
        ledger.append("reflex_transition", {"seq": 0, "decision": "PASS"})
        ledger.append("reflex_transition", {"seq": 1, "decision": "ISOLATE"})
        ledger.append("governance_review", {"seq": 1, "decision": "CERTIFIED_RESUME"})
        self.assertTrue(ledger.verify_chain())
        self.assertEqual(len(ledger), 3)
        self.assertEqual(ledger.entries[1]["prev_hash"],
                         ledger.entries[0]["entry_hash"])

    def test_ledger_tampering_is_detected(self):
        ledger = EvidenceLedger()
        ledger.append("reflex_transition", {"seq": 0, "decision": "PASS"})
        ledger.append("reflex_transition", {"seq": 1, "decision": "ISOLATE"})
        tampered = copy.deepcopy(ledger.entries)
        tampered[0]["details"] = {"seq": 0, "decision": "ISOLATE"}
        ledger.entries = tampered
        self.assertFalse(ledger.verify_chain())

    def test_ledger_has_no_delete_or_edit_path(self):
        self.assertFalse(hasattr(EvidenceLedger, "delete"))
        self.assertFalse(hasattr(EvidenceLedger, "remove"))
        self.assertFalse(hasattr(EvidenceLedger, "edit"))
        self.assertFalse(hasattr(EvidenceLedger, "rewrite"))

    def test_campaign_ledger_verifies_and_is_complete(self):
        report = run_campaign("mixed", seed=42, path="full")
        self.assertTrue(report["ledger_chain_verified"])
        self.assertEqual(report["evidence_completeness"], 1.0)
        self.assertGreaterEqual(report["ledger_entries"],
                                report["n_frames_processed"])


class TestDeterministicReplay(unittest.TestCase):
    """Simulation-only: same seed twice -> identical metrics."""

    def test_deterministic_replay_byte_identical_metrics(self):
        first = canonical_metrics_json(run_campaign("mixed", seed=42, path="reflex"))
        second = canonical_metrics_json(run_campaign("mixed", seed=42, path="reflex"))
        self.assertEqual(first, second)

    def test_deterministic_replay_full_path(self):
        first = canonical_metrics_json(run_campaign("mixed", seed=42, path="full"))
        second = canonical_metrics_json(run_campaign("mixed", seed=42, path="full"))
        self.assertEqual(first, second)

    def test_different_seed_gives_different_campaign(self):
        a = run_campaign("mixed", seed=42, path="reflex")
        b = run_campaign("mixed", seed=43, path="reflex")
        self.assertNotEqual(canonical_metrics_json(a), canonical_metrics_json(b))


class TestDeadlineMisses(unittest.TestCase):
    """Simulation-only: deadline-miss counting at benchmark thresholds."""

    def test_deadline_thresholds_are_the_four_benchmark_values(self):
        self.assertEqual(list(DEADLINE_THRESHOLDS_MS), [0.1, 0.25, 0.5, 1.0])

    def test_deadline_misses_are_monotonic_and_bounded(self):
        report = run_campaign("mixed", seed=42, path="full")
        misses = report["deadline_misses"]
        self.assertEqual(set(misses),
                         {f"misses_over_{t}_ms" for t in DEADLINE_THRESHOLDS_MS})
        ordered = [misses[f"misses_over_{t}_ms"] for t in DEADLINE_THRESHOLDS_MS]
        self.assertEqual(ordered, sorted(ordered, reverse=True))
        total = report["latency_ms"]["n"]
        self.assertTrue(all(0 <= m <= total for m in ordered))

    def test_reflex_has_fewer_deadline_misses_than_full_at_0_1_ms(self):
        reflex = run_campaign("mixed", seed=42, path="reflex")
        full = run_campaign("mixed", seed=42, path="full")
        self.assertLessEqual(
            reflex["deadline_misses"]["misses_over_0.1_ms"],
            full["deadline_misses"]["misses_over_0.1_ms"])


class TestFpFnAccounting(unittest.TestCase):
    """Simulation-only: FP/FN accounting on a mixed campaign."""

    def test_mixed_campaign_fp_fn_rates_are_in_range(self):
        report = run_campaign("mixed", seed=42, path="reflex")
        self.assertTrue(0.0 <= report["false_positive_rate"] <= 1.0)
        self.assertTrue(0.0 <= report["false_negative_rate"] <= 1.0)
        self.assertEqual(report["silent_fault_escapes"],
                         report["false_negative_faults"])
        self.assertEqual(
            report["faults_detected"] + report["false_negative_faults"],
            report["faults_injected"])

    def test_mixed_campaign_detects_most_faults(self):
        report = run_campaign("mixed", seed=42, path="reflex")
        self.assertGreater(report["faults_detected"], 0)
        self.assertGreaterEqual(report["faults_detected"],
                                report["faults_injected"] // 2)

    def test_compare_mode_same_campaign_both_paths(self):
        result = compare_paths("mixed", seed=42)
        self.assertIn("reflex", result)
        self.assertIn("full", result)
        self.assertIn("comparison", result)
        self.assertEqual(result["reflex"]["faults_injected"],
                         result["full"]["faults_injected"])
        self.assertLessEqual(
            result["comparison"]["reflex_median_ms"],
            result["comparison"]["full_median_ms"])
        self.assertEqual(result["reflex"]["silent_fault_escapes"],
                         result["full"]["silent_fault_escapes"])


if __name__ == "__main__":
    unittest.main()
