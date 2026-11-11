"""Gate + error-rate tests. Run: python -m unittest discover -s tests -v"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jga_auto.pipeline import Job, GateError
from jga_auto.drafting import draft_for
from jga_auto.gates import ErrorTracker


def make_job(package="Logo Launch"):
    job = Job(customer="T", package=package, brief="b")
    job.scope()
    return job


class TestGates(unittest.TestCase):
    def test_no_production_before_cleared_deposit(self):
        job = make_job()
        job.state = "DRAFTING"  # force past the deposit stage without clearing
        with self.assertRaises(GateError):
            job.submit_draft(draft_for("b", []))

    def test_deposit_gate_flow(self):
        job = make_job()
        job.mark_deposit_cleared()
        job.submit_draft(draft_for("b", []))
        self.assertEqual(job.state, "PROOF_SENT")

    def test_no_clean_files_before_final_payment(self):
        job = make_job()
        job.mark_deposit_cleared()
        job.submit_draft(draft_for("b", []))
        job.client_decision(approved=True)
        job.state = "DELIVERING"  # force past payment without paying
        job.final_paid = False
        with self.assertRaises(GateError):
            job.deliver_clean_files()

    def test_revision_limit_enforced(self):
        job = make_job()  # Logo Launch: 2 revisions
        job.mark_deposit_cleared()
        job.submit_draft(draft_for("b", []))
        for _ in range(2):
            job.client_decision(approved=False)
            job.revise(draft_for("b", []))
        with self.assertRaises(GateError):
            job.client_decision(approved=False)

    def test_full_happy_path(self):
        job = make_job()
        job.mark_deposit_cleared()
        job.submit_draft(draft_for("b", []))
        job.client_decision(approved=True)
        job.mark_final_paid()
        job.deliver_clean_files()
        job.follow_up()
        self.assertEqual(job.state, "FOLLOW_UP")

    def test_error_rate_math_and_phase_b(self):
        tracker = ErrorTracker()
        for i in range(20):
            tracker.record(error_found=(i == 0))
        self.assertAlmostEqual(tracker.error_rate, 0.05)
        self.assertTrue(tracker.phase_b_ready(threshold=0.05, min_samples=20))
        self.assertFalse(tracker.phase_b_ready(threshold=0.04, min_samples=20))
        small = ErrorTracker()
        small.record(error_found=False)
        self.assertFalse(small.phase_b_ready(threshold=0.05, min_samples=20))


if __name__ == "__main__":
    unittest.main()
