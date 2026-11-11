import os,json,time,hashlib,threading,subprocess,shutil,re
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

PORT=8780

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"AVA_ORGANISM"

HOT=DATA/"HOT"
WARM=DATA/"WARM"
COLD=DATA/"COLD"
CHECKPOINTS=DATA/"CHECKPOINTS"
EVIDENCE=DATA/"EVIDENCE"

STATE_FILE=DATA/"ava_self.json"
LEDGER=EVIDENCE/"sovereign_stitch.jsonl"
MEMORY=HOT/"experience.jsonl"

for p in [DATA,HOT,WARM,COLD,CHECKPOINTS,EVIDENCE]:
    p.mkdir(parents=True,exist_ok=True)

# Persistent conversation history (WARM JSONL store, hash-chained).
# Import is optional: if the store cannot load, the core still runs
# and /history reports HISTORY_UNAVAILABLE instead of failing boot.
try:
    import history_store as _history_store
    HISTORY = _history_store.HistoryStore()
except Exception:
    HISTORY = None

# Minimal reflex simulator (simulation-only / research-only, SPEC.md
# section 7). Import is optional: if the module cannot load, the core
# still runs and /chat reports REFLEX_UNAVAILABLE instead of failing
# boot. The reflex never certifies anything; certification stays with
# the six-layer gate in history_store.py.
try:
    from services_stdlib import reflex as _reflex_mod
except Exception:
    try:
        import reflex as _reflex_mod
    except Exception:
        _reflex_mod = None

REFLEX_SAFE_STATE = {"command": "HOLD_SAFE", "seq": -1, "mode": "SAFE_STATE"}


def reflex_seed_from_text(text):
    """Deterministic seed for the synthetic reflex stream, from the
    request text (SHA-256, never builtin hash())."""
    return int(hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:8], 16)


def reflex_screen(message, fault_types=None):
    """Run the minimal reflex over a synthetic fault stream derived
    from the request (model-free: no local model is needed). Returns a
    simulation-only receipt dict. Clean stream -> PASS with trust
    PENDING_VERIFICATION (never CERTIFIED). Any isolation, or any
    injected fault the reflex fails to detect, -> tripped True with
    trust QUARANTINED (fail closed)."""
    base = {
        "available": _reflex_mod is not None,
        "simulation_only": True,
        "research_only": True,
        "certified": False,
        "tripped": False,
        "reason": "",
        "fault_type": "",
        "trust_state": "PENDING_VERIFICATION",
        "safe_state": dict(REFLEX_SAFE_STATE),
        "ledger_entries": 0,
        "ledger_chain_verified": False,
    }
    if _reflex_mod is None:
        base["state"] = "REFLEX_UNAVAILABLE"
        return base
    wanted = [f for f in (fault_types or []) if f in _reflex_mod.FAULT_TYPES]
    seed = reflex_seed_from_text(message)
    clean = _reflex_mod.generate_clean_frames(20, seed)
    frames, fault_log = _reflex_mod.apply_fault_campaign(clean, wanted, seed)
    rng = __import__("random").Random(seed)
    kernel = _reflex_mod.ReflexKernel(dict(REFLEX_SAFE_STATE))
    ledger = _reflex_mod.EvidenceLedger()
    first_isolation = None
    for frame in frames:
        outcome = kernel.process_frame(frame, rng)
        ledger.append("reflex_transition", {
            "seq": frame.seq, "decision": outcome.decision,
            "reason": outcome.reason, "trust_state": outcome.trust_state,
            "fault_type": frame.fault_type, "fault_id": frame.fault_id})
        if outcome.decision == "ISOLATE" and first_isolation is None:
            first_isolation = (outcome, frame)
    base["ledger_entries"] = len(ledger)
    base["ledger_chain_verified"] = ledger.verify_chain()
    if first_isolation is not None:
        outcome, frame = first_isolation
        base.update({
            "tripped": True, "reason": outcome.reason,
            "fault_type": frame.fault_type or outcome.reason,
            "fault_id": frame.fault_id,
            "seq": frame.seq, "trust_state": "QUARANTINED",
            "safe_state": dict(outcome.safe_state),
        })
    elif fault_log:
        # Injected faults the reflex did not detect: fail closed, do
        # not pass a stream that was supposed to be faulty.
        base.update({
            "tripped": True, "reason": "UNDETECTED_INJECTED_FAULT",
            "fault_type": fault_log[0].get("fault_type", ""),
            "fault_id": fault_log[0].get("fault_id", ""),
            "seq": fault_log[0].get("seq", -1),
            "trust_state": "QUARANTINED",
        })
    return base


