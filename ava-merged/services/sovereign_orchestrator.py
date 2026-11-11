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

app = FastAPI(title="AVA Sovereign Orchestrator (corrected)", version="2.2.0")

BRAID_URL = os.getenv("BRAID_URL", "http://127.0.0.1:8781")
BRAIN_URL = os.getenv("BRAIN_URL", "http://127.0.0.1:8773")


class AgentIntent(BaseModel):
    context_stream: str
    use_llm: bool = False
    llm_model: Optional[str] = None


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
            "llm_provider": "gemini" if intent.use_llm else ""}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8775)
