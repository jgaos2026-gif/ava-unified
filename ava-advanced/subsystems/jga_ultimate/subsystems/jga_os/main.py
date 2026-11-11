from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
import json, sqlite3, hashlib, uuid, secrets, threading, webbrowser, hmac, ast, operator
from datetime import datetime, timezone, timedelta

ROOT=Path(__file__).resolve().parent
DB=ROOT/'data'/'jga.sqlite3'; CFG=ROOT/'config.json'
DEFAULT={'host':'127.0.0.1','port':8765,'owner_pin':'246810','deposit_percent':35,'final_percent':65,'commission_percent':25,'retention_years':7}
if not CFG.exists(): CFG.write_text(json.dumps(DEFAULT,indent=2))
CONFIG=DEFAULT|json.loads(CFG.read_text())
if CONFIG['deposit_percent']+CONFIG['final_percent']!=100: raise RuntimeError('Deposit/final percentages must total 100')
STATES='AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC PR GU'.split()
SESSIONS=set(); SCHEMA='''
CREATE TABLE IF NOT EXISTS clients(id TEXT PRIMARY KEY,name TEXT NOT NULL,email TEXT,phone TEXT,state TEXT NOT NULL,notes TEXT,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS leads(id TEXT PRIMARY KEY,source TEXT NOT NULL,name TEXT,contact TEXT,state TEXT,status TEXT NOT NULL,notes TEXT,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS quotes(id TEXT PRIMARY KEY,client_id TEXT NOT NULL,description TEXT NOT NULL,service_cents INTEGER NOT NULL,tax_cents INTEGER NOT NULL,total_cents INTEGER NOT NULL,status TEXT NOT NULL,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,quote_id TEXT NOT NULL,client_id TEXT NOT NULL,status TEXT NOT NULL,deposit_cleared INTEGER NOT NULL DEFAULT 0,final_cleared INTEGER NOT NULL DEFAULT 0,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS payments(id TEXT PRIMARY KEY,job_id TEXT NOT NULL,kind TEXT NOT NULL,amount_cents INTEGER NOT NULL,provider_ref TEXT NOT NULL,verified_by TEXT NOT NULL,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS contractors(id TEXT PRIMARY KEY,name TEXT NOT NULL,email TEXT,state TEXT NOT NULL,status TEXT NOT NULL,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS commissions(id TEXT PRIMARY KEY,contractor_id TEXT NOT NULL,job_id TEXT NOT NULL,net_cents INTEGER NOT NULL,commission_cents INTEGER NOT NULL,status TEXT NOT NULL,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY,jurisdiction TEXT NOT NULL,category TEXT NOT NULL,related_id TEXT,description TEXT NOT NULL,retain_until TEXT NOT NULL,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT UNIQUE NOT NULL,event_type TEXT NOT NULL,entity TEXT NOT NULL,entity_id TEXT NOT NULL,payload TEXT NOT NULL,created TEXT NOT NULL,prev_hash TEXT NOT NULL,event_hash TEXT NOT NULL);
'''
def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def connect():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA foreign_keys=ON'); c.executescript(SCHEMA); return c
def audit(kind,entity,eid,payload):
    c=connect()
    try:
        row=c.execute('SELECT event_hash FROM events ORDER BY seq DESC LIMIT 1').fetchone(); prev=row['event_hash'] if row else '0'*64
        body={'event_id':str(uuid.uuid4()),'event_type':kind,'entity':entity,'entity_id':eid,'payload':payload,'created':now(),'prev_hash':prev}
        digest=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        c.execute('INSERT INTO events(event_id,event_type,entity,entity_id,payload,created,prev_hash,event_hash) VALUES(?,?,?,?,?,?,?,?)',(body['event_id'],kind,entity,eid,json.dumps(payload,sort_keys=True),body['created'],prev,digest)); c.commit()
    finally:c.close()
def verify_ledger():
    c=connect(); prev='0'*64; rows=c.execute('SELECT * FROM events ORDER BY seq').fetchall()
    for r in rows:
        body={'event_id':r['event_id'],'event_type':r['event_type'],'entity':r['entity'],'entity_id':r['entity_id'],'payload':json.loads(r['payload']),'created':r['created'],'prev_hash':r['prev_hash']}
        digest=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if r['prev_hash']!=prev or r['event_hash']!=digest: c.close(); return {'valid':False,'failed_sequence':r['seq'],'checked':r['seq']}
        prev=digest
    c.close(); return {'valid':True,'checked':len(rows),'head':prev}
