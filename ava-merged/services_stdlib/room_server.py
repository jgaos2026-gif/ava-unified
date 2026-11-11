"""OASIS room server — the missing 127.0.0.1:8770 service that
stitch_bridge (8774) probes.

Stage: WARM (file-backed hash-chained ledger under vault_data/,
the package's WARM disk store). HOT is in-memory request handling
only; nothing HOT is trusted across a restart. WARM -> COLD only
through a sealed archive (not built yet); COLD -> WARM only through
verified restore (Phoenix recovery re-verifies the chain prefix,
never self-certifies).

Endpoints (exactly the ones stitch_bridge probes, plus /health and
a chain verify):
  GET  /health
  GET  /api/status
  GET  /api/room/stitchbridge/status
  GET  /api/room/spine/status
  GET  /api/room/sb688/status
  POST /api/room/stitchbridge/verify
  POST /api/room/stitchbridge/event
  POST /api/room/stitchbridge/cross
  POST /api/room/ledger/append
  GET  /api/room/ledger/verify

Six-layer BCT gate on EVERY append (identity, schema, crypto, braid,
transaction, audit). Malformed envelopes are rejected with the failed
layer named and quarantined to room_quarantine.jsonl — never silently
accepted. /verify reports chain integrity only; certified is always
False (no self-certification; hashes are not truth).
"""
import hashlib
import json
import math
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

PORT = 8770

ROOT = os.path.dirname(os.path.abspath(__file__))
PACKAGE = os.path.dirname(ROOT)
DEFAULT_DIR = os.path.join(PACKAGE, "vault_data")

ENVELOPE_SCHEMA = "JGA-AVA-STITCH-ENVELOPE-1"
MAX_REQUEST_BYTES = 1_048_576
ALLOWED_ORIGINS = set(filter(None, os.environ.get(
    "OASIS_ALLOWED_ORIGINS",
    "http://127.0.0.1:8774,http://localhost:8774"
).split(",")))

LOCK = threading.RLock()


def _sha(obj):
    if not isinstance(obj, (str, bytes)):
        obj = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    if isinstance(obj, str):
        obj = obj.encode("utf-8")
    return hashlib.sha256(obj).hexdigest()


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


