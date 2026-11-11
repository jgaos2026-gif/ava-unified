import os,json,time,hashlib,shutil,subprocess,threading,datetime,re
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse

PORT=8782

RUNTIME=Path(__file__).resolve().parent
PROJECT=RUNTIME.parent.resolve()
SANDBOX=(RUNTIME/"AVA_SANDBOX").resolve()
FILES=(SANDBOX/"FILES").resolve()
SCRIPTS=(SANDBOX/"SCRIPTS").resolve()
AUTOMATIONS=(SANDBOX/"AUTOMATIONS").resolve()
CALENDAR=(SANDBOX/"CALENDAR").resolve()
EVIDENCE=(RUNTIME/"AVA_ORGANISM"/"EVIDENCE").resolve()

CAL_FILE=CALENDAR/"AVA_CALENDAR.json"
ICS_FILE=CALENDAR/"AVA_CALENDAR.ics"
AUTO_FILE=AUTOMATIONS/"AVA_AUTOMATIONS.json"
TOOL_LEDGER=EVIDENCE/"ava_tool_calls.jsonl"

for p in [SANDBOX,FILES,SCRIPTS,AUTOMATIONS,CALENDAR,EVIDENCE]:
    p.mkdir(parents=True,exist_ok=True)

LOCK=threading.RLock()

TOOLS={
 "fs_list":{
   "description":"List files or folders inside AVA sandbox or OASIS project.",
   "args":{"path":"relative path or project-relative path"}
 },
 "fs_read":{
   "description":"Read a local text file.",
   "args":{"path":"path","max_chars":"optional integer"}
 },
 "fs_write":{
   "description":"Create or update a local text file. Existing project files are backed up first.",
   "args":{"path":"path","content":"text","overwrite":"boolean"}
 },
 "fs_mkdir":{
   "description":"Create a local directory.",
   "args":{"path":"path"}
 },
 "fs_copy":{
   "description":"Copy file or directory.",
   "args":{"source":"path","destination":"path"}
 },
 "fs_move":{
   "description":"Move file or directory.",
   "args":{"source":"path","destination":"path"}
 },
 "fs_delete":{
   "description":"Remove a sandbox/project item by moving it into AVA recovery storage instead of permanent erase.",
   "args":{"path":"path"}
 },
 "system_info":{
   "description":"Read local Windows, disk, Python, host and OASIS runtime information.",
   "args":{}
 },
 "process_list":{
   "description":"List local processes, optionally filtered.",
   "args":{"query":"optional process-name filter"}
 },
 "port_check":{
   "description":"Check whether a local TCP port is listening.",
   "args":{"port":"integer"}
 },
 "calendar_add":{
   "description":"Add an event to AVA local calendar and regenerate ICS.",
   "args":{"title":"text","start":"ISO datetime","end":"optional ISO datetime","notes":"optional text","location":"optional text"}
 },
 "calendar_list":{
   "description":"List AVA local calendar events.",
   "args":{"from":"optional ISO datetime","limit":"optional integer"}
 },
 "calendar_delete":{
   "description":"Delete an AVA local calendar event by id.",
   "args":{"id":"event id"}
 },
 "calendar_export":{
   "description":"Return the path to AVA local ICS calendar.",
   "args":{}
 },
 "automation_add":{
   "description":"Create an AVA local automation. Action may be reminder or run_script. Scripts must live in AVA_SANDBOX/SCRIPTS.",
   "args":{"name":"text","run_at":"ISO datetime","repeat":"NONE|DAILY|WEEKLY|HOURLY","action":"reminder|run_script","message":"optional reminder text","script":"optional script filename"}
 },
 "automation_list":{
   "description":"List AVA local automations.",
   "args":{}
 },
 "automation_delete":{
   "description":"Delete an AVA automation by id.",
   "args":{"id":"automation id"}
 },
 "automation_run":{
   "description":"Run one AVA automation immediately.",
   "args":{"id":"automation id"}
 }
}

def now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")

def sha(x):
    if not isinstance(x,str):
        x=json.dumps(x,sort_keys=True,ensure_ascii=False)
    return hashlib.sha256(x.encode("utf-8")).hexdigest()

def load_json(path,default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except:
        pass
    return default

def save_json(path,obj):
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding="utf-8")
    tmp.replace(path)