def uid(): return str(uuid.uuid4())
def cents(x): return round(float(x)*100)
def require_state(s):
    s=(s or '').upper()
    if s not in STATES: raise ValueError('Use a valid state/territory code.')
    return s
def add_client(d):
    if not d.get('name','').strip(): raise ValueError('Client name required')
    state=require_state(d.get('state')); i=uid(); c=connect(); c.execute('INSERT INTO clients VALUES(?,?,?,?,?,?,?)',(i,d['name'].strip(),d.get('email',''),d.get('phone',''),state,d.get('notes',''),now())); c.commit(); c.close(); audit('client.created','client',i,{'state':state}); return {'id':i}
def add_lead(d):
    if not d.get('name','').strip(): raise ValueError('Lead name required')
    state=require_state(d.get('state')); i=uid(); c=connect(); c.execute('INSERT INTO leads VALUES(?,?,?,?,?,?,?,?)',(i,d.get('source','owner'),d['name'],d.get('contact',''),state,'new',d.get('notes',''),now())); c.commit(); c.close(); audit('lead.created','lead',i,{'source':d.get('source','owner'),'state':state}); return {'id':i}
def add_quote(d):
    c=connect(); client=c.execute('SELECT id FROM clients WHERE id=?',(d.get('client_id'),)).fetchone(); c.close()
    if not client: raise ValueError('Client not found')
    service=cents(d.get('service',0)); tax=cents(d.get('tax',0))
    if service<=0 or tax<0: raise ValueError('Service must be positive; tax cannot be negative')
    i=uid(); total=service+tax; c=connect(); c.execute('INSERT INTO quotes VALUES(?,?,?,?,?,?,?,?)',(i,d['client_id'],d['description'],service,tax,total,'approved_pending_deposit',now())); c.commit(); c.close(); audit('quote.created','quote',i,{'client_id':d['client_id'],'total_cents':total}); return {'id':i,'total_cents':total}
def add_job(d):
    c=connect(); q=c.execute('SELECT * FROM quotes WHERE id=?',(d.get('quote_id'),)).fetchone()
    if not q: c.close(); raise ValueError('Quote not found')
    i=uid(); c.execute('INSERT INTO jobs(id,quote_id,client_id,status,created) VALUES(?,?,?,?,?)',(i,q['id'],q['client_id'],'awaiting_deposit',now())); c.commit(); c.close(); audit('job.created','job',i,{'quote_id':q['id']}); return {'id':i}
def record_payment(d):
    kind=d.get('kind'); ref=d.get('provider_ref','').strip(); verifier=d.get('verified_by','').strip()
    if kind not in ('deposit','final') or not ref or not verifier: raise ValueError('Payment type, real provider transaction reference and verifier required')
    c=connect(); j=c.execute('SELECT j.*,q.total_cents FROM jobs j JOIN quotes q ON q.id=j.quote_id WHERE j.id=?',(d.get('job_id'),)).fetchone()
    if not j: c.close(); raise ValueError('Job not found')
    if kind=='deposit':
        if j['deposit_cleared']: c.close(); raise ValueError('Deposit already recorded')
        amount=round(j['total_cents']*CONFIG['deposit_percent']/100); c.execute("UPDATE jobs SET deposit_cleared=1,status='ready_for_production' WHERE id=?",(j['id'],))
    else:
        if not j['deposit_cleared']: c.close(); raise ValueError('Deposit must clear first')
        if j['final_cleared']: c.close(); raise ValueError('Final payment already recorded')
        amount=j['total_cents']-round(j['total_cents']*CONFIG['deposit_percent']/100); c.execute("UPDATE jobs SET final_cleared=1,status='ready_for_delivery' WHERE id=?",(j['id'],))
    i=uid(); c.execute('INSERT INTO payments VALUES(?,?,?,?,?,?,?)',(i,j['id'],kind,amount,ref,verifier,now())); c.commit(); c.close(); audit('payment.manually_verified','payment',i,{'job_id':j['id'],'kind':kind,'amount_cents':amount,'provider_ref':ref}); return {'id':i,'amount_cents':amount,'status':'recorded'}
