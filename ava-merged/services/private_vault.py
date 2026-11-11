"""AVA Private Vault — CORRECTED version.

Fixes vs the pasted version:
1. NO hardcoded PIN hash anywhere, and NO default hash if the
   environment variable is missing. If AVA_VAULT_PIN_HASH is unset,
   the vault answers 503 LOCKED. Set it (to a NEW hash, after rotation)
   in the environment only — never in a Dockerfile, never in chat.
2. PERSISTENT encryption key. The pasted version generated a fresh
   AESGCM key on every start, so stored secrets were undecryptable
   after a restart. Here the key is derived from the PIN with
   PBKDF2-HMAC-SHA256 (200,000 iterations) plus a salt stored in the
   sqlite meta table. Same PIN + same salt = same key across restarts.
   A wrong PIN derives a different key and decryption fails closed.
   The PIN itself is never stored; only its SHA-256 hash (from the
   environment) is compared, and only the salt is stored.
3. Storage path comes from VAULT_DATA_DIR (default ./vault_data).
   In Docker, compose mounts the volume there and sets the variable;
   the path is not hardcoded to /app/vault_data in code.

Endpoints: GET /health, POST /store, GET /retrieve/{key}.
Auth: header X-AVA-VAULT-PIN, checked against AVA_VAULT_PIN_HASH.
"""
import base64
import hashlib
import os
import sqlite3

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from fastapi import FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

app = FastAPI(title="AVA Private Vault (corrected)", version="2.1.0")
api_key_header = APIKeyHeader(name="X-AVA-VAULT-PIN", auto_error=True)

DATA_DIR = os.environ.get("VAULT_DATA_DIR", "vault_data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "vault.db")


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS secure_store "
        "(key TEXT PRIMARY KEY, nonce TEXT, ciphertext TEXT)"
    )
    conn.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
    conn.commit()
    return conn


def _salt() -> bytes:
    conn = _db()
    row = conn.execute("SELECT v FROM meta WHERE k='salt'").fetchone()
    if row:
        conn.close()
        return base64.b64decode(row[0])
    salt = os.urandom(16)
    conn.execute("INSERT INTO meta (k, v) VALUES ('salt', ?)",
                 (base64.b64encode(salt).decode(),))
    conn.commit()
    conn.close()
    return salt


def _key_for_pin(pin: str) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                     salt=_salt(), iterations=200_000)
    return kdf.derive(pin.encode())


def check_pin(provided_pin: str = Security(api_key_header)) -> str:
    """Return the PIN on success; raise locked/refused otherwise."""
    env_hash = os.environ.get("AVA_VAULT_PIN_HASH")
    if not env_hash:
        raise HTTPException(status_code=503,
                            detail="Vault locked: AVA_VAULT_PIN_HASH is not set.")
    if hashlib.sha256(provided_pin.encode()).hexdigest() != env_hash:
        raise HTTPException(status_code=401, detail="Access refused.")
    return provided_pin


class VaultData(BaseModel):
    key: str
    secret_payload: str


@app.get("/health")
async def health():
    return {"ok": True, "service": "AVA_PRIVATE_VAULT",
            "state": "LOCKED_BY_DEFAULT" if not os.environ.get("AVA_VAULT_PIN_HASH")
                     else "PIN_GATED",
            "storage": "SQLITE_PIN_DERIVED_KEY"}


@app.post("/store")
async def store(payload: VaultData, pin: str = Security(check_pin)):
    cipher = AESGCM(_key_for_pin(pin))
    nonce = os.urandom(12)
    ct = cipher.encrypt(nonce, payload.secret_payload.encode(), None)
    conn = _db()
    conn.execute(
        "INSERT OR REPLACE INTO secure_store (key, nonce, ciphertext) VALUES (?,?,?)",
        (payload.key, base64.b64encode(nonce).decode(),
         base64.b64encode(ct).decode()))
    conn.commit()
    conn.close()
    return {"status": "PAYLOAD_ENCRYPTED_AND_VAULTED", "key_identifier": payload.key}


@app.get("/retrieve/{key}")
async def retrieve(key: str, pin: str = Security(check_pin)):
    conn = _db()
    row = conn.execute("SELECT nonce, ciphertext FROM secure_store WHERE key=?",
                       (key,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Key not found.")
    try:
        plain = AESGCM(_key_for_pin(pin)).decrypt(
            base64.b64decode(row[0]), base64.b64decode(row[1]), None)
    except Exception:
        raise HTTPException(status_code=401, detail="Decryption failed.")
    return {"key": key, "secret_payload": plain.decode()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8776)
