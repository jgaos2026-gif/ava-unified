"""AVA Merged — LLM connector (added 2026-11-04 at John's "Connect the merged AVA package here").

What this is, and what it is NOT:
- This is a STANDALONE connector module. It does NOT modify brain_bridge,
  sovereign_orchestrator, vault, braid, or any other core service, and it
  is NOT wired into /inference or /orchestrate yet. Wiring it into the mesh
  is a separate step, after a live test passes here.
- The model PROPOSES text only. It never executes a tool call, never moves
  money, never changes a policy, and never writes to the vault or ledger.
  A response containing a tool-shaped marker is DEFERRED, not executed.
- The API key is read ONLY from the environment (AVA_LLM_API_KEY). It is
  never written to a file, never logged, never printed, and never passed
  as a command-line argument. If the key is absent, status is
  llm_connected=false and propose() defers without touching the network.
- Provider and model are NOT hardcoded as John's choice. They come from
  the environment: AVA_LLM_PROVIDER (default "gemini" after John's
  2026-11-04 switch from OpenAI to Gemini for AVA; OpenAI stays
  connected but unused for AVA) and AVA_LLM_MODEL (no default: if unset,
  status is NOT_CONNECTED, so no model is silently assumed).

Supported providers in this version:
- gemini: POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
  with x-goog-api-key header (NOT Bearer — Bearer is rejected for native
  generateContent), JSON {"contents": [{"parts": [{"text": ...}]}]}.
  Response text is taken from candidates[0].content.parts[].text.
- openai-responses: POST https://api.openai.com/v1/responses
  with Authorization: Bearer <key>, JSON {"model": ..., "input": ...}.
  Response text is taken from output_text, or from output[].content[]
  text parts. Anything else is a DEFER, not a guess.

Usage:
    python llm_connector.py status
    python llm_connector.py propose "Say hello in one sentence."
"""
import json
import os
import sys
import urllib.request
import urllib.error

TOOL_MARKERS = ("tool_call", "function_call", "execute:", "<tool", "tool:")
PROVIDERS = {
    "gemini": {
        "host": "generativelanguage.googleapis.com",
        "url_template": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
    },
    "openai-responses": {
        "host": "api.openai.com",
        "url": "https://api.openai.com/v1/responses",
    },
}


def _provider():
    return os.environ.get("AVA_LLM_PROVIDER", "gemini").strip().lower()


def _model():
    return os.environ.get("AVA_LLM_MODEL", "").strip()


def _key_present():
    return bool(os.environ.get("AVA_LLM_API_KEY"))


def status():
    """Return connection status. Never includes the key value."""
    provider = _provider()
    model = _model()
    if provider not in PROVIDERS:
        return {"llm_connected": False, "provider": provider, "model": model,
                "key_present": _key_present(),
                "reason": "UNSUPPORTED_PROVIDER"}
    if not _key_present():
        return {"llm_connected": False, "provider": provider, "model": model,
                "key_present": False, "reason": "NO_API_KEY"}
    if not model:
        return {"llm_connected": False, "provider": provider, "model": model,
                "key_present": True, "reason": "NO_MODEL_SET"}
    return {"llm_connected": True, "provider": provider, "model": model,
            "key_present": True, "reason": "KEY_AND_MODEL_PRESENT_UNVERIFIED"}


def _extract_text(body):
    if isinstance(body, dict):
        # Gemini generateContent shape
        for cand in body.get("candidates", []) or []:
            content = cand.get("content") or {}
            for part in content.get("parts", []) or []:
                if isinstance(part, dict) and part.get("text"):
                    return part["text"]
        if isinstance(body.get("output_text"), str) and body["output_text"]:
            return body["output_text"]
        for item in body.get("output", []) or []:
            for part in (item.get("content") or []):
                if isinstance(part, dict) and part.get("type") in ("output_text", "text"):
                    if part.get("text"):
                        return part["text"]
    return ""


def propose(prompt, timeout=30):
    """Ask the model for a proposal. Returns a verdict dict, never an action."""
    st = status()
    if not st["llm_connected"]:
        return {"status": "DEFERRED", "reason": st["reason"],
                "text": "", "provider": st["provider"], "model": st["model"]}
    if not isinstance(prompt, str) or not prompt.strip():
        return {"status": "DEFERRED", "reason": "EMPTY_PROMPT",
                "text": "", "provider": st["provider"], "model": st["model"]}
    provider = PROVIDERS[st["provider"]]
    if st["provider"] == "gemini":
        url = provider["url_template"].format(model=st["model"])
        payload = json.dumps(
            {"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
        headers = {"x-goog-api-key": os.environ["AVA_LLM_API_KEY"],
                   "Content-Type": "application/json"}
    else:
        url = provider["url"]
        payload = json.dumps({"model": st["model"], "input": prompt}).encode("utf-8")
        headers = {"Authorization": "Bearer " + os.environ["AVA_LLM_API_KEY"],
                   "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"status": "DEFERRED", "reason": "HTTP_%s" % e.code,
                "text": "", "provider": st["provider"], "model": st["model"]}
    except Exception as e:
        return {"status": "DEFERRED", "reason": "NETWORK_ERROR:%s" % type(e).__name__,
                "text": "", "provider": st["provider"], "model": st["model"]}
    text = _extract_text(body)
    if not text:
        return {"status": "DEFERRED", "reason": "EMPTY_RESPONSE",
                "text": "", "provider": st["provider"], "model": st["model"]}
    if any(m in text for m in TOOL_MARKERS):
        return {"status": "DEFERRED", "reason": "TOOL_MARKER_IN_RESPONSE",
                "text": "", "provider": st["provider"], "model": st["model"]}
    return {"status": "PROPOSED", "reason": "MODEL_PROPOSAL_ONLY",
            "text": text, "provider": st["provider"], "model": st["model"]}


def main(argv):
    if len(argv) < 2 or argv[1] not in ("status", "propose"):
        print("Usage: python llm_connector.py status | propose \"<prompt>\"")
        return 2
    if argv[1] == "status":
        print(json.dumps(status(), indent=2))
        return 0
    result = propose(" ".join(argv[2:]) if len(argv) > 2 else "")
    # Never print the key; propose() output contains no key.
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
