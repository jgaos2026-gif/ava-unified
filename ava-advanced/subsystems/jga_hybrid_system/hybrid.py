#!/usr/bin/env python3
"""JGA Hybrid System — one governor over all the OTHER kept systems.

This is the second combined system, built at John's "Combine all other
system file to create a hybrid system". It does NOT replace jga-ultimate:
ultimate is the operations system (JGA OS + money splits + AVA page).
This hybrid is the governed-intelligence layer: the AVA hybrid prototype
(identity, memory, gateway, decision, pillars) governing the same money
and job systems, with MicroSpine / Gatekeeper as a second sealed ledger
and the Phoenix braid kernel + pulse prototype as included subsystems.

Honest hybrid rule — read before trusting any output:
  * There is ONE governor (AVA hybrid Gateway + DecisionEngine), but
    there are SEPARATE ledgers that are NEVER merged into one chain:
    the hybrid memory ledger, the MicroSpine chain, the JGA OS event
    chain, and the Entertainment Brick ledger each keep their own
    seals. Merging chains would destroy their tamper evidence.
    Hybrid means governed together, not fused into one ledger.
  * Every hybrid decision is labeled SIMULATION until it is verified
    through the normal OBSERVED -> VERIFY -> VALIDATE -> CERTIFY ->
    COMMIT pipeline. A simulation never becomes a committed fact.
  * Money rules are unchanged from ultimate: splits only on CLEARED
    money, receipt-only, no bank movement, no message sent, no file
    released, no outreach without John. The governor cannot override
    a gate — a candidate that fails a constitutional or trust check
    is skipped, however high it scores.

Subsystems (copies; originals untouched):
  subsystems/ava_hybrid/        identity, ledger, memory, gateway,
                                decision, emotion, capsule, did, zk,
                                symbolic, dream, consensus, selfmodel,
                                capability, pulse
  subsystems/micro_spine.py     append-only binary ledger (needs a
                                secret from BCT_SECRET / 0600 keyfile;
                                self-test uses an isolated tmp dir)
  subsystems/bct_gatekeeper.py  106-byte envelope, Ed25519 registry
  subsystems/pulse_*.py         pulse prototype (scratch; needs a haven
                                server to run live — included, not run)
  subsystems/jga_full_auto/     full Brick 1 pipeline (mock drafting;
                                John is the designer until an engine
                                is chosen; Phase B gate unmet)
  subsystems/entertainment_brick/  full Entertainment Brick (96/96)
  subsystems/phoenix_kernel/    Rust braid kernel v0.3.0 (cargo test
                                21/21 upstream; run cargo test here
                                to re-verify — it is NOT a Python import)

Usage:
  python hybrid.py check        — governor probes + money splits
  python hybrid.py govern --claim "TEXT" --source NAME
  python hybrid.py decide       — demo decision for "First cash"
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SUB = ROOT / "subsystems"
sys.path.insert(0, str(SUB))

from ava_hybrid import (  # noqa: E402
    Memory, Ledger, Gateway, Goal, Outcome, Candidate, DecisionEngine,
)
import micro_spine  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def govern(claim: str, sources: list[str]):
    """Run one claim through the hybrid pipeline. Returns (state, ledger_revision)."""
    mem, led = Memory(), Ledger()
    rec = mem.observe(claim, sources=sources)
    verified = mem.verify(rec)
    if verified:
        mem.validate(rec)
        mem.certify(rec, True)
        mem.commit(rec, led)
    return {"claim": claim, "state": rec.state, "ledger_revision": led.revision, "verified": verified}


def decide_demo():
    mem, led = Memory(), Ledger()
    gw = Gateway({"read", "decide"}, mem)
    goal = Goal("First cash from Brick 1", "a paying client, job delivered, paid in full")
    eng = DecisionEngine(gateway=gw)
    cands = [
        Candidate("discount job now", capability="decide", outcomes=[Outcome("cash today, client unhappy, no repeat", 0.9, 0.2)]),
        Candidate("proper job at site price", capability="decide", outcomes=[Outcome("paying client, delivered, paid in full", 0.7, 1.0)]),
        Candidate("skip deposit gate", capability="decide", constitutional_ok=False, outcomes=[Outcome("paid in full", 1.0, 1.0)]),
    ]
    d = eng.decide(goal, cands, flipped_scores={"discount job now": 0.2, "proper job at site price": 0.9, "skip deposit gate": 1.0})
    return {"goal": goal.name, "chosen": d.action, "status": d.status, "score": d.score, "proof_level": d.proof_level}


def check() -> dict:
    mem, led = Memory(), Ledger()
    gw = Gateway({"read", "decide"}, mem)
    deferrals = {}
    for draft, label in [
        ({"unknown_fields": ["x"]}, "unknown_field"),
        ({"capability": "send_payment"}, "capability_outside_grant"),
        ({"digest": "a", "source_digest": "b"}, "digest_mismatch"),
        ({"token_estimate": 100, "token_actual": 120}, "token_overrun"),
        ({"claims": ["John won the lottery"], "sources": ["x"]}, "ungrounded_claim"),
        ({"claims": ["x"], "sources": []}, "missing_source"),
    ]:
        r = gw.check(draft)
        deferrals[label] = {"allowed": r.allowed, "reason": r.reason}
    sourced = govern("John lives in Peoria", ["john-2026-10-22"])
    unsourced = govern("John won the lottery", [])
    # MicroSpine refuses to run without a secret (by design, no default).
    # For this self-test only, use a freshly generated throwaway secret
    # in-process, and restore the environment afterwards. This is NOT a
    # production secret and is never written to any file.
    import os as _os
    import secrets as _secrets

    _had_secret = "BCT_SECRET" in _os.environ or "BCT_SECRET_FILE" in _os.environ
    if not _had_secret:
        _os.environ["BCT_SECRET"] = _secrets.token_hex(16)
    try:
        spine_selftest = micro_spine.run_selftest()
    finally:
        if not _had_secret:
            _os.environ.pop("BCT_SECRET", None)
    alloc = _load("hybrid_alloc", SUB / "jga_full_auto" / "jga_auto" / "allocator_11vt.py")
    brick1 = alloc.allocate_cleared_payment(35000, "DEPOSIT_CLEARED_35", "hybrid-demo")
    ent = _load("hybrid_money", SUB / "entertainment_brick" / "money.py")
    ent_split = ent.split_cleared(100000, "gig-pay-cleared")
    return {
        "system": "JGA Hybrid System",
        "governor": "AVA hybrid Gateway + DecisionEngine (SIMULATION unless COMMIT)",
        "gateway_deferrals": deferrals,
        "sourced_claim": sourced,
        "unsourced_claim": unsourced,
        "decision_demo": decide_demo(),
        "micro_spine_selftest": spine_selftest,
        "brick1_split_balanced": brick1.get("balanced"),
        "entertainment_split_receipt": ent_split.get("receipt_hash", "")[:16] + "...",
        "ledgers": "separate by design — hybrid, micro-spine, JGA OS, entertainment — never fused",
        "money_moved": False,
        "llm_connected": False,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="JGA Hybrid System")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    g = sub.add_parser("govern")
    g.add_argument("--claim", required=True)
    g.add_argument("--source", default="")
    sub.add_parser("decide")
    args = p.parse_args(argv)
    if args.cmd == "check":
        print(json.dumps(check(), indent=2, default=str))
    elif args.cmd == "govern":
        print(json.dumps(govern(args.claim, [args.source] if args.source else []), indent=2, default=str))
    elif args.cmd == "decide":
        print(json.dumps(decide_demo(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
