"""One-shot fixture admission controller. No production-network backend is supplied."""
from pathlib import Path
import sqlite3,json,hashlib,time,threading,re,math
ROOT=Path(__file__).resolve().parents[1]/'disposable'
class Refused(RuntimeError):pass
def integer(v):return type(v)is int and v>=0
def canonical(o):return json.dumps(o,sort_keys=True,separators=(',',':'),allow_nan=False)
def validate(c):
    fields={'authority','producer_session','receiver_session','symbols','universe_version','start_ms','end_ms','rest_requests','rest_weight','connection_attempts','subscriptions','reconnects','max_frames','max_bytes','receiver_pid','receiver_creation'}
    if set(c)!=fields:raise Refused('contract fields')
    for k in fields-{'authority','producer_session','receiver_session','symbols','universe_version'}:
        if not integer(c[k]):raise Refused('integer '+k)
    for k in ('authority','producer_session','receiver_session'):
        if not isinstance(c[k],str) or not re.fullmatch('[a-f0-9]{32}',c[k]):raise Refused('session '+k)
    if not isinstance(c['universe_version'],str) or not re.fullmatch('[a-f0-9]{64}',c['universe_version']):raise Refused('universe')
    if type(c['symbols'])is not list or not 1<=len(c['symbols'])<=2 or len(set(c['symbols']))!=len(c['symbols']) or any(s not in ('BTCUSDT','ETHUSDT') for s in c['symbols']):raise Refused('symbol allowlist')
    if not 0<c['end_ms']-c['start_ms']<=120000:raise Refused('observation duration')
    if c['connection_attempts']>4 or c['reconnects']>3 or c['subscriptions']>8 or c['rest_requests']>20 or c['rest_weight']>40 or c['max_frames']>10000 or c['max_bytes']>16777216:raise Refused('pilot ceilings')
    if not c['receiver_pid'] or not c['receiver_creation']:raise Refused('receiver identity')