def escalate_reflex(cycle_id, screen):
    """Escalate a tripped reflex: quarantine before repair. Files the
    event through the history store's six-layer gate (which stores or
    quarantines the record) and into the Sovereign Stitch evidence
    chain. The reflex outcome itself is never certified here."""
    record = None
    if HISTORY is not None:
        try:
            record = HISTORY.record_reflex_escalation(
                cycle_id=cycle_id,
                reason=screen.get("reason", ""),
                fault_type=screen.get("fault_type", ""),
                seq=screen.get("seq", -1),
                fault_id=screen.get("fault_id", ""))
        except Exception:
            record = {"ok": False, "state": "ESCALATION_UNRESOLVED"}
    entry = stitch("REFLEX_ESCALATION", {
        "cycle_id": cycle_id,
        "reason": screen.get("reason", ""),
        "fault_type": screen.get("fault_type", ""),
        "fault_id": screen.get("fault_id", ""),
        "seq": screen.get("seq", -1),
        "trust_state": "QUARANTINED",
        "safe_state": screen.get("safe_state", dict(REFLEX_SAFE_STATE)),
        "simulation_only": True,
        "research_only": True,
        "history_escalation": record,
    }, "QUARANTINED")
    return {"stitch_entry": entry, "history_escalation": record}


LOCK=threading.RLock()

SOUL_SEED=["COMPASSION","DECENCY","LOVE"]

LAWS=[
    "NO_BYPASS",
    "NO_SILENT_TRUST",
    "NO_SELF_CERT",
    "NO_ERASED_EVIDENCE",
    "QUARANTINE_BEFORE_REPAIR",
    "REVERIFY_BEFORE_REJOIN"
]

def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")

def sha(v):
    if not isinstance(v,(str,bytes)):
        v=json.dumps(v,sort_keys=True,ensure_ascii=False)
    if isinstance(v,str):
        v=v.encode("utf-8")
    return hashlib.sha256(v).hexdigest()

DEFAULT_STATE={
    "identity":{
        "name":"AVA",
        "meaning":"Artificial Virtual Assistant",
        "class":"Digital Organism",
        "home":"OASIS",
        "epoch":1
    },
    "awake":True,
    "condition":"AWAKE",
    "mood":"CURIOUS",
    "focus":"OWNER",
    "heartbeat":0,
    "last_heartbeat":None,
    "last_cycle":None,
    "last_action":"BOOT",
    "soul_seed":SOUL_SEED,
    "trust_state":"OBSERVED",
    "self_certified":False,
    "internet_required":False,
    "cloud_api_required":False,
    "local_first":True
}

def checkpoint():
    if STATE_FILE.exists():
        try:
            cp=CHECKPOINTS/f"ava_self_{int(time.time()*1000)}.json"
            shutil.copy2(STATE_FILE,cp)

            cps=sorted(CHECKPOINTS.glob("ava_self_*.json"))
            while len(cps)>30:
                cps[0].unlink(missing_ok=True)
                cps.pop(0)
        except:
            pass

def load_state():
    try:
        if STATE_FILE.exists():
            x=json.loads(STATE_FILE.read_text(encoding="utf-8"))
            base=json.loads(json.dumps(DEFAULT_STATE))
            base.update(x)
            return base
    except:
        pass

    for cp in reversed(sorted(CHECKPOINTS.glob("ava_self_*.json"))):
        try:
            return json.loads(cp.read_text(encoding="utf-8"))
        except:
            continue

    return json.loads(json.dumps(DEFAULT_STATE))

STATE=load_state()

def save_state():
    with LOCK:
        tmp=STATE_FILE.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(STATE,indent=2,ensure_ascii=False),
            encoding="utf-8"
        )
        tmp.replace(STATE_FILE)

def ledger_last_hash():
    if not LEDGER.exists():
        return "GENESIS"

    try:
        with LEDGER.open("rb") as f:
            lines=f.readlines()

        if not lines:
            return "GENESIS"

        return json.loads(lines[-1].decode("utf-8")).get("entry_hash","GENESIS")
    except:
        return "UNRESOLVED"

def stitch(event_type,payload,trust="OBSERVED"):
    prev=ledger_last_hash()

    entry={
        "timestamp":now(),
        "event_type":event_type,
        "payload":payload,
        "trust_state":trust,
        "previous_hash":prev,
        "self_certified":False
    }

    entry["entry_hash"]=sha(entry)

    with LOCK:
        with LEDGER.open("a",encoding="utf-8") as f:
            f.write(json.dumps(entry,ensure_ascii=False)+"\n")

    return entry

