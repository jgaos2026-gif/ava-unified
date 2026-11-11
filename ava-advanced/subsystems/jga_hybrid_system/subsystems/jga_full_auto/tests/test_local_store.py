"""Local store + job-runner tests. Run: python -m unittest discover -s tests -v"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jga_auto.pipeline import Job, GateError
from jga_auto.drafting import draft_for
from jga_auto import local_store
from jga_auto.taste import TasteCorpus


class TestLocalStore(unittest.TestCase):
    def setUp(self):
        # Point the store at a scratch dir so tests never touch real jobs.
        self.scratch = os.path.join(os.path.dirname(__file__), "_scratch")
        os.makedirs(self.scratch, exist_ok=True)
        local_store.BASE = self.scratch
        local_store.JOBS_FILE = os.path.join(self.scratch, "jobs.json")
        local_store.INVOICES_FILE = os.path.join(self.scratch, "invoices.json")
        for path in (local_store.JOBS_FILE, local_store.INVOICES_FILE):
            if os.path.exists(path):
                os.remove(path)

    def test_round_trip_preserves_state_and_gates(self):
        job = Job(customer="Shop", package="Quick Creative Help",
                  brief="flyer")
        job.scope()
        job.mark_deposit_cleared()
        job.submit_draft(draft_for("flyer", []))
        job_id = local_store.save_job(job)
        loaded = local_store.load_job(job_id)
        self.assertEqual(loaded.state, "PROOF_SENT")
        self.assertEqual(loaded.price_cents, 7500)
        self.assertEqual(loaded.deposit_cents, 2625)
        # Gates still enforced after load: cannot deliver from PROOF_SENT.
        with self.assertRaises(GateError):
            loaded.deliver_clean_files()
        loaded.client_decision(approved=True)
        loaded.mark_final_paid()
        loaded.deliver_clean_files()
        self.assertEqual(loaded.state, "DONE")

    def test_list_shows_saved_jobs(self):
        job = Job(customer="Shop", package="Quick Creative Help",
                  brief="flyer")
        job.scope()
        job_id = local_store.save_job(job)
        rows = local_store.list_jobs()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], job_id)
        self.assertEqual(rows[0][3], "AWAITING_DEPOSIT")

    def test_unknown_job_raises(self):
        with self.assertRaises(KeyError):
            local_store.load_job("job-999")


class TestTasteCorpusV2(unittest.TestCase):
    def test_no_placeholders_remain(self):
        corpus = TasteCorpus.load()
        self.assertEqual(corpus.version, "v2")
        self.assertEqual(len(corpus.items), 6)
        for item in corpus.items:
            self.assertNotIn("Replace with", item["note"])
        names = corpus.names()
        self.assertTrue(any("STREET BOLD" in n for n in names))
        self.assertTrue(any("QUIET PREMIUM" in n for n in names))


if __name__ == "__main__":
    unittest.main()