class Controller:
    @classmethod
    def provision(cls,path,contract):
        validate(contract);p=Path(path).resolve()
        if ROOT not in p.parents or p.exists():raise Refused('new disposable ledger only')
        # O_EXCL reservation: startup never silently recreates a missing ledger.
        with p.open('xb'):pass
        db=sqlite3.connect(p,isolation_level=None)
        try:
            if db.execute('PRAGMA journal_mode=WAL').fetchone()[0]!='wal':raise Refused('WAL required')
            db.execute('PRAGMA synchronous=FULL')
            db.executescript('BEGIN IMMEDIATE; CREATE TABLE state(id INTEGER PRIMARY KEY CHECK(id=1),contract TEXT NOT NULL,hash TEXT NOT NULL,last_ms INTEGER NOT NULL,stopped INTEGER NOT NULL,rest INTEGER NOT NULL,weight INTEGER NOT NULL,connections INTEGER NOT NULL,subscriptions INTEGER NOT NULL,reconnects INTEGER NOT NULL,frames INTEGER NOT NULL,bytes INTEGER NOT NULL);CREATE TABLE attempts(seq INTEGER PRIMARY KEY,kind TEXT NOT NULL,details TEXT NOT NULL);')
            raw=canonical(contract);db.execute('INSERT INTO state VALUES(1,?,?,?,0,0,0,0,0,0,0,0)',(raw,hashlib.sha256(raw.encode()).hexdigest(),contract['start_ms']))
            db.execute('COMMIT')
        finally:db.close()
    def __init__(self,path,contract,clock=None,monotonic=None):
        validate(contract);self.path=Path(path).resolve()
        if ROOT not in self.path.parents or not self.path.is_file():raise Refused('existing ledger required')
        self.c=json.loads(canonical(contract));self.clock=clock or (lambda:time.time_ns()//1000000);self.mono=monotonic or time.monotonic
        self.entered=self.mono();self.entered_wall=self.clock();self.lock=threading.RLock()
        self.db=sqlite3.connect(self.path.as_uri()+'?mode=rw',uri=True,timeout=0,isolation_level=None,check_same_thread=False)
        raw,h=self.db.execute('SELECT contract,hash FROM state WHERE id=1').fetchone()
        if raw!=canonical(contract) or hashlib.sha256(raw.encode()).hexdigest()!=h:self.db.close();raise Refused('authority mismatch')
        self.db.execute('PRAGMA synchronous=FULL')
    def close(self):self.db.close()
    def stop(self,reason):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                self.db.execute('UPDATE state SET stopped=1 WHERE id=1')
                self.db.execute('INSERT INTO attempts(kind,details) VALUES(?,?)',('STOP',canonical({'reason':reason})));self.db.execute('COMMIT')
            except BaseException:
                if self.db.in_transaction:self.db.execute('ROLLBACK')
                raise
    def reserve(self,kind,*,symbol=None,limit=None,reconnect=False,bytes_count=0,count=1,producer_session=None,receiver_session=None,receiver_pid=None,receiver_creation=None):
        """Consume before dispatch; failures are never refunded. Exhaustion latches STOP."""
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                row=self.db.execute('SELECT last_ms,stopped,rest,weight,connections,subscriptions,reconnects,frames,bytes FROM state WHERE id=1').fetchone()
                now=self.clock();elapsed=self.mono()-self.entered
                def deny(why):
                    self.db.execute('UPDATE state SET stopped=1 WHERE id=1');self.db.execute('COMMIT');raise Refused(why)
                raw,digest=self.db.execute('SELECT contract,hash FROM state WHERE id=1').fetchone()
                if raw!=canonical(self.c) or hashlib.sha256(raw.encode()).hexdigest()!=digest:deny('contract changed')
                caps=[self.c[k] for k in ('rest_requests','rest_weight','connection_attempts','subscriptions','reconnects','max_frames','max_bytes')]
                if not integer(row[0]) or not self.c['start_ms']<=row[0]<=self.c['end_ms'] or type(row[1])is not int or row[1] not in (0,1) or any(not integer(v) or v>cap for v,cap in zip(row[2:],caps)):deny('corrupt ledger counters')
                if row[1]:deny('already stopped')
                if not integer(now) or not math.isfinite(elapsed) or elapsed<0 or now<row[0] or now<self.c['start_ms'] or now>=self.c['end_ms'] or elapsed*1000>=self.c['end_ms']-self.entered_wall:deny('time boundary')
                if (producer_session,receiver_session,receiver_pid,receiver_creation)!=(self.c['producer_session'],self.c['receiver_session'],self.c['receiver_pid'],self.c['receiver_creation']):deny('session/receiver custody')
                if symbol is not None and symbol not in self.c['symbols']:deny('symbol')
                used=list(row[2:]);delta=[0]*7
                if kind=='REST_METADATA':delta[:2]=[1,1]
                elif kind=='REST_KLINE':
                    if symbol is None or type(limit)is not int or not 1<=limit<=499:deny('REST page')
                    delta[:2]=[1,1 if limit<100 else 2]
                elif kind in ('WS_CONNECT','NET_CONNECT'):
                    if kind=='NET_CONNECT':
                        if reconnect is not False:deny('HTTP reconnect unsupported')
                        delta[2]=1
                    else:
                        prior_ws=self.db.execute("SELECT count(*) FROM attempts WHERE kind='WS_CONNECT'").fetchone()[0]
                        if type(reconnect)is not bool or (prior_ws>0)!=reconnect:deny('reconnect semantics')
                        delta[2]=1;delta[4]=int(reconnect)
                elif kind=='SUBSCRIBE':
                    if symbol is None or count!=1:deny('one subscription per request')
                    delta[3]=1
                elif kind=='FRAME':
                    if not integer(bytes_count) or bytes_count>16384:deny('frame bytes')
                    delta[5:]=[1,bytes_count]
                elif kind!='HEALTH':deny('unsupported operation')
                new=[a+b for a,b in zip(used,delta)]
                if any(a>b for a,b in zip(new,caps)):deny('aggregate budget exhausted')
                self.db.execute('UPDATE state SET last_ms=?,rest=?,weight=?,connections=?,subscriptions=?,reconnects=?,frames=?,bytes=? WHERE id=1',(now,*new))
                self.db.execute('INSERT INTO attempts(kind,details) VALUES(?,?)',(kind,canonical({'symbol':symbol,'limit':limit,'used':new,'time':now})))
                self.db.execute('COMMIT');return {'remaining_ms':self.c['end_ms']-now,'used':new}
            except BaseException:
                if self.db.in_transaction:self.db.execute('ROLLBACK')
                raise
