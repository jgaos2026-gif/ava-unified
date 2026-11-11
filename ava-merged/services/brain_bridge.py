"""AVA Brain Bridge — CORRECTED version.

Same /inference contract as the pasted version, with two corrections:
1. /health endpoint (the pasted version had none, so a dashboard
   could not measure it — it could only label it ACTIVE).
2. The fallback response is labeled FALLBACK and states plainly that
   no model answered. It is not presented as reasoning, and the
   orchestrator must not present it as a model completion.

Model and host come from AVA_LLM_MODEL / OLLAMA_HOST environment
variables (defaults llama3 / http://127.0.0.1:11434). No model is
bundled, installed, or claimed here.

Gemini wiring (2026-11-04, John's "Do it"): opt-in only. When a request
sets use_llm=True, the brain ALSO asks Gemini (services/llm_vault_client)
for a proposal and returns it in llm_proposal with llm_status. The
proposal never replaces the deterministic Ollama/fallback completion,
never executes anything, and is empty when Gemini defers. Default
requests (use_llm absent/false) behave exactly as before.
"""
import asyncio
import os
from typing import Optional

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

try:
    from .llm_vault_client import propose as gemini_propose
except ImportError:  # run as a bare script from the services directory
    from llm_vault_client import propose as gemini_propose

app = FastAPI(title="AVA Brain Bridge (corrected)", version="2.2.0")

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
MODEL_NAME = os.getenv("AVA_LLM_MODEL", "llama3")
GEMINI_MODEL = os.getenv("AVA_LLM_MODEL", "")


class InferenceRequest(BaseModel):
    prompt: str
    temperature: float = 0.3
    system_instruction: str = "You are the AVA Core Intelligence Engine. Execute cleanly."
    use_llm: bool = False
    llm_model: Optional[str] = None


@app.get("/health")
async def health():
    return {"ok": True, "service": "AVA_BRAIN_BRIDGE",
            "model_configured": MODEL_NAME, "ollama_host": OLLAMA_HOST,
            "llm_provider": "gemini",
            "llm_model_configured": GEMINI_MODEL or "unset",
            "llm_wired": True}


@app.post("/inference")
async def route_inference(payload: InferenceRequest):
    result = None
    async with httpx.AsyncClient(trust_env=False) as client:
        try:
            resp = await client.post(
                f"{OLLAMA_HOST}/api/generate",
                json={"model": MODEL_NAME,
                      "prompt": f"{payload.system_instruction}\n\nContext Input: {payload.prompt}",
                      "options": {"temperature": payload.temperature},
                      "stream": False},
                timeout=10.0)
            if resp.status_code == 200:
                result = {"completion": resp.json().get("response"),
                          "provider": "Ollama local pool", "fallback": False}
        except Exception:
            pass
    if result is None:
        result = {"completion": "[FALLBACK] No model answered; system state safe.",
                  "provider": "FALLBACK_NO_MODEL", "fallback": True}
    # Opt-in Gemini proposal: additive only, never replaces completion.
    if payload.use_llm:
        model = payload.llm_model or GEMINI_MODEL
        llm = await asyncio.to_thread(
            gemini_propose, payload.prompt, model)
        result["llm_proposal"] = llm.get("text", "") if llm.get("status") == "PROPOSED" else ""
        result["llm_status"] = llm.get("status")
        result["llm_reason"] = llm.get("reason")
        result["llm_model"] = llm.get("model", model)
        result["llm_provider"] = "gemini"
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8773)
