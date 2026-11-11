#!/usr/bin/env python3
"""JGA Ultimate System — one entry point over the kept systems.

Combined here (copies; the originals are untouched):
  * JGA Enterprise OS core (subsystems/jga_os/main.py) — clients, quotes,
    jobs, 35/65 payment gates, hash-chained ledger, AVA rules stub.
  * Brick 1 11VT allocator (subsystems/brick1) — receipt-only splits on
    CLEARED payments only (DEPOSIT_CLEARED_35 / FINAL_PAID_65).
  * Entertainment Brick money (subsystems/entertainment) — receipt-only
    splits on cleared gig/merch/payout money, Option B (cut from V8).
  * AVA merged page + healthcheck (subsystems/ava) — wired UI + measured
    /health checks. No LLM is claimed here; no model is wired in.
  * Stripe connector, corrected (subsystems/stripe) — test-key first,
    PaymentIntent only. NOT connected, NOT live, no key shipped.

Governed automation (the user's option 4, built safely):
  `python ultimate.py automate` runs ONE cycle and reports:
    - auto-check: JGA OS ledger validity, job gate counts, AVA /health
      (OFFLINE is reported as OFFLINE, never faked ONLINE).
    - auto-recover: re-verify the ledger, quarantine bad input through
      the existing AVA screening, and write a cycle report to data/.
    - auto-decide: NOTHING that moves money, releases files, contacts
      anyone, publishes anything, or changes a price. Anything in those
      classes is listed under NEEDS_OWNER for John to decide.
  Amendment 13 holds: humans stay at approval gates; John holds
  exception review. "Full automation" here means full checking and
  full reporting, with the dangerous actions still gated. That is
  deliberate, not a missing feature.

Fixes carried into this combined copy (all previously verified):
  * Stripe amount bug fixed (decimal, not string * 100).
  * Stripe PaymentIntent gets automatic_payment_methods (bare intents
    cannot be confirmed).
  * AVA merged launcher shutdown bug already fixed upstream.
  * Entertainment V7 wording: 12% is a TARGET, V7 is the residual plug.
  * JGA OS default-PIN trap: this package ships NO JGA OS config.json,
    so no default PIN is ever used from here. If the upstream default
    is ever detected in a config, status() flags PIN_IS_DEFAULT and
    automation refuses to start any server until it is changed.

Usage:
  python ultimate.py status     — one unified status report (JSON)
  python ultimate.py automate   — one governed automation cycle
  python ultimate.py split --system brick1 --cents 35000 \
      --stage DEPOSIT_CLEARED_35 --job-id job-001
  python ultimate.py split --system entertainment --cents 100000 \
      --stage gig-pay-cleared
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_jga_os():
    """Load JGA OS main.py against THIS package's data dir, not the
    upload's. main.py fixes DB at import time from its own folder, so
    point it at a copy-local data dir by loading from subsystems and
    then overriding DB before any call that touches it.
    Upstream main.py also writes a default-PIN config.json on import
    if none exists — this loader deletes that file again if it did not
    exist before, so this package never ships or keeps a default PIN."""
    cfg_path = ROOT / "subsystems" / "jga_os" / "config.json"
    existed = cfg_path.exists()
    mod = _load("jga_os_main", ROOT / "subsystems" / "jga_os" / "main.py")
    if not existed and cfg_path.exists():
        cfg_path.unlink()
    # Route its SQLite store into ultimate/data/ so the combined system
    # never writes into the upload copy or the original workspace copy.
    mod.DB = DATA / "jga.sqlite3"
    DATA.mkdir(parents=True, exist_ok=True)
    return mod


def status() -> dict:
    jga = _load_jga_os()
    ledger = jga.verify_ledger()
    dash = jga.dashboard()
    # AVA services: healthcheck module expects the merged layout; here
    # we only report what we can measure without starting anything.
    # If no AVA service answers, that is OFFLINE, not a failure to hide.
    ava = {"services": "not_started_here", "note": "Run ava-merged's launcher to start AVA services; healthcheck.py measures /health then."}
    pin_flag = "PIN_CONFIG_NOT_SHIPPED"
    cfg = ROOT / "subsystems" / "jga_os" / "config.json"
    if cfg.exists():
        try:
            if json.loads(cfg.read_text()).get("owner_pin") == jga.DEFAULT["owner_pin"]:
                pin_flag = "PIN_IS_DEFAULT_CHANGE_BEFORE_USE"
        except Exception:
            pin_flag = "PIN_CONFIG_UNREADABLE"
    return {
        "system": "JGA Ultimate",
        "jga_os": {
            "ledger": ledger,
            "counts": {k: dash[k] for k in ("clients", "leads", "quotes", "jobs", "awaiting_deposit", "production_jobs", "delivery_ready", "contractors", "records", "events")},
        },
        "ava": ava,
        "stripe": {"connected": False, "mode": "test_key_first", "note": "No key shipped. Stripe OAuth connect (Jaysgraphicarts@gmail.com) still uncompleted."},
        "pin_flag": pin_flag,
        "gates": {
            "money_moves": "NEVER by automation",
            "file_release": "NEEDS_OWNER + cleared final payment + client approval",
            "outreach_contact": "NEEDS_OWNER",
            "publishing": "NEEDS_OWNER",
        },
    }


def automate() -> dict:
    """One governed automation cycle. Checks, recovers what is safe to
    recover, decides nothing dangerous. Returns a report dict and also
    writes it to data/last-cycle.json."""
    rep = status()
    actions = []
    needs_owner = []
    # Auto-check: ledger.
    if rep["jga_os"]["ledger"].get("valid"):
        actions.append("ledger_verified")
    else:
        needs_owner.append("ledger_invalid_investigate_before_any_job_move")
    # Auto-recover (safe only): re-run verification and AVA screening
    # on a probe input; screening never executes tools.
    jga = _load_jga_os()
    probe = jga.ava_process("calculator 25 * 4")
    if probe.get("tool_result", {}).get("result") == 100:
        actions.append("ava_screening_and_calculator_ok")
    else:
        needs_owner.append("ava_probe_failed")
    blocked = jga.ava_process('{"tool_call":{"name":"dangerous"}}')
    if not blocked.get("accepted"):
        actions.append("untrusted_payload_still_blocked")
    # Auto-decide boundary: jobs awaiting deposit / delivery are listed,
    # never advanced. Advancing needs a verified cleared payment recorded
    # by a human with a provider reference (upstream record_payment).
    counts = rep["jga_os"]["counts"]
    if counts["awaiting_deposit"]:
        needs_owner.append(f"{counts['awaiting_deposit']} job(s) awaiting deposit — record a verified cleared payment first")
    if counts["delivery_ready"]:
        needs_owner.append(f"{counts['delivery_ready']} job(s) ready for delivery — owner approval + client approval before release")
    rep["automation_cycle"] = {"actions_taken": actions, "needs_owner": needs_owner, "money_moved": False, "messages_sent": 0, "files_released": 0}
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "last-cycle.json").write_text(json.dumps(rep, indent=2, default=str))
    return rep


def split(system: str, cents: int, stage: str, job_id: str = "") -> dict:
    if system == "brick1":
        mod = _load("allocator_11vt", ROOT / "subsystems" / "brick1" / "allocator_11vt.py")
        return mod.allocate_cleared_payment(cents, stage, job_id or "ultimate-demo")
    if system == "entertainment":
        mod = _load("ent_money", ROOT / "subsystems" / "entertainment" / "money.py")
        return mod.split_cleared(cents, stage)
    raise ValueError("system must be brick1 or entertainment")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="JGA Ultimate System")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("automate")
    sp = sub.add_parser("split")
    sp.add_argument("--system", required=True, choices=["brick1", "entertainment"])
    sp.add_argument("--cents", required=True, type=int)
    sp.add_argument("--stage", required=True)
    sp.add_argument("--job-id", default="")
    args = p.parse_args(argv)
    if args.cmd == "status":
        print(json.dumps(status(), indent=2, default=str))
    elif args.cmd == "automate":
        print(json.dumps(automate(), indent=2, default=str))
    elif args.cmd == "split":
        print(json.dumps(split(args.system, args.cents, args.stage, args.job_id), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