def set_job_status(d):
    allowed={'in_production','quality_review','revision','completed'}
    if d.get('status') not in allowed: raise ValueError('Unsupported status')
    c=connect(); j=c.execute('SELECT * FROM jobs WHERE id=?',(d.get('job_id'),)).fetchone()
    if not j: c.close(); raise ValueError('Job not found')
    if not j['deposit_cleared']: c.close(); raise ValueError('VERA BLOCK: deposit not cleared')
    if d['status']=='completed' and not j['final_cleared']: c.close(); raise ValueError('VERA BLOCK: final payment not cleared')
    c.execute('UPDATE jobs SET status=? WHERE id=?',(d['status'],j['id'])); c.commit(); c.close(); audit('job.status_changed','job',j['id'],{'status':d['status']}); return {'status':d['status']}
def add_contractor(d):
    if not d.get('name','').strip(): raise ValueError('Contractor name required')
    state=require_state(d.get('state')); i=uid(); c=connect(); c.execute('INSERT INTO contractors VALUES(?,?,?,?,?,?)',(i,d['name'],d.get('email',''),state,'pending_review',now())); c.commit(); c.close(); audit('contractor.created','contractor',i,{'state':state}); return {'id':i,'status':'pending_review'}
def commission(d):
    c=connect(); ct=c.execute('SELECT id FROM contractors WHERE id=?',(d.get('contractor_id'),)).fetchone(); j=c.execute('SELECT * FROM jobs WHERE id=?',(d.get('job_id'),)).fetchone()
    if not ct or not j or not j['deposit_cleared']: c.close(); raise ValueError('Contractor/job missing or deposit not cleared')
    net=cents(d.get('net_service',0));
    if net<=0: c.close(); raise ValueError('Net service amount must be positive')
    amount=round(net*CONFIG['commission_percent']/100); i=uid(); c.execute('INSERT INTO commissions VALUES(?,?,?,?,?,?,?)',(i,ct['id'],j['id'],net,amount,'held_pending_policy_review',now())); c.commit(); c.close(); audit('commission.calculated','commission',i,{'commission_cents':amount,'status':'held_pending_policy_review'}); return {'id':i,'commission_cents':amount,'status':'held_pending_policy_review'}
def add_record(d):
    state=require_state(d.get('jurisdiction')); cat=d.get('category','').strip(); desc=d.get('description','').strip()
    if not cat or len(desc)<5: raise ValueError('Category and meaningful description required')
    i=uid(); until=(datetime.now(timezone.utc)+timedelta(days=365*int(CONFIG['retention_years']))).date().isoformat(); c=connect(); c.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?)',(i,state,cat,d.get('related_id',''),desc,until,now())); c.commit(); c.close(); audit('record.created','record',i,{'jurisdiction':state,'retain_until':until}); return {'id':i,'retain_until':until}
