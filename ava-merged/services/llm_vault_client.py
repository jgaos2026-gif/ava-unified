"""AVA Merged — Gemini service client (added 2026-11-04 at John's "Do it").

This is the wiring layer between the brain/orchestrator services and
Gemini. It is deliberately narrow:

- PROPOSE ONLY. The model returns text. Nothing here executes a tool
  call, moves money, changes a policy, or writes to the vault or ledger.
  A response containing a tool-shaped marker is DEFERRED, not executed.
- TWO AUTH MODES, never a key in code, never a key in logs:
  1. Env key (Pavilion mode): AVA_LLM_API_KEY, sent as x-goog-api-key.
  2. Vault surrogate (this machine): if no env key is set, and the
     dynamic_credentials helper is importable, it fetches an hsurr:*
     surrogate for custom.gemini and sends that as x-goog-api-key.
     Muse swaps the surrogate for the real key only on an approved
     request to generativelanguage.googleapis.com.
  If neither mode yields a credential, propose() defers with
  NO_API_KEY and touches no network.
- MODEL: AVA_LLM_MODEL env, or the model passed by the caller. No
  default model is assumed: an empty model defers with NO_MODEL_SET.
  The 2026-11-04 live test used gemini-3.5-flash as a test choice only;
  it is NOT hardcoded here as John's locked model.
- SYNC urllib, redirects refused. Callers in async services should run
  propose() in a thread (asyncio.to_thread) so the event loop is not
  blocked.
"""
import json
import os
import urllib.error
import urllib.request

TOOL_MARKERS = ("tool_call", "function_call", "execute:", "<tool", "tool:")
HOST = "generativelanguage.googleapis.com"
BASE = "https://generativelanguage.googleapis.com/v1beta"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused, verify the endpoint")


def _extract_text(body):
    for cand in body.get("candidates", []) or []:
        for part in (cand.get("content") or {}).get("parts", []) or []:
            if isinstance(part, dict) and part.get("text"):
                return part["text"]
    return ""


def propose(prompt, model=None):
    model = (model or os.environ.get("AVA_LLM_MODEL", "")).strip()
    if not model:
        return {"status": "DEFERRED", "reason": "NO_MODEL_SET",
                "text": "", "model": model}
    if not isinstance(prompt, str) or not prompt.strip():
        return {"status": "DEFERRED", "reason": "EMPTY_PROMPT",
                "text": "", "model": model}
    env_key = os.environ.get("AVA_LLM_API_KEY", "").strip()
    url = "%s/models/%s:generateContent" % (BASE, model)
    payload = json.dumps(
        {"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"}, method="POST")
    if env_key:
        req.add_header("x-goog-api-key", env_key)
    else:
        try:
            import sys
            sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
            from dynamic_credentials import add_surrogate_to_request
            add_surrogate_to_request(req, "custom.gemini", allowed_hosts=[HOST])
        except Exception as e:
            return {"status": "DEFERRED", "reason": "NO_API_KEY",
                    "text": "", "model": model, "detail": type(e).__name__}
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        return {"status": "DEFERRED", "reason": "HTTP_%s" % e.code,
                "text": "", "model": model, "detail": detail}
    except Exception as e:
        return {"status": "DEFERRED", "reason": "NETWORK_ERROR:%s" % type(e).__name__,
                "text": "", "model": model}
    text = _extract_text(body)
    if not text:
        return {"status": "DEFERRED", "reason": "EMPTY_RESPONSE",
                "text": "", "model": model}
    if any(m in text for m in TOOL_MARKERS):
        return {"status": "DEFERRED", "reason": "TOOL_MARKER_IN_RESPONSE",
                "text": "", "model": model}
    return {"status": "PROPOSED", "reason": "MODEL_PROPOSAL_ONLY",
            "text": text, "model": model}
