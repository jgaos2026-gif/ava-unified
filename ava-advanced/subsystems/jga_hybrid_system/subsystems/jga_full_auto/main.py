"""Jay's Graphic Arts full-auto pipeline — CLI.

Commands:
  python main.py --demo                    one sample job end to end (mock drafting)
  python main.py --gates                   error-rate report on a sample review set
  python main.py --new --customer NAME --package PACKAGE --brief TEXT
                                               scope + store a real job (no money moved)
  python main.py --list                    list stored jobs
  python main.py --advance JOB_ID STEP     move a stored job one legal step:
      deposit  = mark the 35% deposit cleared (only when money actually cleared)
      draft    = produce a proof (mock drafting until an engine is chosen)
      approve  = client approved the proof
      reject   = client asked for a revision (within the package limit)
      pay      = mark final payment received
      deliver  = release clean files + invoice (needs payment + approval)
      followup = post-delivery follow-up

Every step is enforced by the pipeline gates. A blocked step prints the
gate message and changes nothing. No command moves money — deposits and
payments are recorded only when John confirms they actually cleared.
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jga_auto import config
from jga_auto.pipeline import Job, GateError
from jga_auto.drafting import draft_for
from jga_auto.taste import TasteCorpus
from jga_auto.books import build_invoice
from jga_auto.gates import ErrorTracker
from jga_auto import local_store


def run_demo():
    corpus = TasteCorpus.load()
    print(f"Business: {config.BUSINESS_NAME} | phase: {config.PHASE} "
          f"| taste corpus: {corpus.version} ({len(corpus.items)} refs)")
    job = Job(customer="Demo Client", package="Logo Launch",
              brief="Bold logo for a local barbershop")
    job.scope()
    print(f"Scoped: {job.package} ${job.price_cents / 100:.2f}, "
          f"deposit due ${job.deposit_cents / 100:.2f} (35%)")
    job.mark_deposit_cleared()
    draft = draft_for(job.brief, corpus.names())
    job.submit_draft(draft)
    print(f"Proof sent: {draft.describe()}")
    job.client_decision(approved=True)
    job.mark_final_paid()
    job.deliver_clean_files()
    inv = build_invoice(job)
    print(f"Delivered. Invoice receipt SHA-256: {inv.receipt_sha256[:16]}...")
    job.follow_up()
    job_id = local_store.save_job(job)
    local_store.save_invoice(inv)
    print(f"Final state: {job.state} — pipeline complete, no human in production.")
    print(f"Stored locally as {job_id} (data/store/jobs.json).")


def run_gates():
    tracker = ErrorTracker()
    # Sample review set: 20 reviewed, 1 error -> rate 0.05, at threshold.
    for i in range(20):
        tracker.record(error_found=(i == 7))
    print("Task Error Rate gate — " + tracker.report())


def run_new(customer, package, brief):
    job = Job(customer=customer, package=package, brief=brief)
    job.scope()
    job_id = local_store.save_job(job)
    print(f"Job {job_id}: {package} for {customer} — scoped "
          f"${job.price_cents / 100:.2f}, deposit due "
          f"${job.deposit_cents / 100:.2f} (35%).")
    print("Deposit NOT cleared: run --advance %s deposit only when the "
          "money has actually cleared." % job_id)


def run_list():
    rows = local_store.list_jobs()
    if not rows:
        print("No stored jobs yet. Run --new to scope one.")
        return
    for job_id, customer, package, state in rows:
        print(f"{job_id} | {customer} | {package} | {state}")


def run_advance(job_id, step):
    job = local_store.load_job(job_id)
    job.id = job_id  # so the 11VT invoice splits carry the real job id
    corpus = TasteCorpus.load()
    if step == "deposit":
        job.mark_deposit_cleared()
    elif step == "draft":
        draft = draft_for(job.brief, corpus.names())
        if job.state == "REVISING":
            job.revise(draft)
        else:
            job.submit_draft(draft)
        print(f"Proof: {draft.describe()}")
    elif step == "approve":
        job.client_decision(approved=True)
    elif step == "reject":
        job.client_decision(approved=False)
    elif step == "pay":
        job.mark_final_paid()
    elif step == "deliver":
        job.deliver_clean_files()
        inv = build_invoice(job)
        local_store.save_invoice(inv)
        print(f"Delivered. Invoice receipt SHA-256: {inv.receipt_sha256[:16]}...")
    elif step == "followup":
        job.follow_up()
    else:
        print(f"Unknown step: {step}")
        return 1
    local_store.save_job(job, job_id)
    print(f"{job_id} -> {job.state}")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--gates", action="store_true")
    parser.add_argument("--new", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--advance", nargs=2, metavar=("JOB_ID", "STEP"))
    parser.add_argument("--customer")
    parser.add_argument("--package")
    parser.add_argument("--brief")
    args = parser.parse_args()
    try:
        if args.gates:
            run_gates()
        elif args.new:
            if not (args.customer and args.package and args.brief):
                parser.error("--new needs --customer, --package and --brief")
            run_new(args.customer, args.package, args.brief)
        elif args.list:
            run_list()
        elif args.advance:
            return run_advance(args.advance[0], args.advance[1])
        else:
            run_demo()
    except GateError as exc:
        print(f"Gate blocked this: {exc}")
        return 1
    except KeyError as exc:
        print(exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
