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
"""
import os

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="AVA Brain Bridge (corrected)", version="2.1.0")

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
MODEL_NAME = os.getenv("AVA_LLM_MODEL", "llama3")


class InferenceRequest(BaseModel):
    prompt: str
    temperature: float = 0.3
    system_instruction: str = "You are the AVA Core Intelligence Engine. Execute cleanly."


@app.get("/health")
async def health():
    return {"ok": True, "service": "AVA_BRAIN_BRIDGE",
            "model_configured": MODEL_NAME, "ollama_host": OLLAMA_HOST}


@app.post("/inference")
async def route_inference(payload: InferenceRequest):
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
                return {"completion": resp.json().get("response"),
                        "provider": "Ollama local pool", "fallback": False}
        except Exception:
            pass
    return {"completion": "[FALLBACK] No model answered; system state safe.",
            "provider": "FALLBACK_NO_MODEL", "fallback": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8773)
