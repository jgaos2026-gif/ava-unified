"""AVA Embedding Braid — CORRECTED version.

Fix vs the pasted version: the pasted "Q8" embedding was a seeded
random vector — two similar sentences got unrelated vectors, and it
was not all-minilm and not INT8 quantization. This version is honest
about what it is: a deterministic TOKEN-HASH embedding (256 dims,
L2-normalized, cosine similarity). Similar texts share tokens, so they
score higher than unrelated texts. It is NOT a neural embedding, NOT
Q8, and NOT all-minilm. A real neural model (e.g. sentence-transformers
all-minilm) is a future swap behind the same /upsert and /search
endpoints — swap embed_text(), not the API.

Endpoints: GET /health, POST /upsert, POST /search.
Storage is in-memory only in this version; a persistent store is a
future step, not claimed here.
"""
import hashlib
import math
import re
from typing import Any, Dict, List

import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="AVA Embedding Braid (corrected)", version="2.1.0")
DIM = 256
REGISTRY: List[Dict[str, Any]] = []


def embed_text(text: str) -> np.ndarray:
    """Deterministic token-hash embedding. Honest label: HASH, not Q8."""
    v = np.zeros(DIM, dtype=float)
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        idx = int(hashlib.sha256(token.encode()).hexdigest(), 16) % DIM
        v[idx] += 1.0
    norm = float(np.linalg.norm(v))
    return v / norm if norm else v


class EmbeddingVector(BaseModel):
    text: str
    metadata: Dict[str, Any] = {}


class QueryVector(BaseModel):
    query_text: str
    top_k: int = 3


@app.get("/health")
async def health():
    return {"ok": True, "service": "AVA_EMBEDDING_BRAID",
            "embedding": "TOKEN_HASH_256", "registry_depth": len(REGISTRY)}


@app.post("/upsert")
async def upsert(payload: EmbeddingVector):
    REGISTRY.append({"text": payload.text, "vector": embed_text(payload.text),
                     "metadata": payload.metadata})
    return {"status": "SUCCESS_UPSERT", "registry_depth": len(REGISTRY)}


@app.post("/search")
async def search(payload: QueryVector):
    if not REGISTRY:
        return {"matches": [], "layer": "COLD_REGISTER_EMPTY"}
    q = embed_text(payload.query_text)
    results = [{"text": n["text"], "score": float(np.dot(n["vector"], q)),
                "metadata": n["metadata"]} for n in REGISTRY]
    results.sort(key=lambda r: r["score"], reverse=True)
    return {"matches": results[: payload.top_k], "layer": "HASH_BRAID_CACHE"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8781)