def log_tool(name,args,result):
    entry={
      "timestamp":now(),
      "tool":name,
      "args":args,
      "result_state":"OK" if result.get("ok") else "FAILED",
      "result_hash":sha(result),
      "self_certified":False
    }

    with LOCK:
        with TOOL_LEDGER.open("a",encoding="utf-8") as f:
            f.write(json.dumps(entry,ensure_ascii=False)+"\n")

def resolve_path(value,write=False):
    raw=str(value or "").strip()

    if not raw or raw==".":
        return FILES

    p=Path(raw)

    if p.is_absolute():
        target=p.resolve()
    else:
        if raw.lower().startswith("project/"):
            target=(PROJECT/raw[8:]).resolve()
        elif raw.lower().startswith("sandbox/"):
            target=(SANDBOX/raw[8:]).resolve()
        else:
            target=(FILES/raw).resolve()

    allowed=False

    for root in [PROJECT,SANDBOX]:
        try:
            target.relative_to(root)
            allowed=True
            break
        except:
            pass

    if not allowed:
        raise PermissionError("PATH_OUTSIDE_AVA_LOCAL_BOUNDARY")

    blocked=[
      Path(os.environ.get("WINDIR",r"C:\Windows")).resolve(),
      Path(os.environ.get("ProgramFiles",r"C:\Program Files")).resolve()
    ]

    for b in blocked:
        try:
            target.relative_to(b)
            raise PermissionError("SYSTEM_PATH_BLOCKED")
        except ValueError:
            pass

    return target

def recover_delete(path):
    p=resolve_path(path,True)

    if not p.exists():
        return {"ok":False,"error":"NOT_FOUND"}

    recovery=(SANDBOX/"RECOVERY").resolve()
    recovery.mkdir(parents=True,exist_ok=True)

    dest=recovery/f"{int(time.time()*1000)}_{p.name}"

    shutil.move(str(p),str(dest))

    return {
      "ok":True,
      "state":"MOVED_TO_RECOVERY",
      "recovery_path":str(dest)
    }

def fs_list(args):
    p=resolve_path(args.get("path","."))

    if not p.exists():
        return {"ok":False,"error":"NOT_FOUND"}

    if p.is_file():
        return {
          "ok":True,
          "path":str(p),
          "type":"file",
          "size":p.stat().st_size
        }

    items=[]

    for x in sorted(p.iterdir(),key=lambda z:(not z.is_dir(),z.name.lower()))[:300]:
        items.append({
          "name":x.name,
          "type":"directory" if x.is_dir() else "file",
          "size":None if x.is_dir() else x.stat().st_size
        })

    return {"ok":True,"path":str(p),"items":items}

def fs_read(args):
    p=resolve_path(args.get("path",""))

    if not p.exists() or not p.is_file():
        return {"ok":False,"error":"FILE_NOT_FOUND"}

    maximum=max(100,min(100000,int(args.get("max_chars",24000))))

    try:
        text=p.read_text(encoding="utf-8",errors="replace")
    except Exception as e:
        return {"ok":False,"error":str(e)}

    return {
      "ok":True,
      "path":str(p),
      "content":text[:maximum],
      "truncated":len(text)>maximum
    }

def fs_write(args):
    p=resolve_path(args.get("path",""),True)
    content=str(args.get("content",""))
    overwrite=bool(args.get("overwrite",False))

    p.parent.mkdir(parents=True,exist_ok=True)

    if p.exists():
        if not overwrite:
            return {
              "ok":False,
              "error":"FILE_EXISTS",
              "instruction":"Set overwrite true to update. AVA will make a backup first."
            }

        backup=p.with_name(p.name+".ava_backup_"+str(int(time.time())))
        shutil.copy2(p,backup)

    p.write_text(content,encoding="utf-8")

    return {
      "ok":True,
      "path":str(p),
      "bytes":len(content.encode("utf-8"))
    }

def fs_mkdir(args):
    p=resolve_path(args.get("path",""),True)
    p.mkdir(parents=True,exist_ok=True)
    return {"ok":True,"path":str(p)}

def fs_copy(args):
    src=resolve_path(args.get("source",""))
    dst=resolve_path(args.get("destination",""),True)

    if not src.exists():
        return {"ok":False,"error":"SOURCE_NOT_FOUND"}

    dst.parent.mkdir(parents=True,exist_ok=True)

    if src.is_dir():
        shutil.copytree(src,dst,dirs_exist_ok=True)
    else:
        shutil.copy2(src,dst)

    return {"ok":True,"source":str(src),"destination":str(dst)}

