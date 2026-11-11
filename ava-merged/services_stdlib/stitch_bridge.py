import json,time,urllib.request,urllib.error
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

PORT=8774
OASIS="http://127.0.0.1:8770"

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

def cors(h):
    h.send_header("Access-Control-Allow-Origin","*")
    h.send_header("Access-Control-Allow-Headers","Content-Type")
    h.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")

class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass

    def out(self,obj,status=200):
        b=json.dumps(obj).encode("utf-8")
        self.send_response(status);cors(self)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(b)))
        self.end_headers();self.wfile.write(b)

    def do_OPTIONS(self):
        self.send_response(204);cors(self);self.end_headers()

    def do_GET(self):
        if self.path.startswith("/health"):
            live,attempts=first_live(STATUS_ENDPOINTS)
            return self.out({
                "ok":bool(live),
                "bridge":"AVA_TO_SOVEREIGN_STITCH",
                "state":"CONNECTED" if live else "UNRESOLVED",
                "active_endpoint":live.get("endpoint") if live else None,
                "attempts":attempts,
                "laws":[
                    "NO_BYPASS",
                    "NO_SILENT_TRUST",
                    "NO_SELF_CERT",
                    "NO_ERASED_EVIDENCE",
                    "VERIFY_VALIDATE_CERTIFY"
                ]
            },200 if live else 503)
        return self.out({"error":"not found"},404)

    def do_POST(self):
        try:
            n=int(self.headers.get("Content-Length","0"))
            obj=json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except Exception as e:
            return self.out({"error":str(e)},400)

        envelope={
            "schema":"JGA-AVA-STITCH-ENVELOPE-1",
            "timestamp":time.time(),
            "source":"AVA",
            "room":obj.get("room","ava"),
            "event_type":obj.get("event_type","AVA_EVENT"),
            "payload":obj.get("payload",obj),
            "governance":{
                "no_bypass":True,
                "no_silent_trust":True,
                "no_self_certification":True,
                "preserve_failed_evidence":True
            }
        }

        if self.path.startswith("/event"):
            live,attempts=first_live(EVENT_ENDPOINTS,"POST",envelope)
            return self.out({
                "ok":bool(live),
                "state":"STITCH_ACCEPTED" if live else "LOCAL_BRIDGE_ONLY",
                "accepted_by":live.get("endpoint") if live else None,
                "attempts":attempts,
                "envelope":envelope
            },200 if live else 202)

        if self.path.startswith("/verify"):
            live,attempts=first_live(VERIFY_ENDPOINTS,"POST",envelope)
            return self.out({
                "ok":bool(live),
                "verified":bool(live),
                "certified":False,
                "state":"VERIFIED_BY_BACKEND" if live else "UNRESOLVED",
                "verified_by":live.get("endpoint") if live else None,
                "attempts":attempts
            },200 if live else 503)

        return self.out({"error":"not found"},404)

if __name__=="__main__":
    ThreadingHTTPServer(("127.0.0.1",PORT),H).serve_forever()
