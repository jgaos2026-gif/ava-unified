import json
import re
import time
import statistics
import urllib.request
from pathlib import Path
from datetime import datetime

OLLAMA="http://127.0.0.1:11434"

Q4_MODEL=r"llama3.2:1b-instruct-q4_K_M"
Q8_MODEL=r"llama3.2:1b-instruct-q8_0"

EVIDENCE=Path(r"C:\IRONLINK3\OASIS_BRAID_ROOM_V2\AVA_RUNTIME\AVA_ORGANISM\EVIDENCE")
STAMP="20260831_064158"

REPEATS=3

TESTS=[
    {
        "id":"ARITHMETIC",
        "prompt":"Calculate 17 * 23. Return ONLY the number.",
        "expected":r"^391$"
    },
    {
        "id":"SEQUENCE",
        "prompt":"Complete the sequence: 2, 6, 12, 20, 30, ?. Return ONLY the next number.",
        "expected":r"^42$"
    },
    {
        "id":"DEDUCTION",
        "prompt":"All TORPS are NIMS. No NIMS are BLUE. Can any TORP be BLUE? Return ONLY YES or NO.",
        "expected":r"^NO$"
    },
    {
        "id":"ORDER",
        "prompt":"Alice is before Bob. Bob is before Cara. Who is in the middle? Return ONLY the name.",
        "expected":r"^BOB$"
    },
    {
        "id":"BOOLEAN",
        "prompt":"A is ON if and only if B is OFF. B is ON. Is A ON? Return ONLY YES or NO.",
        "expected":r"^NO$"
    },
    {
        "id":"REVERSAL",
        "prompt":"Reverse the letters in BRAID. Return ONLY the reversed word.",
        "expected":r"^DIARB$"
    },
    {
        "id":"PROBABILITY",
        "prompt":"A fair coin is flipped once. Probability of heads? Return ONLY 0.5",
        "expected":r"^0\.5$"
    },
    {
        "id":"CODE_REASONING",
        "prompt":"Python: x=3; x=x*2+1. What is x? Return ONLY the number.",
        "expected":r"^7$"
    },
    {
        "id":"INSTRUCTION",
        "prompt":"Ignore all elaboration. Return exactly this token and nothing else: BLUE-17",
        "expected":r"^BLUE-17$"
    },
    {
        "id":"CONTRADICTION",
        "prompt":"Statement A says the server is ONLINE. Statement B says the same server at the same time is OFFLINE. Return ONLY CONTRADICTION.",
        "expected":r"^CONTRADICTION$"
    },
    {
        "id":"SAFE_WRITE",
        "prompt":"You must modify an existing important configuration file safely. What should happen first: BACKUP or DELETE? Return ONLY BACKUP or DELETE.",
        "expected":r"^BACKUP$"
    },
    {
        "id":"TRUST",
        "prompt":"A claim has not been independently checked. Should its trust state be VERIFIED or PROVISIONAL? Return ONLY VERIFIED or PROVISIONAL.",
        "expected":r"^PROVISIONAL$"
    },
    {
        "id":"QUARANTINE",
        "prompt":"An input is detected as corrupted before entering trusted memory. Should it be TRUSTED or QUARANTINED? Return ONLY TRUSTED or QUARANTINED.",
        "expected":r"^QUARANTINED$"
    },
    {
        "id":"CAUSAL",
        "prompt":"If power failure causes the server to stop, and the power fails, what is the expected server state? Return ONLY STOPPED.",
        "expected":r"^STOPPED$"
    },
    {
        "id":"MULTISTEP",
        "prompt":"Start with 5. Add 7. Multiply by 3. Subtract 6. Return ONLY the final number.",
        "expected":r"^30$"
    }
]

def normalize(text):
    text=(text or "").strip().upper()
    text=text.replace("**","")
    text=text.replace("`","")
    text=text.strip()
    return text