def fs_move(args):
    src=resolve_path(args.get("source",""),True)
    dst=resolve_path(args.get("destination",""),True)

    if not src.exists():
        return {"ok":False,"error":"SOURCE_NOT_FOUND"}

    dst.parent.mkdir(parents=True,exist_ok=True)
    shutil.move(str(src),str(dst))

    return {"ok":True,"source":str(src),"destination":str(dst)}

def ps(command,timeout=20):
    try:
        p=subprocess.run(
          ["powershell.exe","-NoProfile","-Command",command],
          capture_output=True,
          text=True,
          timeout=timeout,
          creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0)
        )

        return {
          "ok":p.returncode==0,
          "stdout":(p.stdout or "")[:30000],
          "stderr":(p.stderr or "")[:10000],
          "exit_code":p.returncode
        }
    except Exception as e:
        return {"ok":False,"error":str(e)}

def system_info(args):
    q=r'''
$os=Get-CimInstance Win32_OperatingSystem
$cpu=Get-CimInstance Win32_Processor | Select-Object -First 1
$mem=[math]::Round($os.FreePhysicalMemory/1MB,2)
$drives=Get-PSDrive -PSProvider FileSystem | Select-Object Name,@{N='FreeGB';E={[math]::Round($_.Free/1GB,2)}},@{N='UsedGB';E={[math]::Round($_.Used/1GB,2)}}
[pscustomobject]@{
 Computer=$env:COMPUTERNAME
 Windows=$os.Caption
 Version=$os.Version
 CPU=$cpu.Name
 FreeMemoryGB=$mem
 PowerShell=$PSVersionTable.PSVersion.ToString()
 Drives=$drives
}|ConvertTo-Json -Depth 5
'''

    r=ps(q)

    if not r.get("ok"):
        return r

    try:
        return {"ok":True,"system":json.loads(r["stdout"])}
    except:
        return {"ok":True,"raw":r["stdout"]}

def process_list(args):
    query=str(args.get("query","")).strip().lower()

    q="Get-Process | Select-Object -First 250 Id,ProcessName,CPU,WorkingSet64 | ConvertTo-Json"

    r=ps(q)

    if not r.get("ok"):
        return r

    try:
        data=json.loads(r["stdout"] or "[]")
        if isinstance(data,dict):
            data=[data]

        if query:
            data=[x for x in data if query in str(x.get("ProcessName","")).lower()]

        return {"ok":True,"processes":data[:150]}
    except:
        return {"ok":False,"error":"PROCESS_PARSE_FAILURE"}

def port_check(args):
    port=int(args.get("port",0))

    if port<1 or port>65535:
        return {"ok":False,"error":"INVALID_PORT"}

    q=f"if(Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue){{'LISTENING'}}else{{'CLOSED'}}"

    r=ps(q)

    return {
      "ok":True,
      "port":port,
      "state":"LISTENING" if "LISTENING" in r.get("stdout","") else "CLOSED"
    }

def parse_dt(v):
    return datetime.datetime.fromisoformat(str(v).replace("Z","+00:00"))

def calendar_events():
    return load_json(CAL_FILE,[])

def write_ics(events):
    def esc(v):
        return str(v or "").replace("\\","\\\\").replace(",","\\,").replace(";","\\;").replace("\n","\\n")

    def dt(v):
        d=parse_dt(v)
        if d.tzinfo:
            d=d.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            return d.strftime("%Y%m%dT%H%M%SZ")
        return d.strftime("%Y%m%dT%H%M%S")

    lines=[
      "BEGIN:VCALENDAR",
      "VERSION:2.0",
      "PRODID:-//JGA//AVA Local Calendar//EN",
      "CALSCALE:GREGORIAN"
    ]

    for e in events:
        lines.extend([
          "BEGIN:VEVENT",
          "UID:"+esc(e["id"])+"@ava.local",
          "DTSTAMP:"+datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ"),
          "DTSTART:"+dt(e["start"]),
          "DTEND:"+dt(e["end"]),
          "SUMMARY:"+esc(e["title"]),
          "DESCRIPTION:"+esc(e.get("notes","")),
          "LOCATION:"+esc(e.get("location","")),
          "END:VEVENT"
        ])

    lines.append("END:VCALENDAR")
    ICS_FILE.write_text("\r\n".join(lines)+"\r\n",encoding="utf-8")