def dashboard():
    c=connect(); counts={k:c.execute(q).fetchone()[0] for k,q in {'clients':'SELECT COUNT(*) FROM clients','leads':'SELECT COUNT(*) FROM leads','quotes':'SELECT COUNT(*) FROM quotes','jobs':'SELECT COUNT(*) FROM jobs','awaiting_deposit':'SELECT COUNT(*) FROM jobs WHERE deposit_cleared=0','production_jobs':'SELECT COUNT(*) FROM jobs WHERE deposit_cleared=1 AND final_cleared=0','delivery_ready':'SELECT COUNT(*) FROM jobs WHERE final_cleared=1','contractors':'SELECT COUNT(*) FROM contractors','records':'SELECT COUNT(*) FROM records','events':'SELECT COUNT(*) FROM events'}.items()}
    counts['recent_clients']=[dict(x) for x in c.execute('SELECT * FROM clients ORDER BY created DESC LIMIT 8')]; counts['recent_jobs']=[dict(x) for x in c.execute('SELECT j.*,q.description,q.total_cents,cl.name client_name FROM jobs j JOIN quotes q ON q.id=j.quote_id JOIN clients cl ON cl.id=j.client_id ORDER BY j.created DESC LIMIT 8')]; c.close(); counts['ledger']=verify_ledger(); return counts
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def sendj(self,obj,status=200):
        b=json.dumps(obj,default=str).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(b))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(b)
    def readbody(self):
        n=int(self.headers.get('Content-Length','0'))
        if n>1_000_000: raise ValueError('Request too large')
        return json.loads(self.rfile.read(n) or b'{}')
    def authenticated(self):
        token=self.headers.get('Cookie','').split('jga=',1)[-1].split(';')[0]; return token in SESSIONS
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/': self.serve(ROOT/'ui'/'index.html','text/html'); return
        if path in ('/assets/app.js','/assets/style.css'):
            f=ROOT/'ui'/path.split('/')[-1]; self.serve(f,'text/javascript' if f.suffix=='.js' else 'text/css'); return
        if path=='/api/session': self.sendj({'authenticated':self.authenticated()}); return
        if path=='/api/states': self.sendj(STATES); return
        if not self.authenticated(): self.sendj({'error':'Owner login required'},401); return
        if path=='/api/dashboard': self.sendj(dashboard()); return
        if path=='/api/ava/ledger': self.sendj({'ledger':verify_ledger()}); return
        if path=='/api/ledger': self.sendj(verify_ledger()); return
        self.sendj({'error':'Not found'},404)
    def serve(self,f,typ):
        b=f.read_bytes(); self.send_response(200); self.send_header('Content-Type',typ); self.send_header('Content-Length',str(len(b))); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(b)
    def do_POST(self):
        path=urlparse(self.path).path
        try:
            d=self.readbody()
            if path=='/api/login':
                if not hmac.compare_digest(str(d.get('pin','')),str(CONFIG['owner_pin'])): self.sendj({'error':'Incorrect PIN'},403); return
                token=secrets.token_urlsafe(32); SESSIONS.add(token); self.send_response(200); self.send_header('Set-Cookie',f'jga={token}; HttpOnly; SameSite=Strict; Path=/'); self.end_headers(); return
            if path=='/api/logout': SESSIONS.clear(); self.send_response(200); self.send_header('Set-Cookie','jga=; Max-Age=0; Path=/'); self.end_headers(); return
            if not self.authenticated(): self.sendj({'error':'Owner login required'},401); return
            routes={'/api/clients':add_client,'/api/leads':add_lead,'/api/quotes':add_quote,'/api/jobs':add_job,'/api/payments':record_payment,'/api/job-status':set_job_status,'/api/contractors':add_contractor,'/api/commissions':commission,'/api/records':add_record}
            if path in routes: self.sendj(routes[path](d),201); return
            if path=='/api/assistant': self.sendj(assistant(d.get('message',''))); return
            if path=='/api/ava/process': self.sendj(ava_process(d.get('message',''))); return
            if path=='/api/proof':
                report={'generated':now(),'dashboard':dashboard(),'scope':'Local database snapshot and hash-chain check only; not external certification.'}; raw=json.dumps(report,sort_keys=True,indent=2); report['sha256']=hashlib.sha256(raw.encode()).hexdigest(); f=ROOT/'proof_reports'/('proof_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.json'); f.write_text(json.dumps(report,indent=2)); self.sendj({'file':str(f.relative_to(ROOT)),'sha256':report['sha256']},201); return
            self.sendj({'error':'Not found'},404)
        except (ValueError,KeyError,TypeError) as e: self.sendj({'error':str(e)},400)
        except Exception as e: self.sendj({'error':'Internal error: '+str(e)},500)
# AVA Sovereign Core: honest local screening + deterministic routing.
# No embedding model, LLM, dual-model assurance, or autonomous tool execution is claimed here.
_ALLOWED_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
def safe_calculate(expression):
    if len(expression) > 120: raise ValueError('Calculator expression too long')
    tree = ast.parse(expression, mode='eval')
    def visit(node, depth=0):
        if depth > 20: raise ValueError('Calculator expression too complex')
        if isinstance(node, ast.Expression): return visit(node.body, depth+1)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float): return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            v=visit(node.operand, depth+1); return v if isinstance(node.op, ast.UAdd) else -v
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
            a,b=visit(node.left,depth+1),visit(node.right,depth+1)
            if isinstance(node.op, ast.Pow) and abs(b)>8: raise ValueError('Exponent limit exceeded')
            result=_ALLOWED_BINOPS[type(node.op)](a,b)
            if abs(result)>1e15: raise ValueError('Calculator result limit exceeded')
            return result
        raise ValueError('Unsupported calculator syntax')
    result=visit(tree)
    if isinstance(result,float) and not __import__('math').isfinite(result): raise ValueError('Non-finite result')
    return result