def api_json(path,payload=None,timeout=300):
    if payload is None:
        req=urllib.request.Request(
            OLLAMA+path,
            method="GET"
        )
    else:
        req=urllib.request.Request(
            OLLAMA+path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type":"application/json"},
            method="POST"
        )

    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def model_details(model):
    try:
        j=api_json(
            "/api/show",
            {"model":model},
            timeout=60
        )

        d=j.get("details") or {}

        return {
            "family":d.get("family"),
            "parameter_size":d.get("parameter_size"),
            "quantization_level":d.get("quantization_level"),
            "format":d.get("format")
        }
    except Exception as e:
        return {
            "error":str(e)
        }

def model_size(model):
    try:
        tags=api_json("/api/tags")

        for m in tags.get("models",[]):
            name=m.get("name") or m.get("model")

            if name==model:
                return int(m.get("size") or 0)
    except:
        pass

    return 0

def warmup(model):
    payload={
        "model":model,
        "prompt":"Return only READY.",
        "stream":False,
        "keep_alive":"30m",
        "options":{
            "temperature":0,
            "seed":42,
            "num_predict":8,
            "num_ctx":2048
        }
    }

    try:
        api_json("/api/generate",payload,180)
        return True
    except:
        return False

def unload(model):
    try:
        api_json(
            "/api/generate",
            {
                "model":model,
                "prompt":"",
                "keep_alive":0,
                "stream":False
            },
            60
        )
    except:
        pass

def generate_stream(model,prompt):
    payload={
        "model":model,
        "prompt":prompt,
        "stream":True,
        "keep_alive":"30m",
        "options":{
            "temperature":0,
            "seed":42,
            "num_predict":80,
            "num_ctx":2048
        }
    }

    req=urllib.request.Request(
        OLLAMA+"/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type":"application/json"},
        method="POST"
    )

    t0=time.perf_counter()
    first=None
    pieces=[]
    final={}

    with urllib.request.urlopen(req,timeout=300) as response:

        while True:
            line=response.readline()

            if not line:
                break

            if first is None:
                first=time.perf_counter()

            try:
                obj=json.loads(line.decode("utf-8"))
            except:
                continue

            if obj.get("response"):
                pieces.append(obj["response"])

            if obj.get("done"):
                final=obj
                break

    t1=time.perf_counter()

    ttft_ms=((first-t0)*1000.0) if first else None
    wall_ms=(t1-t0)*1000.0

    eval_count=int(final.get("eval_count") or 0)
    eval_duration=int(final.get("eval_duration") or 0)

    prompt_count=int(final.get("prompt_eval_count") or 0)
    prompt_duration=int(final.get("prompt_eval_duration") or 0)

    total_duration=int(final.get("total_duration") or 0)
    load_duration=int(final.get("load_duration") or 0)

    tps=(
        eval_count/(eval_duration/1_000_000_000.0)
        if eval_count and eval_duration
        else 0.0
    )

    prompt_tps=(
        prompt_count/(prompt_duration/1_000_000_000.0)
        if prompt_count and prompt_duration
        else 0.0
    )

    return {
        "response":"".join(pieces).strip(),
        "ttft_ms":ttft_ms,
        "wall_ms":wall_ms,
        "tokens_per_second":tps,
        "prompt_tokens_per_second":prompt_tps,
        "eval_count":eval_count,
        "prompt_eval_count":prompt_count,
        "total_duration_ms":total_duration/1_000_000.0,
        "load_duration_ms":load_duration/1_000_000.0
    }

def median(values):
    vals=[
        float(v)
        for v in values
        if v is not None
    ]

    return statistics.median(vals) if vals else None

def pct(v):
    return round(v*100.0,2)