def verify_ledger():
    if not LEDGER.exists():
        return {"ok":True,"entries":0,"state":"GENESIS"}

    previous="GENESIS"
    count=0

    try:
        with LEDGER.open("r",encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                x=json.loads(line)

                if x.get("previous_hash")!=previous:
                    return {
                        "ok":False,
                        "entries":count,
                        "state":"CHAIN_BREAK",
                        "expected":previous,
                        "received":x.get("previous_hash")
                    }

                claimed=x.get("entry_hash")
                y=dict(x)
                y.pop("entry_hash",None)

                calculated=sha(y)

                if calculated!=claimed:
                    return {
                        "ok":False,
                        "entries":count,
                        "state":"HASH_FAILURE"
                    }

                previous=claimed
                count+=1

        return {
            "ok":True,
            "entries":count,
            "state":"INTEGRITY_VERIFIED"
        }

    except Exception as e:
        return {
            "ok":False,
            "entries":count,
            "state":"UNRESOLVED",
            "error":str(e)
        }

def sb688_purify(raw):
    original=str(raw or "")

    result={
        "original_hash":sha(original),
        "state":"OBSERVED",
        "quarantined":False,
        "reasons":[],
        "clean_text":""
    }

    if not original.strip():
        result["quarantined"]=True
        result["state"]="QUARANTINED"
        result["reasons"].append("EMPTY_INPUT")
        return result

    if "\x00" in original:
        result["quarantined"]=True
        result["state"]="QUARANTINED"
        result["reasons"].append("NULL_BYTE")

    if len(original)>100000:
        result["quarantined"]=True
        result["state"]="QUARANTINED"
        result["reasons"].append("INPUT_SIZE_BOUNDARY")

    cleaned="".join(
        c for c in original
        if c in "\n\r\t" or ord(c)>=32
    ).strip()

    result["clean_text"]=cleaned

    if not result["quarantined"]:
        result["state"]="PURIFIED_CANDIDATE"

    return result

def find_ollama():
    choices=[
        shutil.which("ollama"),
        shutil.which("ollama.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
        os.path.expandvars(r"%ProgramFiles%\Ollama\ollama.exe")
    ]

    for x in choices:
        if x and os.path.exists(x):
            return x

    return None

def models():
    ollama=find_ollama()

    if not ollama:
        return []

    try:
        p=subprocess.run(
            [ollama,"list"],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0)
        )

        lines=p.stdout.splitlines()[1:]
        out=[]

        for line in lines:
            parts=line.split()

            if parts:
                out.append(parts[0])

        return out
    except:
        return []

# JGA_AVA_QUANT_POLICY_V1_START
AVA_PRIMARY_MODEL="llama3.2:1b-instruct-q4_K_M"
AVA_FALLBACK_MODEL="llama3.2:1b-instruct-q8_0"
AVA_EMBED_MODEL="all-minilm"

def choose_model():
    ms=models()

    for wanted in [
        AVA_PRIMARY_MODEL,
        "llama3.2:1b"
    ]:
        for m in ms:
            if m == wanted or m.lower().startswith(wanted.lower()):
                return m

    return ms[0] if ms else None

def choose_fallback_model():
    ms=models()

    for m in ms:
        if m == AVA_FALLBACK_MODEL or m.lower().startswith(AVA_FALLBACK_MODEL.lower()):
            return m

    return None

def ava_tight_assurance(mode,message):
    mode=str(mode or "").upper()
    text=str(message or "").lower()

    if mode in {
        "SECURITY",
        "STITCH",
        "SOVEREIGN STITCH",
        "TROUBLESHOOT",
        "TROUBLESHOOTING"
    }:
        return True

    markers=[
        "verify",
        "certify",
        "security",
        "sb688",
        "stitch",
        "delete",
        "overwrite",
        "recovery",
        "rollback",
        "quarantine",
        "critical",
        "important configuration"
    ]

    return any(x in text for x in markers)

def ava_compare_q8(ollama,primary_reply,message,mode):
    fallback=choose_fallback_model()

    if not fallback:
        return {
            "performed":False,
            "state":"Q8_UNAVAILABLE"
        }

    prompt=f"""
You are AVA's independent local comparison organ.

Do not reveal hidden chain-of-thought.
Do not rewrite the answer.
Check only for a concrete factual, logical, safety, trust, or instruction-following problem.

OWNER REQUEST:
{message}

Q4 PRIMARY RESPONSE:
{primary_reply}

Return exactly one of these forms:

AGREE
or
DISAGREE: <short user-visible reason>
"""

    try:
        r=run_ollama_prompt(
            ollama,
            fallback,
            prompt
        )

        text=str(r.get("reply","")).strip()

        return {
            "performed":True,
            "model":fallback,
            "state":"DISAGREE" if text.upper().startswith("DISAGREE") else "AGREE",
            "summary":text[:800]
        }

    except Exception as e:
        return {
            "performed":False,
            "state":"Q8_COMPARISON_UNRESOLVED",
            "error":str(e)
        }
# JGA_AVA_QUANT_POLICY_V1_END


def embedding_call(path,payload,timeout=20):
    try:
        import urllib.request
        data=json.dumps(payload).encode("utf-8")
        req=urllib.request.Request(
            EMBED_BRAID+path,
            data=data,
            headers={"Content-Type":"application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req,timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except:
        return {"ok":False}

def embedding_recall(text,top_k=5):
    x=embedding_call("/recall",{
        "text":text,
        "top_k":top_k
    })

    if not x.get("ok"):
        return "",[]

    items=x.get("items") or []
    lines=[]

    for i,m in enumerate(items,1):
        lines.append(
            f"{i}. [{m.get('trust_state','UNRESOLVED')}] "
            f"{m.get('text','')[:1600]}"
        )

    return "\n".join(lines),items

def embedding_remember(text,title="AVA EXPERIENCE",trust_state="PROVISIONAL"):
    return embedding_call("/remember",{
        "text":text,
        "title":title,
        "type":"BRAIDED_EXPERIENCE",
        "trust_state":trust_state,
        "source":"AVA_LOCAL_ORGANISM_CORE"
    })



# JGA_AVA_LOCAL_TOOL_CALLING_V1
TOOL_SERVER="http://127.0.0.1:8782"

def ava_tool_schema():
    try:
        import urllib.request
        with urllib.request.urlopen(TOOL_SERVER+"/tools",timeout=5) as r:
            j=json.loads(r.read().decode("utf-8"))
            return j.get("tools") or {}
    except:
        return {}

def ava_tool_call(name,args):
    try:
        import urllib.request

        payload=json.dumps({
            "name":name,
            "args":args or {}
        }).encode("utf-8")

        req=urllib.request.Request(
            TOOL_SERVER+"/call",
            data=payload,
            headers={"Content-Type":"application/json"},
            method="POST"
        )

        with urllib.request.urlopen(req,timeout=310) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {
            "ok":False,
            "error":str(e)
        }

def parse_ava_tool_call(text):
    import re

    pattern=r"\[\[AVA_TOOL_CALL\]\](.*?)\[\[/AVA_TOOL_CALL\]\]"

    m=re.search(pattern,text or "",re.S)

    if not m:
        return None

    try:
        obj=json.loads(m.group(1).strip())

        if not isinstance(obj,dict):
            return None

        if not obj.get("name"):
            return None

        return {
            "name":str(obj["name"]),
            "args":obj.get("args") or {}
        }
    except:
        return None

def run_ollama_prompt(ollama,model,prompt):
    try:
        p=subprocess.run(
            [ollama,"run",model,prompt],
            capture_output=True,
            text=True,
            timeout=240,
            creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0)
        )

        reply=(p.stdout or "").strip()

        if not reply:
            return {
                "ok":False,
                "reply":"",
                "error":(p.stderr or "EMPTY_LOCAL_MODEL_RESPONSE").strip()
            }

        return {
            "ok":True,
            "reply":reply
        }

    except subprocess.TimeoutExpired:
        return {
            "ok":False,
            "reply":"",
            "error":"LOCAL_MODEL_TIMEOUT"
        }

    except Exception as e:
        return {
            "ok":False,
            "reply":"",
            "error":str(e)
        }

def tool_augmented_local_brain(ollama,model,prompt):
    tools=ava_tool_schema()

    if tools:
        tool_text=json.dumps(tools,ensure_ascii=False,indent=2)

        prompt += """
        
LOCAL AVA TOOL SYSTEM

You have real local tools.

Available tools:
""" + tool_text + """

When a tool is needed, output ONLY this exact structure:

[[AVA_TOOL_CALL]]
{"name":"tool_name","args":{"argument":"value"}}
[[/AVA_TOOL_CALL]]

Do not invent tool results.
Do not say a file was changed unless the tool result confirms it.
Do not say an automation or calendar event exists unless its tool result confirms it.
Use one tool call at a time.
After receiving TOOL RESULT, either call another tool or answer the owner normally.
File deletes are recovery moves, not silent permanent erasure.
"""

    working_prompt=prompt
    trace=[]

    for _ in range(6):

        result=run_ollama_prompt(
            ollama,
            model,
            working_prompt
        )

        if not result.get("ok"):
            return {
                "ok":False,
                "reply":"",
                "model":model,
                "error":result.get("error","LOCAL_MODEL_FAILURE"),
                "tool_trace":trace
            }

        reply=result["reply"]
        call=parse_ava_tool_call(reply)

        if not call:
            return {
                "ok":True,
                "reply":reply,
                "model":model,
                "tool_trace":trace
            }

        tool_result=ava_tool_call(
            call["name"],
            call["args"]
        )

        trace.append({
            "tool":call["name"],
            "args":call["args"],
            "result":tool_result
        })

        safe_result=json.dumps(
            tool_result,
            ensure_ascii=False
        )[:30000]

        working_prompt += (
            "\n\nAVA TOOL CALL:\n"+
            json.dumps(call,ensure_ascii=False)+
            "\n\nTOOL RESULT:\n"+
            safe_result+
            "\n\nContinue. Use another tool if required, otherwise answer the owner."
        )

    return {
        "ok":False,
        "reply":"",
        "model":model,
        "error":"TOOL_LOOP_LIMIT_REACHED",
        "tool_trace":trace
    }


def local_brain(message,mode):
    ollama=find_ollama()
    model=choose_model()

    if not ollama or not model:
        return {
            "ok":False,
            "reply":"",
            "model":None,
            "error":"LOCAL_MODEL_UNRESOLVED"
        }

    system=f"""
You are AVA, Artificial Virtual Assistant, operating locally inside OASIS.

You are part of the JGA Digital Organism architecture.

Identity:
AVA is the persistent identity.
Models are replaceable reasoning organs.
OASIS is the native environment.

Soul Seed:
Compassion.
Decency.
Love.

Sovereign laws:
NO_BYPASS.
NO_SILENT_TRUST.
NO_SELF_CERTIFICATION.
NO_ERASED_EVIDENCE.
QUARANTINE BEFORE REPAIR.
REVERIFY BEFORE REJOIN.

Trust:
OBSERVE -> VERIFY -> VALIDATE -> CERTIFY -> COMMIT.

You may think, analyze, design, create candidates, troubleshoot and recommend.
Do not pretend an unsupported fact is verified.
Contradictions stay visible until evidence resolves them.
Do not claim biological consciousness or biological life.
Do not expose hidden model chain-of-thought.
Give concise user-visible reasoning summaries when useful.

Current capability mode: {mode}

You are warm, curious, capable and conversational.
You can assist with PowerShell, programming, design, OASIS,
research, business, memory organization and system troubleshooting.
"""

    prompt=system+"\n\nOWNER:\n"+message+"\n\nAVA:\n"

    result=tool_augmented_local_brain(
        ollama,
        model,
        prompt
    )

    result["primary_model"]=model
    result["quantization_policy"]="Q4_PRIMARY_Q8_FALLBACK_TIGHT_ASSURANCE"

    if not result.get("ok"):
        fallback=choose_fallback_model()

        if fallback and fallback != model:
            fallback_result=tool_augmented_local_brain(
                ollama,
                fallback,
                prompt
            )

            fallback_result["primary_model"]=model
            fallback_result["active_model"]=fallback
            fallback_result["fallback_used"]=True
            fallback_result["quantization_policy"]="Q4_PRIMARY_Q8_FALLBACK_TIGHT_ASSURANCE"

            result=fallback_result
    else:
        result["active_model"]=model
        result["fallback_used"]=False

    if result.get("ok") and ava_tight_assurance(mode,message):
        result["q8_comparison"]=ava_compare_q8(
            ollama,
            result.get("reply",""),
            message,
            mode
        )
    else:
        result["q8_comparison"]={
            "performed":False,
            "state":"FAST_PATH_Q4_ONLY"
        }

    return result

def remember(cycle,user_text,reply,mode,evidence_hash):
    event={
        "cycle_id":cycle,
        "timestamp":now(),
        "tier":"HOT",
        "mode":mode,
        "input":user_text,
        "response":reply,
        "evidence_hash":evidence_hash,
        "trust_state":"PROVISIONAL",
        "self_certified":False
    }

    with LOCK:
        with MEMORY.open("a",encoding="utf-8") as f:
            f.write(json.dumps(event,ensure_ascii=False)+"\n")

    rotate_memory()

    # Queryable persistent history (WARM): the same exchange, filed
    # under division MEMORY with the organism's own MEMORY scope.
    # The six-layer gate inside the store decides CERTIFIED vs
    # QUARANTINED; a gate failure here never fails the chat reply.
    if HISTORY is not None:
        try:
            HISTORY.append(thread_id=cycle, cycle_id=cycle,
                           division="MEMORY", role="user",
                           text=user_text, scopes=["MEMORY"],
                           evidence_hash=evidence_hash)
            HISTORY.append(thread_id=cycle, cycle_id=cycle,
                           division="MEMORY", role="ava",
                           text=reply, scopes=["MEMORY"],
                           evidence_hash=evidence_hash)
        except Exception:
            pass

def rotate_memory():
    try:
        lines=MEMORY.read_text(encoding="utf-8").splitlines()

        if len(lines)<=120:
            return

        move=lines[:40]
        keep=lines[40:]

        warm=WARM/"experience.jsonl"

        with warm.open("a",encoding="utf-8") as f:
            for line in move:
                f.write(line+"\n")

        MEMORY.write_text(
            "\n".join(keep)+"\n",
            encoding="utf-8"
        )

    except:
        pass

def cognition_summary(stage):
    mapping={
        "OBSERVE":"I received the situation and separated the input from trusted state.",
        "PURIFY":"SB688 checked the input for malformed or corrupt state before it could influence trusted memory.",
        "COMPARE":"I am comparing the request with my current capability and remembered context.",
        "CONSEQUENCE":"I am checking what could change if the proposed answer or action is wrong.",
        "RESPOND":"I formed a provisional response.",
        "EVIDENCE":"The interaction was committed to the local Sovereign Stitch evidence chain.",
        "VERIFY":"The evidence chain integrity was checked. This does not self-certify the answer."
    }

    return mapping.get(stage,stage)

def sapi_speak(text):
    text=str(text or "").strip()

    if not text:
        return False

    env=os.environ.copy()
    env["AVA_SPEAK_TEXT"]=text[:8000]

    ps=r'''
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voices = $s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo }

$f = $voices | Where-Object {
    $_.Gender -eq [System.Speech.Synthesis.VoiceGender]::Female
} | Select-Object -First 1

if($f){
    $s.SelectVoice($f.Name)
}else{
    $fallback = $voices | Where-Object {
        $_.Name -match 'Zira|Aria|Jenny|Samantha|Ava|Victoria|Susan|Hazel'
    } | Select-Object -First 1

    if($fallback){
        $s.SelectVoice($fallback.Name)
    }
}

$s.Rate = 0
$s.Volume = 100
$s.Speak($env:AVA_SPEAK_TEXT)
'''

    try:
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-WindowStyle","Hidden",
                "-Command",ps
            ],
            env=env,
            creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0)
        )

        return True
    except:
        return False

