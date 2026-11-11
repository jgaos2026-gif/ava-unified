"""Supabase backend for the Brick 1 pipeline.

The supabase package is imported lazily so the pipeline, gates, and
tests all run without keys or the package installed. With keys set in
.env, this store persists jobs, proofs, invoices, and error samples to
the brick1_* tables (see sql/001_brick1_tables.sql).

Server-side use takes the service-role key. That key never ships to a
client and never appears in logs.
"""
from . import config


class SupabaseStore:
    def __init__(self, url=None, key=None):
        self.url = url or config.SUPABASE_URL
        self.key = key or config.SUPABASE_KEY
        self._client = None

    @property
    def client(self):
        if self._client is None:
            if not self.url or not self.key:
                raise RuntimeError(
                    "SUPABASE_URL and SUPABASE_KEY must be set in .env "
                    "before the Supabase backend can run."
                )
            try:
                from supabase import create_client
            except ImportError as exc:
                raise RuntimeError(
                    "supabase package not installed: pip install -r requirements.txt"
                ) from exc
            self._client = create_client(self.url, self.key)
        return self._client

    def upsert_job(self, job):
        payload = {
            "customer": job.customer,
            "package": job.package,
            "brief": job.brief,
            "state": job.state,
            "price_cents": job.price_cents,
            "deposit_cleared": job.deposit_cleared,
            "final_paid": job.final_paid,
            "client_approved": job.client_approved,
            "revisions_used": job.revisions_used,
        }
        return self.client.table("brick1_jobs").upsert(payload).execute()

    def record_error_sample(self, job_ref, error_found):
        return self.client.table("brick1_error_samples").insert({
            "job_ref": job_ref,
            "error_found": bool(error_found),
        }).execute()