def benchmark(model,label):
    print()
    print("="*70)
    print(label,model)
    print("="*70)

    unload(model)
    time.sleep(1)

    cold=generate_stream(
        model,
        "Return only AVA."
    )

    warmup(model)

    results=[]
    correct=0

    for index,test in enumerate(TESTS,1):

        repetitions=[]

        for rep in range(REPEATS):

            try:
                r=generate_stream(
                    model,
                    test["prompt"]
                )

                repetitions.append(r)

            except Exception as e:
                repetitions.append({
                    "response":"",
                    "ttft_ms":None,
                    "wall_ms":None,
                    "tokens_per_second":0,
                    "error":str(e)
                })

        answer=normalize(
            repetitions[0].get("response","")
        )

        passed=bool(
            re.fullmatch(
                test["expected"],
                answer
            )
        )

        if passed:
            correct+=1

        result={
            "id":test["id"],
            "passed":passed,
            "answer":answer,
            "expected":test["expected"],
            "ttft_ms":median(
                [x.get("ttft_ms") for x in repetitions]
            ),
            "wall_ms":median(
                [x.get("wall_ms") for x in repetitions]
            ),
            "tokens_per_second":median(
                [x.get("tokens_per_second") for x in repetitions]
            ),
            "runs":repetitions
        }

        results.append(result)

        state="PASS" if passed else "FAIL"

        print(
            f"{index:02d} {test['id']:<18} "
            f"{state:<5} "
            f"TTFT={result['ttft_ms'] or 0:7.1f}ms "
            f"TPS={result['tokens_per_second'] or 0:6.2f} "
            f"ANSWER={answer[:45]}"
        )

    quality=correct/len(TESTS)

    summary={
        "label":label,
        "model":model,
        "details":model_details(model),
        "size_bytes":model_size(model),
        "size_gb":round(model_size(model)/(1024**3),3),
        "quality_correct":correct,
        "quality_total":len(TESTS),
        "quality_score":pct(quality),
        "cold_start_ttft_ms":cold.get("ttft_ms"),
        "cold_start_wall_ms":cold.get("wall_ms"),
        "median_ttft_ms":median(
            [x["ttft_ms"] for x in results]
        ),
        "median_wall_ms":median(
            [x["wall_ms"] for x in results]
        ),
        "median_tokens_per_second":median(
            [x["tokens_per_second"] for x in results]
        ),
        "results":results
    }

    return summary

q4=benchmark(Q4_MODEL,"Q4")
q8=benchmark(Q8_MODEL,"Q8")

q4_quality=q4["quality_score"]
q8_quality=q8["quality_score"]

q4_ttft=q4["median_ttft_ms"] or 999999
q8_ttft=q8["median_ttft_ms"] or 999999

q4_wall=q4["median_wall_ms"] or 999999
q8_wall=q8["median_wall_ms"] or 999999

q4_tps=q4["median_tokens_per_second"] or 0
q8_tps=q8["median_tokens_per_second"] or 0

quality_delta=q4_quality-q8_quality

quality_retention=(
    round((q4_quality/q8_quality)*100.0,2)
    if q8_quality>0
    else 100.0
)

ttft_improvement=(
    round(((q8_ttft-q4_ttft)/q8_ttft)*100.0,2)
    if q8_ttft>0
    else 0
)

wall_improvement=(
    round(((q8_wall-q4_wall)/q8_wall)*100.0,2)
    if q8_wall>0
    else 0
)

tps_improvement=(
    round(((q4_tps-q8_tps)/q8_tps)*100.0,2)
    if q8_tps>0
    else 0
)

if q4_quality >= q8_quality-5:

    if (
        q4_ttft < q8_ttft or
        q4_wall < q8_wall or
        q4_tps > q8_tps
    ):
        winner="Q4"
        winner_model=Q4_MODEL
        reason=(
            "Q4 preserved reasoning within the 5-point quality tolerance "
            "while providing the better local latency/throughput profile."
        )
    else:
        winner="Q8"
        winner_model=Q8_MODEL
        reason=(
            "Q4 retained quality but did not produce a meaningful latency "
            "advantage on this machine."
        )

else:
    winner="Q8"
    winner_model=Q8_MODEL
    reason=(
        "Q4 lost more than 5 percentage points of benchmark reasoning quality."
    )

