"""AVA Sovereign Orchestrator — CORRECTED version.

Fixes vs the pasted version:
1. Correct filename: sovereign_orchestrator.py, matching the existing
   AVA runtime (the pasted launcher referenced a system_orchestrator.py
   that does not exist). Service URLs are configurable via
   BRAID_URL / BRAIN_URL environment variables instead of hardcoded
   localhost ports in two places.
2. /health endpoint, so health can be measured, not labeled.
3. The orchestrator reports whether the brain answer was a fallback
   (brain_fallback: true/false) instead of letting a fallback pass as
   a model completion. vector_context_injected is true only when a
   real braid match was returned, not when the braid timed out.

Endpoints: GET /health, POST /orchestrate, WS /telemetry.

Pre-brain gates (round 3, Finding 03 — MANDATORY): /orchestrate
passes every request through services_stdlib/orchestrate_gate
run_pre_brain_gates() BEFORE the braid search and BEFORE the brain
call. The gate checks the scope token (a presented token must
verify; strict mode AVA_REQUIRE_AUTHENTICATED_SCOPES=true also
requires one) and re-verifies the WARM history chain fresh from
disk. A failing gate returns GATE_REFUSED and the brain is never
called. The SB688 SpineGovernor / LiquidTruthNodeMesh (TypeScript)
is NOT wired here — no Python spine/truth module exists in this
repo, and the gate records spine_runtime NOT_WIRED honestly rather
than faking an approval; wiring the real TS runtime is the
follow-up. See services_stdlib/orchestrate_gate.py.

Gemini wiring (2026-11-04, John's "Do it"): opt-in only. When a request
sets use_llm=True, the orchestrator passes it to the brain, which
returns a Gemini proposal in llm_proposal. The proposal is additive
only: it never replaces ai_reasoning_output, never executes anything,
and brain_fallback stays True unless the proposal actually returned.
Default requests behave exactly as before.
"""
import json
import os
from typing import List, Optional

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

try:
    from services_stdlib import history_store as _history_store_mod
    from services_stdlib import orchestrate_gate as _gate
except Exception:  # noqa: BLE001 - plain-import layout fallback
    _history_store_mod = None
    _gate = None

app = FastAPI(title="AVA Sovereign Orchestrator (corrected)", version="2.3.0")

BRAID_URL = os.getenv("BRAID_URL", "http://127.0.0.1:8781")
BRAIN_URL = os.getenv("BRAIN_URL", "http://127.0.0.1:8773")

# The WARM history store the pre-brain gate verifies. Built lazily
# (constructing it creates the WARM directory); a store that cannot
# be built leaves the gate with no store, and the gate then refuses
# every request (fail closed) instead of running ungated.
_HISTORY_STORE = None
_HISTORY_STORE_FAILED = False


def _get_history_store():
    global _HISTORY_STORE, _HISTORY_STORE_FAILED
    if _HISTORY_STORE is not None:
        return _HISTORY_STORE
    if _HISTORY_STORE_FAILED or _history_store_mod is None:
        return None
    try:
        _HISTORY_STORE = _history_store_mod.HistoryStore()
    except Exception:
        _HISTORY_STORE_FAILED = True
        return None
    return _HISTORY_STORE


class AgentIntent(BaseModel):
    context_stream: str
    use_llm: bool = False
    llm_model: Optional[str] = None
    # Signed scope token for the pre-brain gate (optional in default
    # mode; required when AVA_REQUIRE_AUTHENTICATED_SCOPES=true).
    scope_token: Optional[str] = None


class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: str):
        for ws in list(self.active):
            try:
                await ws.send_text(message)
            except Exception:
                pass


manager = ConnectionManager()


@app.get("/health")
async def health():
    return {"ok": True, "service": "AVA_SOVEREIGN_ORCHESTRATOR"}


@app.websocket("/telemetry")
async def telemetry(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            data = await ws.receive_text()
            await manager.broadcast(f"[Telemetry] {data}")
    except WebSocketDisconnect:
        manager.disconnect(ws)


@app.post("/orchestrate")
async def orchestrate(intent: AgentIntent):
    # MANDATORY pre-brain gates (round 3, Finding 03). This runs
    # BEFORE the braid search and BEFORE the brain call: a refused
    # request never reaches the brain service. The gate module itself
    # is stdlib-only; if it failed to import, refuse rather than run
    # ungated.
    if _gate is None:
        return {"status": "GATE_REFUSED",
                "error": "pre-brain gate unavailable: orchestrate_gate "
                         "module did not load",
                "gate": {"ok": False, "checks": {},
                         "scope_trust": "unavailable"}}
    gate = _gate.run_pre_brain_gates(
        intent.context_stream, history_store=_get_history_store(),
        scope_token=intent.scope_token)
    if not gate["ok"]:
        return {"status": "GATE_REFUSED", "error": gate["error"],
                "gate": gate}
    context_memory = None
    async with httpx.AsyncClient(trust_env=False) as client:
        try:
            r = await client.post(f"{BRAID_URL}/search",
                                  json={"query_text": intent.context_stream,
                                        "top_k": 1}, timeout=5.0)
            matches = r.json().get("matches", [])
            if matches:
                context_memory = matches[0]["text"]
        except Exception:
            context_memory = None
        prompt = (f"Long-Term Memory Data Match: {context_memory}\n"
                  f"Active Intent Channel: {intent.context_stream}")
        brain_fallback = True
        brain_response = "[FALLBACK] No model answered; system state safe."
        llm_proposal = ""
        llm_status = "NOT_REQUESTED"
        llm_model = intent.llm_model or ""
        try:
            body = {"prompt": prompt, "temperature": 0.2,
                    "use_llm": intent.use_llm}
            if intent.llm_model:
                body["llm_model"] = intent.llm_model
            r = await client.post(f"{BRAIN_URL}/inference",
                                  json=body, timeout=30.0)
            data = r.json()
            brain_response = data.get("completion", brain_response)
            brain_fallback = bool(data.get("fallback", False))
            llm_proposal = data.get("llm_proposal", "")
            llm_status = data.get("llm_status", "NOT_REQUESTED")
            llm_model = data.get("llm_model", llm_model)
            if intent.use_llm and llm_status != "PROPOSED":
                brain_fallback = True
        except Exception:
            pass
    await manager.broadcast(json.dumps(
        {"event": "ORCHESTRATION_CYCLE_COMPLETE",
         "intent_processed": intent.context_stream}))
    return {"status": "COGNITIVE_CYCLE_RESOLVED",
            "vector_context_injected": context_memory is not None,
            "brain_fallback": brain_fallback,
            "ai_reasoning_output": brain_response,
            "llm_proposal": llm_proposal,
            "llm_status": llm_status,
            "llm_model": llm_model,
            "llm_provider": "gemini" if intent.use_llm else "",
            "pre_brain_gate": gate}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8775)
