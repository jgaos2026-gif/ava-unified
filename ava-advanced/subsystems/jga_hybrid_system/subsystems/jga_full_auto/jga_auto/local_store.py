"""Local JSON store — run real jobs with no keys, no cloud, no spending.

Supabase is still the cloud backend when keys exist. Until then, jobs
and invoices persist here (data/store/*.json) so a first paying job can
be run on the owner's own machine today. The store never bypasses the
pipeline: it only records states the pipeline reached legally, and a
loaded job is subject to exactly the same gates as a fresh one.
"""
import json
import os
from dataclasses import asdict

from .drafting import Draft
from .pipeline import Job

BASE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "store",
)
JOBS_FILE = os.path.join(BASE, "jobs.json")
INVOICES_FILE = os.path.join(BASE, "invoices.json")


def _read(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write(path, rows):
    os.makedirs(BASE, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)


def _draft_to_dict(draft):
    return {
        "brief": draft.brief,
        "taste_items": list(draft.taste_items),
        "engine": draft.engine,
        "mock": draft.mock,
    }


def _dict_to_draft(data):
    return Draft(data["brief"], data["taste_items"], data["engine"],
                 mock=data.get("mock", False))


def job_to_record(job, job_id):
    data = asdict(job)
    data["drafts"] = [_draft_to_dict(d) for d in job.drafts]
    return {"id": job_id, "job": data}


def record_to_job(record):
    data = dict(record["job"])
    data["drafts"] = [_dict_to_draft(d) for d in data.get("drafts", [])]
    return Job(**data)


def _next_id(jobs):
    return "job-%03d" % (len(jobs) + 1)


def save_job(job, job_id=None):
    """Persist a job; returns its id. Re-saving with an id overwrites."""
    jobs = _read(JOBS_FILE)
    if job_id is None:
        job_id = _next_id(jobs)
    record = job_to_record(job, job_id)
    for i, existing in enumerate(jobs):
        if existing["id"] == job_id:
            jobs[i] = record
            break
    else:
        jobs.append(record)
    _write(JOBS_FILE, jobs)
    return job_id


def load_job(job_id):
    for record in _read(JOBS_FILE):
        if record["id"] == job_id:
            return record_to_job(record)
    raise KeyError(f"no stored job: {job_id}")


def list_jobs():
    return [
        (r["id"], r["job"]["customer"], r["job"]["package"], r["job"]["state"])
        for r in _read(JOBS_FILE)
    ]


def save_invoice(invoice):
    rows = _read(INVOICES_FILE)
    rows.append(asdict(invoice))
    _write(INVOICES_FILE, rows)
    return len(rows)