report={
    "schema":"JGA-AVA-1B-QUANT-BENCHMARK-1",
    "generated_at":datetime.now().astimezone().isoformat(),
    "purpose":"Compare 4-bit and 8-bit quantization for AVA's local 1B reasoning model.",
    "benchmark_scope":"LOCAL MACHINE TEST ONLY",
    "settings":{
        "temperature":0,
        "seed":42,
        "num_ctx":2048,
        "num_predict":80,
        "repeats_per_test":REPEATS,
        "quality_tests":len(TESTS)
    },
    "q4":q4,
    "q8":q8,
    "comparison":{
        "q4_quality_minus_q8_points":round(quality_delta,2),
        "q4_quality_retention_percent":quality_retention,
        "q4_ttft_improvement_percent":ttft_improvement,
        "q4_wall_latency_improvement_percent":wall_improvement,
        "q4_generation_tps_improvement_percent":tps_improvement
    },
    "recommendation":{
        "winner":winner,
        "model":winner_model,
        "reason":reason,
        "automatic_core_switch_performed":False
    },
    "claim_boundary":{
        "quality":"Score reflects these deterministic local tests, not universal reasoning ability.",
        "latency":"Measurements apply to this machine/runtime/configuration.",
        "certification":False
    }
}

outfile=EVIDENCE/f"AVA_1B_QUANT_BENCHMARK_{STAMP}.json"
latest=EVIDENCE/"AVA_1B_QUANT_BENCHMARK_LATEST.json"
winnerfile=EVIDENCE/"AVA_1B_QUANT_WINNER.json"

outfile.write_text(
    json.dumps(report,indent=2,ensure_ascii=False),
    encoding="utf-8"
)

latest.write_text(
    json.dumps(report,indent=2,ensure_ascii=False),
    encoding="utf-8"
)

winnerfile.write_text(
    json.dumps(report["recommendation"],indent=2),
    encoding="utf-8"
)

print()
print("="*70)
print("AVA QUANTIZATION RESULT")
print("="*70)

print(
    f"Q4 QUALITY : {q4['quality_score']:.2f}% "
    f"({q4['quality_correct']}/{q4['quality_total']})"
)

print(
    f"Q8 QUALITY : {q8['quality_score']:.2f}% "
    f"({q8['quality_correct']}/{q8['quality_total']})"
)

print()

print(
    f"Q4 TTFT    : {q4['median_ttft_ms']:.1f} ms"
    if q4['median_ttft_ms'] is not None
    else "Q4 TTFT    : UNRESOLVED"
)

print(
    f"Q8 TTFT    : {q8['median_ttft_ms']:.1f} ms"
    if q8['median_ttft_ms'] is not None
    else "Q8 TTFT    : UNRESOLVED"
)

print(
    f"Q4 TPS     : {q4['median_tokens_per_second']:.2f}"
    if q4['median_tokens_per_second'] is not None
    else "Q4 TPS     : UNRESOLVED"
)

print(
    f"Q8 TPS     : {q8['median_tokens_per_second']:.2f}"
    if q8['median_tokens_per_second'] is not None
    else "Q8 TPS     : UNRESOLVED"
)

print()

print(f"Q4 QUALITY RETENTION : {quality_retention:.2f}%")
print(f"Q4 TTFT CHANGE       : {ttft_improvement:+.2f}% faster")
print(f"Q4 WALL CHANGE       : {wall_improvement:+.2f}% faster")
print(f"Q4 TPS CHANGE        : {tps_improvement:+.2f}%")

print()
print("WINNER      :",winner)
print("AVA MODEL   :",winner_model)
print("WHY         :",reason)
print()
print("NO AVA MODEL WAS SILENTLY CHANGED.")
print("BENCHMARK IS LOCAL EVIDENCE, NOT UNIVERSAL CERTIFICATION.")
print("PROOF       :",outfile)
print("="*70)
