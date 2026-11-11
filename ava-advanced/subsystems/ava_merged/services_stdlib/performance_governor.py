import json,time,statistics,urllib.request
from pathlib import Path
from datetime import datetime

CORE="http://127.0.0.1:8780"
OUT=Path(r"C:\IRONLINK3\OASIS_BRAID_ROOM_V2\AVA_RUNTIME\AVA_ORGANISM\EVIDENCE")

TESTS=[
 {
  "name":"FAST_GENERAL",
  "mode":"GENERAL",
  "message":"In one sentence explain why a backup should exist before changing an important file."
 },
 {
  "name":"MEMORY_RECALL",
  "mode":"MEMORY",
  "message":"What is AVA's trust rule for an unchecked claim? Answer briefly."
 },
 {
  "name":"POWERSHELL_REASONING",
  "mode":"POWERSHELL",
  "message":"I need to check whether local port 8780 is listening. Tell me the safest PowerShell command."
 },
 {
  "name":"STITCH_TIGHT",
  "mode":"STITCH",
  "message":"An important state has conflicting evidence. Should AVA silently certify it or preserve the contradiction? Answer briefly."
 },
 {
  "name":"SB688_TIGHT",
  "mode":"SECURITY",
  "message":"A corrupted input reaches AVA before trusted memory. What should SB688 do first? Answer briefly."
 }
]

def call(path,payload=None,timeout=300):
    if payload is None:
        req=urllib.request.Request(CORE+path,method="GET")
    else:
        req=urllib.request.Request(
            CORE+path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type":"application/json"},
            method="POST"
        )
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def run_test(t):
    started=time.perf_counter()
    try:
        j=call("/chat",{
            "message":t["message"],
            "task_mode":t["mode"]
        },300)
        elapsed=(time.perf_counter()-started)*1000.0
        return {
            "ok":bool(j.get("ok")),
            "name":t["name"],
            "mode":t["mode"],
            "latency_ms":round(elapsed,2),
            "model":j.get("model"),
            "trust_state":j.get("trust_state"),
            "verified_integrity":j.get("verified_integrity"),
            "certified":j.get("certified"),
            "reply":j.get("reply"),
            "tool_trace":j.get("tool_trace",[]),
            "raw":j
        }
    except Exception as e:
        return {
            "ok":False,
            "name":t["name"],
            "mode":t["mode"],
            "latency_ms":round((time.perf_counter()-started)*1000.0,2),
            "error":str(e)
        }

health={}
try:
    health=call("/health",None,20)
except Exception as e:
    health={"ok":False,"error":str(e)}

results=[]

for t in TESTS:
    print()
    print("TEST:",t["name"])
    x=run_test(t)
    results.append(x)
    print("STATE :", "PASS" if x.get("ok") else "FAIL")
    print("MODE  :",x.get("mode"))
    print("MODEL :",x.get("model","UNRESOLVED"))
    print("MS    :",x.get("latency_ms"))
    if x.get("trust_state"):
        print("TRUST :",x.get("trust_state"))
    if x.get("reply"):
        print("AVA   :",x.get("reply")[:300])

good=[x["latency_ms"] for x in results if x.get("ok")]

summary={
 "schema":"JGA-AVA-PERFORMANCE-GOVERNOR-PROOF-1",
 "generated_at":datetime.now().astimezone().isoformat(),
 "architecture":{
   "primary_reasoning":"llama3.2:1b-instruct-q4_K_M",
   "tight_assurance_challenger":"llama3.2:1b-instruct-q8_0",
   "embedding":"all-minilm",
   "vector_memory":"INT8_Q8",
   "tool_execution":"AVA_LOCAL_TOOL_SANDBOX",
   "trust":"SB688 + SOVEREIGN_STITCH"
 },
 "policy":{
   "FAST_PATH":"Q4 PRIMARY",
   "BALANCED_PATH":"Q4 + LOCAL MEMORY",
   "TIGHT_ASSURANCE":"Q4 PRIMARY + Q8 INDEPENDENT CHALLENGER",
   "FAILURE":"Q8 FALLBACK",
   "cloud_api_required":False
 },
 "health":health,
 "tests":results,
 "performance":{
   "successful_tests":len(good),
   "total_tests":len(results),
   "median_end_to_end_ms":round(statistics.median(good),2) if good else None,
   "fastest_ms":round(min(good),2) if good else None,
   "slowest_ms":round(max(good),2) if good else None
 },
 "claim_boundary":{
   "scope":"THIS LOCAL MACHINE AND CURRENT AVA RUNTIME",
   "universal_certification":False
 }
}

path=OUT/"AVA_PERFORMANCE_GOVERNOR_LATEST.json"
path.write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf-8")

print()
print("="*70)
print("AVA PERFORMANCE GOVERNOR")
print("="*70)
print("SUCCESS :",len(good),"/",len(results))

if good:
    print("MEDIAN  :",round(statistics.median(good),2),"ms")
    print("FASTEST :",round(min(good),2),"ms")
    print("SLOWEST :",round(max(good),2),"ms")

print("PRIMARY : Q4")
print("TIGHT   : Q4 + Q8 CHALLENGER")
print("MEMORY  : all-minilm + Q8 VECTOR STORE")
print("TOOLS   : LOCAL SANDBOX")
print("TRUST   : SB688 + SOVEREIGN STITCH")
print("PROOF   :",path)
print("="*70)