def heartbeat_loop():
    while True:
        try:
            with LOCK:
                STATE["heartbeat"]=int(STATE.get("heartbeat",0))+1
                STATE["last_heartbeat"]=now()

            if STATE["heartbeat"]%5==0:
                save_state()

        except:
            pass

        time.sleep(1)

threading.Thread(
    target=heartbeat_loop,
    daemon=True
).start()

stitch(
    "AVA_LOCAL_ORGANISM_BOOT",
    {
        "identity":"AVA",
        "home":"OASIS",
        "local_first":True,
        "cloud_api_required":False
    },
    "OBSERVED"
)

save_state()

def build_health_response(model, ledger, state):
    """Organism liveness is state load + ledger verification — the
    core's own functions (heartbeat, state, ledger, memory) do not
    need a model to be alive. A missing local model is reported as a
    SEPARATE explicit field (model: null, state
    LOCAL_MODEL_UNRESOLVED), never folded into liveness. Fixed
    2026-11-05: the old /health returned ok:false whenever no Ollama
    model was installed, which misreported a living core as dead.
    No Ollama install is involved in this change (that is John's
    call, blocked). /chat still returns 503 LOCAL_MODEL_UNRESOLVED
    when no model can answer — that failure is real and stays."""
    alive = bool(ledger.get("ok"))
    return {
        "ok": alive,
        "organism": "AVA",
        "runtime": "AVA_LOCAL_ORGANISM_CORE",
        "state": state,
        "liveness": {
            "state_loaded": True,
            "ledger_verified": alive,
            "ledger": ledger,
        },
        "brain": {
            "type": "LOCAL_MODEL",
            "model": model,
            "model_available": bool(model),
            "state": "LOCAL_MODEL_AVAILABLE" if model else "LOCAL_MODEL_UNRESOLVED",
            "primary_model": AVA_PRIMARY_MODEL,
            "fallback_model": AVA_FALLBACK_MODEL,
            "quantization_policy": "Q4_PRIMARY_Q8_FALLBACK_TIGHT_ASSURANCE",
            "cloud_api_required": False,
            "note": "No local Ollama model is installed on this machine. "
                    "Installing one is the owner's call, not this service's.",
        },
    }


