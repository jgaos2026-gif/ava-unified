import json, os, secrets, time, uuid, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

PORT=8774
OASIS=os.environ.get("OASIS_ROOM_URL", "http://127.0.0.1:8770").rstrip("/")
MAX_BODY_BYTES=1_048_576
ALLOWED_ORIGINS=set(filter(None, os.environ.get(
    "AVA_STITCH_BRIDGE_ALLOWED_ORIGINS",
    "http://127.0.0.1:8770,http://localhost:8770,http://127.0.0.1:8774,http://localhost:8774"
).split(",")))

from urllib.parse import urlparse

if urlparse(OASIS).hostname not in ("127.0.0.1", "localhost", "::1"):
    raise RuntimeError("OASIS_ROOM_URL must target loopback; remote transport is not implemented.")

STATUS_ENDPOINTS=[
 "/api/room/stitchbridge/status",
 "/api/room/spine/status",
 "/api/room/sb688/status",
 "/api/status"
]

VERIFY_ENDPOINTS=[
 "/api/room/stitchbridge/verify",
 "/api/room/spine/verify",
 "/api/room/sb688/verify"
]

EVENT_ENDPOINTS=[
 "/api/room/stitchbridge/event",
 "/api/room/stitchbridge/cross",
 "/api/room/ledger/append"
]

def call(path,method="GET",payload=None,timeout=3):
    data=None
    headers={}
    if payload is not None:
        data=json.dumps(payload).encode("utf-8")
        headers["Content-Type"]="application/json"
    try:
        req=urllib.request.Request(OASIS+path,data=data,headers=headers,method=method)
        with urllib.request.urlopen(req,timeout=timeout) as r:
            raw=r.read().decode("utf-8","replace")
            try: body=json.loads(raw) if raw else {}
            except: body={"raw":raw[:1000]}
            return {"ok":200 <= r.status < 300,"status":r.status,"endpoint":path,"body":body}
    except Exception as e:
        return {"ok":False,"endpoint":path,"error":str(e)}

def first_live(paths,method="GET",payload=None):
    results=[]
    for p in paths:
        r=call(p,method,payload)
        results.append(r)
        if r.get("ok"): return r,results
    return None,results

def origin_allowed(origin):
    return not origin or origin in ALLOWED_ORIGINS


def cors(h):
    origin=h.headers.get("Origin")
    if origin and origin in ALLOWED_ORIGINS:
        h.send_header("Access-Control-Allow-Origin",origin)
        h.send_header("Vary","Origin")
        h.send_header("Access-Control-Allow-Headers","Content-Type")
        h.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")

class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass

    def out(self,obj,status=200):
        b=json.dumps(obj).encode("utf-8")
        self.send_response(status);cors(self)
        self.send_header("Content-Type","application/json")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Length",str(len(b)))
        self.end_headers();self.wfile.write(b)

    def do_OPTIONS(self):
        if not origin_allowed(self.headers.get("Origin")):
            return self.out({"error":"origin not allowed"},403)
        self.send_response(204);cors(self);self.end_headers()

    def do_GET(self):
        from urllib.parse import urlparse
        path=urlparse(self.path).path
        if path == "/health":
            live,attempts=first_live(STATUS_ENDPOINTS)
            body=live.get("body",{}) if live else {}
            ledger=body.get("ledger",{}) if isinstance(body,dict) else {}
            backend_ok=bool(live) and body.get("ok") is True and ledger.get("ok") is True
            return self.out({
                "ok":backend_ok,
                "bridge":"AVA_TO_SOVEREIGN_STITCH",
                "state":"BACKEND_RESPONDING" if backend_ok else "UNRESOLVED",
                "connection":"OFFLINE",
                "certified":False,
                "active_endpoint":live.get("endpoint") if live and backend_ok else None,
                "attempts":attempts,
                "laws":[
                    "NO_BYPASS",
                    "NO_SILENT_TRUST",
                    "NO_SELF_CERT",
                    "NO_ERASED_EVIDENCE",
                    "VERIFY_VALIDATE_CERTIFY"
                ]
            },200 if backend_ok else 503)
        return self.out({"error":"not found"},404)

    def do_POST(self):
        from urllib.parse import urlparse
        if not origin_allowed(self.headers.get("Origin")):
            return self.out({"error":"origin not allowed"},403)
        try:
            n=int(self.headers.get("Content-Length","0"))
            if n < 0 or n > MAX_BODY_BYTES:
                return self.out({"error":"request body exceeds the configured limit"},413)
            obj=json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
            if not isinstance(obj,dict):
                return self.out({"error":"request body must be a JSON object"},400)
        except (ValueError, UnicodeError) as e:
            return self.out({"error":str(e)},400)

        path=urlparse(self.path).path
        envelope={
            "schema":"JGA-AVA-STITCH-ENVELOPE-1",
            "envelope_id":str(uuid.uuid4()),
            "nonce":secrets.token_hex(32),
            "timestamp":time.time(),
            "source":"AVA",
            "room":obj.get("room","ava"),
            "event_type":obj.get("event_type","AVA_EVENT"),
            "payload":obj.get("payload",obj),
            "identity_verification":"NOT_PERFORMED",
            "signature_status":"UNSIGNED_RELAY",
            "governance":{
                "no_bypass":True,
                "no_silent_trust":True,
                "no_self_certification":True,
                "preserve_failed_evidence":True,
                "attestation":"UNSIGNED_CLAIMS"
            }
        }

        if path == "/event":
            live,attempts=first_live(EVENT_ENDPOINTS,"POST",envelope)
            body=live.get("body",{}) if live else {}
            appended=bool(
                live and isinstance(body,dict)
                and body.get("ok") is True
                and body.get("certified") is False
                and body.get("state") == "APPENDED_UNCERTIFIED"
                and isinstance(body.get("entry_hash"),str)
                and len(body.get("entry_hash")) == 64
            )
            return self.out({
                "ok":appended,
                "state":"APPENDED_UNCERTIFIED" if appended else "LOCAL_BRIDGE_ONLY",
                "certified":False,
                "identity_verified":False,
                "signature_verified":False,
                "appended_by":live.get("endpoint") if live and appended else None,
                "evidence_hash":body.get("entry_hash") if appended else None,
                "attempts":attempts,
                "envelope":envelope
            },200 if appended else 202)

        if path == "/verify":
            live,attempts=first_live(VERIFY_ENDPOINTS,"POST",envelope)
            body=live.get("body",{}) if live else {}
            ledger_ok=bool(
                live and isinstance(body,dict)
                and body.get("ok") is True
                and body.get("ledger_integrity_verified") is True
            )
            return self.out({
                "ok":ledger_ok,
                "verified":False,
                "ledger_integrity_verified":ledger_ok,
                "envelope_verified":False,
                "certified":False,
                "state":"LEDGER_INTEGRITY_VERIFIED" if ledger_ok else "UNRESOLVED",
                "verified_by":live.get("endpoint") if live and ledger_ok else None,
                "attempts":attempts
            },200 if ledger_ok else 503)

        return self.out({"error":"not found"},404)

if __name__=="__main__":
    ThreadingHTTPServer(("127.0.0.1",PORT),H).serve_forever()
