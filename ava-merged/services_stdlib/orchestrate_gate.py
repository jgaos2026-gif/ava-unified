"""Mandatory pre-brain gates for AVA /orchestrate (round 3, Finding 03).

Round 1 found that /orchestrate sent every request straight to the
brain service with no spine/truth gate in front of it. This module is
the Python-side gate the orchestrator MUST pass a request through
before any braid or brain call. A failing gate refuses the request;
the brain is never called.

What the gate checks (real checks, against modules that exist in
this repo — nothing here is a stub that always passes):
  1. identity / scopes — a presented scope token must verify
     (scope_tokens.resolve_scopes). In strict mode
     (AVA_REQUIRE_AUTHENTICATED_SCOPES=true) a missing token refuses
     too. In default mode a missing token passes as declared-untrusted,
     exactly like the history store.
  2. history chain — the WARM history chain must verify fresh from
     disk (HistoryStore.verify_chain). A broken chain refuses the
     request: the brain must not reason on top of corrupted memory.
     No history store configured at all also refuses (fail closed).

What the gate does NOT check (honest boundary):
  The SB688 runtime's SpineGovernor + LiquidTruthNodeMesh are
  TypeScript (sb688-public); NO Python spine/truth module exists in
  this repo — grep for SpineGovernor / LiquidTruthNodeMesh in
  ava-merged finds nothing callable. So this gate records
  spine_runtime: "NOT_WIRED_TS_RUNTIME" and does NOT pretend to call
  it. Wiring the real TS runtime (HTTP call to the SB688 truth
  service, or a Python port) is the documented follow-up; until
  then the gate's refusals come from the scope + chain checks above,
  which are the checks this repo can actually perform. A gate that
  claimed spine approval without calling the spine would be a fake
  gate, and is worse than an honest NOT_WIRED.

Stdlib only. The orchestrator (FastAPI) calls run_pre_brain_gates()
at the top of its /orchestrate handler, before the braid search and
before the brain call, and returns GATE_REFUSED when it fails.
"""
try:
    from services_stdlib import history_store as _history_store_mod
    from services_stdlib import scope_tokens as _scope_tokens
except Exception:  # noqa: BLE001 - plain-import layout fallback
    try:
        import history_store as _history_store_mod
        import scope_tokens as _scope_tokens
    except Exception:  # noqa: BLE001 - gates unavailable, fail closed
        _history_store_mod = None
        _scope_tokens = None


class GateError(Exception):
    """The pre-brain gate refused the request. The message names the
    failing check; it never contains a token or a key."""


def run_pre_brain_gates(intent_text, history_store=None, scope_token=None,
                        scopes=None, require_authenticated=None,
                        authority=None):
    """Run the mandatory pre-brain gates for one /orchestrate request.
    Returns a report dict; never raises for a failing check.
    {"ok": True} means the request may proceed to the brain.
    {"ok": False, "error": ...} means it must be refused and the
    brain must not be called. `checks` names each check and its
    outcome, including spine_runtime NOT_WIRED (see module docstring).
    """
    checks = {
        "scope": {"ok": True, "detail": "no token presented"},
        "history_chain": {"ok": False, "detail": "no history store"},
        "spine_runtime": {
            "ok": True,
            "detail": "NOT_WIRED_TS_RUNTIME: no Python "
                      "SpineGovernor/LiquidTruthNodeMesh module exists "
                      "in this repo; the TS-runtime wiring is the "
                      "follow-up (see module docstring). This check "
                      "does not approve anything."},
    }
    # 1. identity / scopes.
    if _scope_tokens is None:
        checks["scope"] = {"ok": False,
                           "detail": "scope_tokens module not loaded"}
        return {"ok": False, "checks": checks,
                "error": "pre-brain gate refused: scope_tokens module "
                         "not loaded (cannot authenticate scopes)",
                "scope_trust": "unavailable"}
    _, scope_trust, refusal = _scope_tokens.resolve_scopes(
        scopes, scope_token, authority=authority,
        require_authenticated=require_authenticated)
    checks["scope"] = {"ok": refusal is None,
                       "detail": "scope_trust=%s" % scope_trust}
    if refusal is not None:
        return {"ok": False, "checks": checks,
                "error": "pre-brain gate refused (scope): %s"
                         % refusal.get("error"),
                "scope_trust": scope_trust}
    # 2. history chain, verified fresh from disk.
    if history_store is None:
        return {"ok": False, "checks": checks,
                "error": "pre-brain gate refused (history_chain): no "
                         "history store configured for /orchestrate",
                "scope_trust": scope_trust}
    chain = history_store.verify_chain()
    checks["history_chain"] = {
        "ok": bool(chain.get("ok")),
        "detail": "state=%s entries=%s" % (chain.get("state"),
                                            chain.get("entries"))}
    if not chain.get("ok"):
        return {"ok": False, "checks": checks,
                "error": "pre-brain gate refused (history_chain): "
                         "history chain does not verify (state=%s)"
                         % chain.get("state"),
                "scope_trust": scope_trust}
    return {"ok": True, "checks": checks, "error": None,
            "scope_trust": scope_trust}
