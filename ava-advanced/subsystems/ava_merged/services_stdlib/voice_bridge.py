import asyncio,json,os,tempfile,urllib.parse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

PORT=8772
ROOT=os.path.dirname(os.path.abspath(__file__))
LOG=os.path.join(ROOT,"AVA_VISIBLE_COGNITION.jsonl")
VOICE="en-US-AriaNeural"

def cors(h):
    h.send_header("Access-Control-Allow-Origin","*")
    h.send_header("Access-Control-Allow-Headers","Content-Type")
    h.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")

class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass

    def do_OPTIONS(self):
        self.send_response(204);cors(self);self.end_headers()

    def json_out(self,obj,status=200):
        b=json.dumps(obj).encode("utf-8")
        self.send_response(status);cors(self)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(b)))
        self.end_headers();self.wfile.write(b)

    def do_GET(self):
        u=urllib.parse.urlparse(self.path)
        q=urllib.parse.parse_qs(u.query)

        if u.path=="/health":
            return self.json_out({"ok":True,"voice":VOICE,"mode":"NEURAL_FEMALE","visible_cognition_log":LOG})

        if u.path=="/thoughts":
            rows=[]
            try:
                with open(LOG,"r",encoding="utf-8") as f:
                    for line in f.readlines()[-100:]:
                        try: rows.append(json.loads(line))
                        except: pass
            except: pass
            return self.json_out({"events":rows})

        if u.path=="/speak":
            text=q.get("text",[""])[0].strip()[:1500]
            if not text:return self.json_out({"error":"text required"},400)
            try:
                import edge_tts
                fd,path=tempfile.mkstemp(suffix=".mp3")
                os.close(fd)
                async def make():
                    c=edge_tts.Communicate(text,VOICE,rate="+4%",pitch="+0Hz")
                    await c.save(path)
                asyncio.run(make())
                with open(path,"rb") as f:b=f.read()
                try:os.unlink(path)
                except:pass
                self.send_response(200);cors(self)
                self.send_header("Content-Type","audio/mpeg")
                self.send_header("Cache-Control","no-store")
                self.send_header("Content-Length",str(len(b)))
                self.end_headers();self.wfile.write(b);return
            except Exception as e:
                return self.json_out({"error":str(e),"fallback":"browser_voice"},503)

        self.json_out({"error":"not found"},404)

    def do_POST(self):
        u=urllib.parse.urlparse(self.path)
        if u.path!="/thoughts":return self.json_out({"error":"not found"},404)
        try:
            n=int(self.headers.get("Content-Length","0"))
            obj=json.loads(self.rfile.read(n).decode("utf-8"))
            entry={
                "timestamp":obj.get("timestamp"),
                "type":obj.get("type","VISIBLE_ACTIVITY"),
                "text":str(obj.get("text",""))[:4000],
                "source":"AVA_VISIBLE_COGNITION",
                "claim":"APPLICATION_EVENT_NOT_HIDDEN_CHAIN_OF_THOUGHT"
            }
            with open(LOG,"a",encoding="utf-8") as f:
                f.write(json.dumps(entry,ensure_ascii=False)+"\n")
            return self.json_out({"ok":True})
        except Exception as e:return self.json_out({"error":str(e)},400)

if __name__=="__main__":
    ThreadingHTTPServer(("127.0.0.1",PORT),H).serve_forever()
