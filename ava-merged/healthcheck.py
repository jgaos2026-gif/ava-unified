"""Measured health checks for the dashboard.

Fix vs the pasted dashboard: the pasted version hardcoded
ACTIVE / ONLINE / STABLE as static labels. This module actually
queries each service's /health endpoint and returns what it measured
— a service that does not answer is reported OFFLINE, not ACTIVE.
The Streamlit dashboard imports this; the function is also testable
without Streamlit installed.
"""
import httpx

SERVICES = [
    ("Room Server", "http://127.0.0.1:8770/health"),
    ("Voice Bridge", "http://127.0.0.1:8772/health"),
    ("Brain Bridge", "http://127.0.0.1:8773/health"),
    ("Stitch Bridge", "http://127.0.0.1:8774/health"),
    ("Orchestrator", "http://127.0.0.1:8775/health"),
    ("Private Vault", "http://127.0.0.1:8776/health"),
    ("Organism Core", "http://127.0.0.1:8780/health"),
    ("Embedding Braid", "http://127.0.0.1:8781/health"),
    ("Tool Sandbox", "http://127.0.0.1:8782/health"),
    ("Stitch Link", "http://127.0.0.1:8783/health"),
]


def check_all(timeout: float = 2.0):
    results = []
    for name, url in SERVICES:
        try:
            r = httpx.get(url, timeout=timeout, trust_env=False)
            body = r.json() if r.status_code == 200 else {}
            results.append({"service": name, "status": "ONLINE"
                            if body.get("ok") else "DEGRADED",
                            "detail": body})
        except Exception as e:
            results.append({"service": name, "status": "OFFLINE",
                            "detail": str(e)})
    return results