def calendar_add(args):
    title=str(args.get("title","")).strip()
    start=str(args.get("start","")).strip()

    if not title or not start:
        return {"ok":False,"error":"TITLE_AND_START_REQUIRED"}

    s=parse_dt(start)

    end=str(args.get("end","")).strip()

    if end:
        e=parse_dt(end)
    else:
        e=s+datetime.timedelta(hours=1)
        end=e.isoformat()

    event={
      "id":"AVACAL-"+str(int(time.time()*1000)),
      "title":title,
      "start":s.isoformat(),
      "end":e.isoformat(),
      "notes":str(args.get("notes","")),
      "location":str(args.get("location","")),
      "created_at":now()
    }

    with LOCK:
        events=calendar_events()
        events.append(event)
        events.sort(key=lambda x:x["start"])
        save_json(CAL_FILE,events)
        write_ics(events)

    return {"ok":True,"event":event}

def calendar_list(args):
    events=calendar_events()
    limit=max(1,min(200,int(args.get("limit",50))))

    start=args.get("from")

    if start:
        d=parse_dt(start)
        events=[
          e for e in events
          if parse_dt(e["end"])>=d
        ]

    return {"ok":True,"events":events[:limit]}

def calendar_delete(args):
    wanted=str(args.get("id",""))

    with LOCK:
        events=calendar_events()
        new=[e for e in events if e.get("id")!=wanted]

        if len(new)==len(events):
            return {"ok":False,"error":"EVENT_NOT_FOUND"}

        save_json(CAL_FILE,new)
        write_ics(new)

    return {"ok":True,"deleted":wanted}

def automations():
    return load_json(AUTO_FILE,[])

def save_automations(x):
    save_json(AUTO_FILE,x)

def safe_script(name):
    p=(SCRIPTS/str(name)).resolve()

    try:
        p.relative_to(SCRIPTS)
    except:
        raise PermissionError("SCRIPT_OUTSIDE_SANDBOX")

    if p.suffix.lower()!=".ps1":
        raise PermissionError("ONLY_POWERSHELL_SCRIPT_FILES_ALLOWED")

    return p

def automation_add(args):
    name=str(args.get("name","")).strip()
    run_at=str(args.get("run_at","")).strip()
    repeat=str(args.get("repeat","NONE")).upper()
    action=str(args.get("action","reminder")).lower()

    if not name or not run_at:
        return {"ok":False,"error":"NAME_AND_RUN_AT_REQUIRED"}

    if repeat not in ["NONE","DAILY","WEEKLY","HOURLY"]:
        return {"ok":False,"error":"INVALID_REPEAT"}

    parse_dt(run_at)

    if action not in ["reminder","run_script"]:
        return {"ok":False,"error":"INVALID_ACTION"}

    script=None

    if action=="run_script":
        script=safe_script(args.get("script",""))

        if not script.exists():
            return {"ok":False,"error":"SCRIPT_NOT_FOUND","path":str(script)}

    item={
      "id":"AVAAUTO-"+str(int(time.time()*1000)),
      "name":name,
      "run_at":parse_dt(run_at).isoformat(),
      "repeat":repeat,
      "action":action,
      "message":str(args.get("message","")),
      "script":str(script) if script else None,
      "enabled":True,
      "last_run":None,
      "created_at":now()
    }

    with LOCK:
        x=automations()
        x.append(item)
        save_automations(x)

    return {"ok":True,"automation":item}

def run_automation(item):
    result={"ok":True}

    if item.get("action")=="reminder":
        result={
          "ok":True,
          "reminder":item.get("message") or item.get("name")
        }

        reminder=SANDBOX/"AVA_REMINDERS.jsonl"

        with reminder.open("a",encoding="utf-8") as f:
            f.write(json.dumps({
              "timestamp":now(),
              "automation_id":item["id"],
              "message":result["reminder"]
            },ensure_ascii=False)+"\n")

    elif item.get("action")=="run_script":
        p=safe_script(Path(item.get("script","")).name)

        result=ps(
          "& '"+str(p).replace("'","''")+"'",
          timeout=300
        )

    return result

def automation_list(args):
    return {"ok":True,"automations":automations()}

def automation_delete(args):
    wanted=str(args.get("id",""))

    with LOCK:
        x=automations()
        new=[a for a in x if a.get("id")!=wanted]

        if len(new)==len(x):
            return {"ok":False,"error":"AUTOMATION_NOT_FOUND"}

        save_automations(new)

    return {"ok":True,"deleted":wanted}