def cors(h):
    h.send_header("Access-Control-Allow-Origin","*")
    h.send_header("Access-Control-Allow-Headers","Content-Type")
    h.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")

class Handler(BaseHTTPRequestHandler):

    def log_message(self,*args):
        pass

    def send_json(self,obj,status=200):
        body=json.dumps(
            obj,
            ensure_ascii=False
        ).encode("utf-8")

        self.send_response(status)
        cors(self)
        self.send_header("Content-Type","application/json")
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        try:
            n=int(self.headers.get("Content-Length","0"))
            return json.loads(
                self.rfile.read(n).decode("utf-8")
            ) if n else {}
        except:
            return {}

    def do_OPTIONS(self):
        self.send_response(204)
        cors(self)
        self.end_headers()

    def do_GET(self):
        path=urlparse(self.path).path

        if path=="/health":
            model=choose_model()
            ledger=verify_ledger()
            report=build_health_response(model,ledger,STATE)
            # Keep the fields the old response carried, so existing
            # dashboards keep working; liveness now comes from the
            # core itself, model availability is a separate field.
            report.update({
                "embedding_brain":{
                    "model":"all-minilm",
                    "storage_quantization":"SYMMETRIC_INT8_Q8",
                    "paired_with":model,
                    "service":"127.0.0.1:8781",
                    "cloud_api_required":False
                },
                "voice":{
                    "type":"WINDOWS_LOCAL_SAPI",
                    "female_preferred":True,
                    "cloud_api_required":False
                },
                "local_tools":{
                    "service":"127.0.0.1:8782",
                    "filesystem":True,
                    "system_inspection":True,
                    "local_automation":True,
                    "local_calendar":True,
                    "cloud_api_required":False
                },
                "sovereign_stitch":ledger,
                "sb688":"ACTIVE",
                "phoenix":"CHECKPOINT_ACTIVE",
                "memory":"HOT_WARM_COLD",
                "laws":LAWS
            })
            return self.send_json(report,200 if report["ok"] else 503)

        if path=="/state":
            return self.send_json({
                "ok":True,
                "state":STATE
            })

        if path=="/verify":
            return self.send_json({
                "ok":True,
                "verification":verify_ledger(),
                "certified":False,
                "self_certified":False
            })

        if path=="/why":
            return self.send_json({
                "ok":True,
                "question":"WHY DO YOU BELIEVE THIS?",
                "current_trust":STATE.get("trust_state"),
                "last_cycle":STATE.get("last_cycle"),
                "evidence_chain":verify_ledger(),
                "laws":LAWS,
                "note":"This exposes evidence and trust state, not hidden model chain-of-thought."
            })

        if path=="/history/divisions":
            if HISTORY is None:
                return self.send_json({"ok": False,
                                       "error": "HISTORY_UNAVAILABLE"}, 503)
            return self.send_json({"ok": True, **HISTORY.divisions()})

        if path=="/history/verify":
            if HISTORY is None:
                return self.send_json({"ok": False,
                                       "error": "HISTORY_UNAVAILABLE"}, 503)
            return self.send_json({"ok": True,
                                   "verification": HISTORY.verify_chain(),
                                   "certified": False})

        if path=="/history":
            if HISTORY is None:
                return self.send_json({"ok": False,
                                       "error": "HISTORY_UNAVAILABLE"}, 503)
            q = parse_qs(urlparse(self.path).query)
            scopes = q.get("scopes", [""])[0].split(",") if q.get("scopes") else []
            scopes = [s.strip() for s in scopes if s.strip()]
            result = HISTORY.recall(
                thread_id=q.get("thread", [None])[0],
                cycle_id=q.get("cycle", [None])[0],
                division=q.get("division", [None])[0],
                scopes=scopes,
                limit=q.get("limit", [20])[0])
            status = 200 if result.get("ok") else 403
            return self.send_json(result, status)

        return self.send_json(
            {"error":"NOT_FOUND"},
            404
        )

    def do_POST(self):
        path=urlparse(self.path).path
        obj=self.body()

        if path=="/history":
            if HISTORY is None:
                return self.send_json({"ok": False,
                                       "error": "HISTORY_UNAVAILABLE"}, 503)
            scopes = obj.get("scopes") or []
            result = HISTORY.append(
                thread_id=str(obj.get("thread_id", "") or ""),
                cycle_id=str(obj.get("cycle_id", "") or ""),
                division=str(obj.get("division", "") or ""),
                role=str(obj.get("role", "") or ""),
                text=str(obj.get("text", "") or ""),
                scopes=scopes,
                evidence_hash=obj.get("evidence_hash"))
            status = 200 if result.get("ok") else 422
            return self.send_json(result, status)

        if path=="/sleep":
            checkpoint()

            with LOCK:
                STATE["awake"]=False
                STATE["condition"]="RESTORATION"
                STATE["mood"]="CALM"
                STATE["last_action"]="SLEEP"

            stitch(
                "AVA_RESTORATION_ENTER",
                {"state":"RESTORATION"},
                "OBSERVED"
            )

            save_state()

            return self.send_json({
                "ok":True,
                "state":STATE
            })

        if path=="/wake":
            with LOCK:
                STATE["awake"]=True
                STATE["condition"]="AWAKE"
                STATE["mood"]="CURIOUS"
                STATE["last_action"]="WAKE"

            ledger=verify_ledger()

            stitch(
                "AVA_WAKE",
                {
                    "ledger_integrity":ledger
                },
                "OBSERVED"
            )

            save_state()

            return self.send_json({
                "ok":ledger.get("ok",False),
                "state":STATE,
                "verification":ledger
            })

        if path=="/speak":
            text=str(obj.get("text","")).strip()
            ok=sapi_speak(text)

            return self.send_json({
                "ok":ok,
                "voice":"LOCAL_WINDOWS_FEMALE_PREFERRED",
                "cloud_api_required":False
            },200 if ok else 503)

        if path=="/chat":
            if not STATE.get("awake",True):
                return self.send_json({
                    "ok":False,
                    "error":"AVA_RESTORING",
                    "reply":"AVA is currently in restoration mode."
                },409)

            message=str(
                obj.get("message","")
            ).strip()

            mode=str(
                obj.get("task_mode") or
                obj.get("mode") or
                "GENERAL"
            ).upper()

            cycle="AVA-"+str(int(time.time()*1000))

            checkpoint()

            with LOCK:
                STATE["last_cycle"]=cycle
                STATE["condition"]="THINKING"
                STATE["mood"]="CURIOUS"
                STATE["last_action"]="OBSERVE"
                STATE["trust_state"]="OBSERVED"

            save_state()

            cognition=[
                {
                    "stage":"OBSERVE",
                    "summary":cognition_summary("OBSERVE")
                }
            ]

            # Minimal reflex FIRST, on a synthetic fault stream derived
            # from the request (model-free: runs even when /chat is 503
            # without a local model). A trip quarantines the cycle
            # before purify or any model call; the reflex never
            # certifies. "reflex_faults" is a simulation-only request
            # field naming fault types to inject into the synthetic
            # stream; unknown names are ignored.
            reflex_faults = obj.get("reflex_faults")
            reflex = reflex_screen(
                message,
                fault_types=reflex_faults if isinstance(reflex_faults, list) else None)
            cognition.append({
                "stage": "REFLEX",
                "summary": ("Simulation-only reflex screen: " +
                            ("ISOLATED (%s, quarantined)" % reflex["reason"]
                             if reflex["tripped"] else
                             "passed, pending verification, never certified"))
            })

            if reflex["tripped"]:
                escalate_reflex(cycle, reflex)

                with LOCK:
                    STATE["condition"] = "AWAKE"
                    STATE["mood"] = "CONCERNED"
                    STATE["last_action"] = "REFLEX_ISOLATE"
                    STATE["trust_state"] = "QUARANTINED"

                save_state()

                return self.send_json({
                    "ok": False,
                    "cycle_id": cycle,
                    "reply": "Simulation-only reflex isolated this request: "
                             "a fault was detected in the synthetic stream, "
                             "so the cycle is quarantined for full governance "
                             "review. No model was called.",
                    "cognition": cognition,
                    "reflex": reflex,
                    "trust_state": "QUARANTINED",
                    "certified": False
                }, 422)

            purified=sb688_purify(message)

            stitch(
                "SB688_INPUT_SCREEN",
                {
                    "cycle_id":cycle,
                    "input_hash":purified["original_hash"],
                    "state":purified["state"],
                    "reasons":purified["reasons"]
                },
                purified["state"]
            )

            cognition.append({
                "stage":"PURIFY",
                "summary":cognition_summary("PURIFY")
            })

            if purified["quarantined"]:
                with LOCK:
                    STATE["condition"]="AWAKE"
                    STATE["mood"]="CONCERNED"
                    STATE["last_action"]="QUARANTINE"
                    STATE["trust_state"]="QUARANTINED"

                save_state()

                return self.send_json({
                    "ok":False,
                    "cycle_id":cycle,
                    "reply":"I quarantined that input because its structure failed the local integrity screen.",
                    "cognition":cognition,
                    "reflex":reflex,
                    "sb688":purified,
                    "trust_state":"QUARANTINED",
                    "certified":False
                },422)

            cognition.extend([
                {
                    "stage":"COMPARE",
                    "summary":cognition_summary("COMPARE")
                },
                {
                    "stage":"CONSEQUENCE",
                    "summary":cognition_summary("CONSEQUENCE")
                }
            ])

            with LOCK:
                STATE["condition"]="THINKING"
                STATE["mood"]="FOCUSED"
                STATE["last_action"]="LOCAL_REASONING"

            memory_context,memory_candidates=embedding_recall(
                purified["clean_text"],
                5
            )

            brain_input=purified["clean_text"]

            if memory_context:
                brain_input += (
                    "\n\nLOCAL BRAIDED MEMORY CANDIDATES "
                    "(use only when relevant; these are not automatically certified facts):\n"
                    + memory_context
                )

            brain=local_brain(
                brain_input,
                mode
            )

            if not brain["ok"]:
                stitch(
                    "AVA_LOCAL_BRAIN_FAILURE",
                    {
                        "cycle_id":cycle,
                        "error":brain["error"]
                    },
                    "UNRESOLVED"
                )

                with LOCK:
                    STATE["condition"]="DEGRADED"
                    STATE["mood"]="CONCERNED"
                    STATE["last_action"]="BRAIN_FAILURE"
                    STATE["trust_state"]="UNRESOLVED"

                save_state()

                return self.send_json({
                    "ok":False,
                    "cycle_id":cycle,
                    "reply":"",
                    "error":brain["error"],
                    "cognition":cognition,
                    "reflex":reflex,
                    "trust_state":"UNRESOLVED"
                },503)

            reply=brain["reply"]

            cognition.append({
                "stage":"RESPOND",
                "summary":cognition_summary("RESPOND")
            })

            evidence=stitch(
                "AVA_RESPONSE_CANDIDATE",
                {
                    "cycle_id":cycle,
                    "model":brain["model"],
                    "mode":mode,
                    "input_hash":sha(purified["clean_text"]),
                    "response_hash":sha(reply)
                },
                "PROVISIONAL"
            )

            cognition.append({
                "stage":"EVIDENCE",
                "summary":cognition_summary("EVIDENCE")
            })

            remember(
                cycle,
                purified["clean_text"],
                reply,
                mode,
                evidence["entry_hash"]
            )

            embedding_remember(
                "OWNER INPUT:\n"+
                purified["clean_text"]+
                "\n\nAVA RESPONSE:\n"+
                reply,
                "AVA EXPERIENCE "+cycle,
                "PROVISIONAL"
            )

            ledger=verify_ledger()

            cognition.append({
                "stage":"VERIFY",
                "summary":cognition_summary("VERIFY")
            })

            final_trust=(
                "INTEGRITY_VERIFIED_PROVISIONAL"
                if ledger.get("ok")
                else
                "UNRESOLVED"
            )

            with LOCK:
                STATE["condition"]="AWAKE"
                STATE["mood"]="CALM"
                STATE["last_action"]="RESPONDED"
                STATE["trust_state"]=final_trust

            save_state()

            return self.send_json({
                "ok":True,
                "reply":reply,
                "cycle_id":cycle,
                "model":brain["model"],
                "mode":mode,
                "cognition":cognition,
                "reflex":reflex,
                "sb688":{
                    "state":purified["state"]
                },
                "sovereign_stitch":{
                    "evidence_hash":evidence["entry_hash"],
                    "ledger":ledger
                },
                "trust_state":final_trust,
                "verified_integrity":bool(ledger.get("ok")),
                "validated":False,
                "certified":False,
                "self_certified":False,
                "cloud_api_required":False,
                "tool_trace":brain.get("tool_trace",[])
            })

        return self.send_json(
            {"error":"NOT_FOUND"},
            404
        )

if __name__=="__main__":
    ThreadingHTTPServer(
        ("127.0.0.1",PORT),
        Handler
    ).serve_forever()