def ava_process(message):
    if not isinstance(message,str) or not message.strip(): raise ValueError('Input cannot be empty')
    if len(message)>4000: raise ValueError('Input exceeds 4000 characters')
    if '\x00' in message:
        audit('ava.input_quarantined','ava','screening',{'reason':'null_byte','length':len(message)})
        return {'accepted':False,'stage':'SB-688','status':'QUARANTINED','reason':'Null byte detected. Input was not routed.'}
    lowered=message.lower()
    # Tool-shaped JSON is never executed just because a user supplied it.
    if 'tool_call' in lowered or 'ignore previous instructions' in lowered or 'system prompt' in lowered:
        audit('ava.input_blocked','ava','screening',{'reason':'untrusted_tool_or_instruction_payload','length':len(message)})
        return {'accepted':False,'stage':'VERA','status':'BLOCKED','reason':'Untrusted tool/instruction payload blocked. No tool was executed.'}
    result={'accepted':True,'status':'SCREENED','agent':'AVA','response':'Input passed basic boundary screening. No connected language model is configured.'}
    if 'calculator' in lowered or lowered.startswith('math:'):
        expr=message.split(':',1)[1].strip() if lowered.startswith('math:') else message.lower().split('calculator',1)[1].strip().lstrip('for: =')
        try:
            value=safe_calculate(expr)
            result.update({'agent':'AVA / CALCULATOR','status':'COMPLETED','response':f'{expr} = {value}','tool_result':{'tool':'safe_calculator','result':value}})
        except Exception as e:
            result.update({'status':'NEEDS_CLARIFICATION','response':f'Calculator did not run: {e}'})
    elif any(k in lowered for k in ('ledger','audit','verify','proof')):
        result.update({'agent':'VERA','status':'COMPLETED','response':'Local hash-chain verification completed.','verification':verify_ledger()})
    elif any(k in lowered for k in ('status','dashboard','health')):
        result.update({'agent':'AVA','status':'COMPLETED','response':'Local JGA operations snapshot.','dashboard':dashboard()})
    audit('ava.pipeline_processed','ava','pipeline',{'agent':result['agent'],'status':result['status'],'input_sha256':hashlib.sha256(message.encode()).hexdigest()})
    result['ledger']=verify_ledger()
    return result

def assistant(message):
    m=message.lower()
    if any(x in m for x in ('status','dashboard','health')): return {'agent':'AVA','answer':'Owner operations snapshot','data':dashboard()}
    if any(x in m for x in ('verify','ledger','audit','proof')): return {'agent':'VERA','answer':'Hash-chain verification result','data':verify_ledger()}
    if any(x in m for x in ('strategy','decision','should i','forecast')): return {'agent':'ORION','answer':'Decision framework: estimate probability and payoff; model best, base and worst cases; trace first-, second- and third-order effects; assess cash, reputation, operational load and reversibility; update estimates from measured outcomes. Provide actual figures for a numeric expected-value model.'}
    if any(x in m for x in ('tax','1099','nexus','sales tax')): return {'agent':'TAX AI','answer':'This build stores jurisdiction-tagged evidence only. It does not determine nexus, taxability, rates, filing deadlines or submit returns. Validate against current official rules and a qualified tax professional.'}
    return {'agent':'AVA','answer':'I can summarize the local dashboard, verify the event ledger, explain workflow gates, or help structure an owner decision. This initial assistant uses deterministic rules, not a connected language model.'}
if __name__=='__main__':
    connect().close()
    for d in ('proof_reports','quarantine','recovery','logs'): (ROOT/d).mkdir(exist_ok=True)
    url=f"http://{CONFIG['host']}:{CONFIG['port']}"; print(f"JGA Enterprise OS local server: {url}\nFirst-run owner PIN: {CONFIG['owner_pin']} (change config.json immediately)\nCtrl+C to stop")
    threading.Timer(1,lambda:webbrowser.open(url)).start(); ThreadingHTTPServer((CONFIG['host'],int(CONFIG['port'])),Handler).serve_forever()