class RoomLedger:
    """WARM hash-chained ledger for room events."""

    def __init__(self, directory=None):
        self.directory = directory or os.environ.get(
            "AVA_ROOM_LEDGER_DIR", DEFAULT_DIR)
        os.makedirs(self.directory, exist_ok=True)
        self.path = os.path.join(self.directory, "room_ledger.jsonl")
        self.quarantine_path = os.path.join(
            self.directory, "room_quarantine.jsonl")
        self.lock = threading.RLock()
        self.chain = self.verify_chain()

    def _read_entries(self):
        entries = []
        if not os.path.exists(self.path):
            return entries
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    entries.append(json.loads(line))
        return entries

    def verify_chain(self):
        if not os.path.exists(self.path):
            return {"ok": True, "entries": 0, "state": "GENESIS",
                    "certified": False}
        previous = "GENESIS"
        count = 0
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    x = json.loads(line)
                    if x.get("previous_hash") != previous:
                        return {"ok": False, "entries": count,
                                "state": "CHAIN_BREAK",
                                "expected": previous,
                                "received": x.get("previous_hash"),
                                "certified": False}
                    claimed = x.get("entry_hash")
                    y = dict(x)
                    y.pop("entry_hash", None)
                    if _sha(_canonical(y)) != claimed:
                        return {"ok": False, "entries": count,
                                "state": "HASH_FAILURE",
                                "certified": False}
                    previous = claimed
                    count += 1
            return {"ok": True, "entries": count,
                    "state": "INTEGRITY_VERIFIED", "certified": False}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "entries": count, "state": "UNRESOLVED",
                    "error": str(e), "certified": False}

    def last_hash(self):
        entries = self._read_entries()
        if not entries:
            return "GENESIS"
        return entries[-1].get("entry_hash", "GENESIS")

    def gate(self, envelope):
        """Six-layer gate. Returns (certified, failed_layer|None)."""
        # 1. identity — source and room named.
        if not isinstance(envelope.get("source"), str) or not envelope["source"].strip():
            return False, "identity"
        if not isinstance(envelope.get("room"), str) or not envelope["room"].strip():
            return False, "identity"
        # 2. schema — envelope shape, types, bounds, freshness and replay identity.
        if envelope.get("schema") != ENVELOPE_SCHEMA:
            return False, "schema"
        timestamp = envelope.get("timestamp")
        if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp):
            return False, "schema"
        if abs(time.time() - timestamp) > 300:
            return False, "freshness"
        if not isinstance(envelope.get("event_type"), str) or not envelope["event_type"].strip():
            return False, "schema"
        if "payload" not in envelope:
            return False, "schema"
        if not isinstance(envelope.get("envelope_id"), str) or not envelope["envelope_id"].strip():
            return False, "transaction"
        nonce = envelope.get("nonce")
        if not isinstance(nonce, str) or len(nonce) != 64:
            return False, "transaction"
        try:
            int(nonce, 16)
        except ValueError:
            return False, "transaction"
        gov = envelope.get("governance")
        if not isinstance(gov, dict):
            return False, "schema"
        for flag in ("no_bypass", "no_silent_trust",
                     "no_self_certification", "preserve_failed_evidence"):
            if gov.get(flag) is not True:
                return False, "schema"
        # 3. crypto — chain intact at mount.
        if not self.chain.get("ok"):
            return False, "crypto"
        # 4. braid — payload linked to an event_type + room (linkage,
        # not a vector similarity claim).
        if not envelope.get("event_type") or not envelope.get("room"):
            return False, "braid"
        # 5. transaction — envelope id unique when supplied.
        env_id = envelope["envelope_id"]
        nonce = envelope["nonce"]
        for existing in self._read_entries():
            prior = existing.get("envelope", {})
            if prior.get("envelope_id") == env_id or prior.get("nonce") == nonce:
                return False, "transaction"
        # 6. audit — pre-write shape only; durable append checked
        # by append() itself.
        return True, None

    def append(self, envelope, endpoint):
        """Gate, then append. Returns a result dict; failures are
        quarantined with the failed layer named, never silently
        accepted."""
        with self.lock:
            # Re-read disk under the append lock. A cached startup result is not
            # sufficient if the ledger was modified or corrupted after mount.
            self.chain = self.verify_chain()
            if not self.chain.get("ok"):
                self._quarantine(envelope, "crypto", endpoint)
                return {"ok": False, "certified": False,
                        "state": "QUARANTINED", "failed_layer": "crypto",
                        "endpoint": endpoint}
            certified, failed_layer = self.gate(envelope)
            if not certified:
                self._quarantine(envelope, failed_layer, endpoint)
                return {"ok": False, "certified": False,
                        "state": "QUARANTINED",
                        "failed_layer": failed_layer,
                        "endpoint": endpoint}
            entry = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "endpoint": endpoint,
                "envelope": envelope,
                "trust_state": "OBSERVED",
                "identity_verified": False,
                "signature_verified": False,
                "self_certified": False,
                "previous_hash": self.last_hash(),
                "stage": "WARM",
            }
            try:
                entry["entry_hash"] = _sha(_canonical(entry))
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            except Exception as e:  # noqa: BLE001
                self._quarantine(envelope, "audit", endpoint)
                return {"ok": False, "certified": False,
                        "state": "QUARANTINED", "failed_layer": "audit",
                        "endpoint": endpoint, "error": str(e)}
            self.chain = self.verify_chain()
            if not self.chain.get("ok"):
                # The write happened, so preserve it for forensic review, but
                # never report a failed post-write integrity check as success.
                self._quarantine(envelope, "audit", endpoint)
                return {"ok": False, "certified": False,
                        "state": "UNRESOLVED", "failed_layer": "audit",
                        "endpoint": endpoint, "verification": self.chain}
            return {"ok": True, "certified": False,
                    "state": "APPENDED_UNCERTIFIED",
                    "entry_hash": entry["entry_hash"],
                    "endpoint": endpoint}

    def _quarantine(self, envelope, failed_layer, endpoint):
        record = {"envelope": envelope, "quarantined": True,
                  "failed_layer": failed_layer, "endpoint": endpoint,
                  "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}
        try:
            with open(self.quarantine_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass


LEDGER = RoomLedger()


def origin_allowed(origin):
    return not origin or origin in ALLOWED_ORIGINS


def cors(h):
    origin = h.headers.get("Origin")
    if origin and origin in ALLOWED_ORIGINS:
        h.send_header("Access-Control-Allow-Origin", origin)
        h.send_header("Vary", "Origin")
        h.send_header("Access-Control-Allow-Headers", "Content-Type")
        h.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")


def status_body(room):
    chain = LEDGER.verify_chain()
    return {
        "ok": bool(chain.get("ok")),
        "room": room,
        "state": "LOCAL_SERVICE_READY" if chain.get("ok") else "UNRESOLVED",
        "connected": False,
        "certified": False,
        "service": "OASIS_ROOM_SERVER",
        "ledger": chain,
    }


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def out(self, obj, status=200):
        b = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        cors(self)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def body(self):
        n = int(self.headers.get("Content-Length", "0"))
        if n < 0 or n > MAX_REQUEST_BYTES:
            raise ValueError("request body exceeds the configured limit")
        value = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value

    def do_OPTIONS(self):
        if not origin_allowed(self.headers.get("Origin")):
            return self.out({"error": "origin not allowed"}, 403)
        self.send_response(204)
        cors(self)
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            chain = LEDGER.verify_chain()
            return self.out({"ok": chain.get("ok", False),
                             "service": "OASIS_ROOM_SERVER",
                             "port": PORT, "ledger": chain,
                             "certified": False},
                            200 if chain.get("ok") else 503)
        if path == "/api/status":
            return self.out(status_body("oasis"))
        if path == "/api/room/stitchbridge/status":
            return self.out(status_body("stitchbridge"))
        if path == "/api/room/spine/status":
            return self.out(status_body("spine"))
        if path == "/api/room/sb688/status":
            return self.out(status_body("sb688"))
        if path == "/api/room/ledger/verify":
            verification = LEDGER.verify_chain()
            valid = bool(verification.get("ok"))
            return self.out({"ok": valid, "ledger_integrity_verified": valid,
                             "envelope_verified": False, "certified": False,
                             "verification": verification}, 200 if valid else 503)
        return self.out({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if not origin_allowed(self.headers.get("Origin")):
            return self.out({"error": "origin not allowed"}, 403)
        try:
            obj = self.body()
        except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
            status = 413 if "limit" in str(exc) else 400
            return self.out({"error": str(exc)}, status)
        if path == "/api/room/stitchbridge/verify":
            envelope = obj if isinstance(obj, dict) and obj.get("schema") else {
                "schema": ENVELOPE_SCHEMA,
                "timestamp": time.time(),
                "source": obj.get("source", "AVA") if isinstance(obj, dict) else "AVA",
                "room": "stitchbridge",
                "event_type": "VERIFY_REQUEST",
                "payload": obj,
                "governance": {"no_bypass": True, "no_silent_trust": True,
                               "no_self_certification": True,
                               "preserve_failed_evidence": True},
            }
            chain = LEDGER.verify_chain()
            valid = bool(chain.get("ok"))
            return self.out({
                "ok": valid,
                "ledger_integrity_verified": valid,
                "envelope_verified": False,
                "certified": False,
                "state": "LEDGER_INTEGRITY_VERIFIED" if valid else "UNRESOLVED",
                "verification": chain,
                "envelope_schema": envelope.get("schema"),
            }, 200 if valid else 503)
        if path in ("/api/room/stitchbridge/event",
                    "/api/room/stitchbridge/cross",
                    "/api/room/ledger/append"):
            if not isinstance(obj, dict) or obj.get("schema") != ENVELOPE_SCHEMA:
                LEDGER._quarantine(obj if isinstance(obj, dict) else {},
                                   "schema", path)
                return self.out({"ok": False, "certified": False,
                                 "state": "QUARANTINED",
                                 "failed_layer": "schema",
                                 "error": "envelope schema must be %s"
                                 % ENVELOPE_SCHEMA}, 422)
            result = LEDGER.append(obj, path)
            status = 200 if result.get("ok") else 422
            return self.out(result, status)
        return self.out({"error": "not found"}, 404)


def create_server(port=PORT, ledger_dir=None):
    """Factory for tests: a server on any port with its own ledger dir."""
    global LEDGER
    LEDGER = RoomLedger(ledger_dir)
    return ThreadingHTTPServer(("127.0.0.1", port), H)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