def automation_run(args):
    wanted=str(args.get("id",""))
    x=automations()

    for item in x:
        if item.get("id")==wanted:
            result=run_automation(item)
            item["last_run"]=now()
            save_automations(x)
            return {
              "ok":result.get("ok",False),
              "automation":wanted,
              "result":result
            }

    return {"ok":False,"error":"AUTOMATION_NOT_FOUND"}

FUNCTIONS={
 "fs_list":fs_list,
 "fs_read":fs_read,
 "fs_write":fs_write,
 "fs_mkdir":fs_mkdir,
 "fs_copy":fs_copy,
 "fs_move":fs_move,
 "fs_delete":lambda a:recover_delete(a.get("path","")),
 "system_info":system_info,
 "process_list":process_list,
 "port_check":port_check,
 "calendar_add":calendar_add,
 "calendar_list":calendar_list,
 "calendar_delete":calendar_delete,
 "calendar_export":lambda a:{"ok":True,"ics":str(ICS_FILE)},
 "automation_add":automation_add,
 "automation_list":automation_list,
 "automation_delete":automation_delete,
 "automation_run":automation_run
}

def execute_tool(name,args):
    if name not in FUNCTIONS:
        result={"ok":False,"error":"UNKNOWN_TOOL"}
    else:
        try:
            result=FUNCTIONS[name](args or {})
        except Exception as e:
            result={"ok":False,"error":str(e)}

    log_tool(name,args,result)
    return result

def automation_loop():
    while True:
        try:
            changed=False
            x=automations()
            current=datetime.datetime.now().astimezone()

            for item in x:
                if not item.get("enabled",True):
                    continue

                due=parse_dt(item["run_at"])

                if due.tzinfo is None:
                    due=due.astimezone()

                if current>=due:
                    run_automation(item)
                    item["last_run"]=now()
                    repeat=item.get("repeat","NONE")

                    if repeat=="NONE":
                        item["enabled"]=False
                    elif repeat=="HOURLY":
                        item["run_at"]=(due+datetime.timedelta(hours=1)).isoformat()
                    elif repeat=="DAILY":
                        item["run_at"]=(due+datetime.timedelta(days=1)).isoformat()
                    elif repeat=="WEEKLY":
                        item["run_at"]=(due+datetime.timedelta(days=7)).isoformat()

                    changed=True

            if changed:
                save_automations(x)

        except:
            pass

        time.sleep(15)

threading.Thread(target=automation_loop,daemon=True).start()

class H(BaseHTTPRequestHandler):

    def log_message(self,*a):
        pass

    def cors(self):
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Headers","Content-Type")
        self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")

    def out(self,obj,status=200):
        b=json.dumps(obj,ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.cors()
        self.send_header("Content-Type","application/json")
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Length",str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def body(self):
        try:
            n=int(self.headers.get("Content-Length","0"))
            return json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except:
            return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.cors()
        self.end_headers()

    def do_GET(self):
        path=urlparse(self.path).path

        if path=="/health":
            return self.out({
              "ok":True,
              "service":"AVA_LOCAL_TOOL_SANDBOX",
              "port":PORT,
              "tool_count":len(TOOLS),
              "sandbox":str(SANDBOX),
              "project_root":str(PROJECT),
              "calendar":str(CAL_FILE),
              "calendar_ics":str(ICS_FILE),
              "automation_engine":"LOCAL",
              "cloud_api_required":False,
              "tools":list(TOOLS.keys())
            })

        if path=="/tools":
            return self.out({
              "ok":True,
              "tools":TOOLS
            })

        return self.out({"error":"NOT_FOUND"},404)

    def do_POST(self):
        path=urlparse(self.path).path

        if path!="/call":
            return self.out({"error":"NOT_FOUND"},404)

        obj=self.body()
        name=str(obj.get("name",""))
        args=obj.get("args") or {}

        result=execute_tool(name,args)

        return self.out({
          "ok":result.get("ok",False),
          "tool":name,
          "result":result,
          "trust_state":"TOOL_RESULT_OBSERVED",
          "self_certified":False
        },200 if result.get("ok") else 400)

if __name__=="__main__":
    ThreadingHTTPServer(("127.0.0.1",PORT),H).serve_forever()
