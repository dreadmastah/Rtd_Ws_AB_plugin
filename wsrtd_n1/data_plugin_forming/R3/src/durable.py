"""R3 disposable transactional finalization. No production admission authority."""
from pathlib import Path
import sqlite3,json,hashlib,os
from decimal import Decimal,localcontext
ROOT=Path(__file__).resolve().parents[1]/'disposable'
def exact(s):
    # String operation only: Decimal.normalize() rounds at the active context precision.
    v=format(Decimal(s),'f')
    return v.rstrip('0').rstrip('.') if '.' in v else v
class Store:
    def __init__(self,path,scope):
        p=Path(path).resolve()
        if ROOT not in p.parents or not scope:raise ValueError('disposable scope required')
        if any(a.is_symlink() for a in (p,*p.parents)):raise ValueError('symlink')
        self.path=p;self.scope=scope
        if p.exists():
            check=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True,timeout=0)
            try:
                if check.execute('SELECT scope FROM context').fetchall()!=[(scope,)]:raise ValueError('scope mismatch')
                if check.execute('PRAGMA application_id').fetchone()[0]!=1465074227 or check.execute('PRAGMA user_version').fetchone()[0]!=3:raise ValueError('schema identity')
            finally:check.close()
        self.db=sqlite3.connect(p,timeout=0,isolation_level=None)
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS context(scope TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS owner(singleton INTEGER PRIMARY KEY CHECK(singleton=1),generation INTEGER NOT NULL,session TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS finals(symbol TEXT NOT NULL,minute INTEGER NOT NULL,interval TEXT NOT NULL,values_json TEXT NOT NULL,source TEXT NOT NULL,event_json TEXT NOT NULL,event_hash TEXT NOT NULL,generation INTEGER NOT NULL,receipt_required INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(symbol,minute,interval));
CREATE TABLE IF NOT EXISTS checkpoint(symbol TEXT PRIMARY KEY,last_committed INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS receipts(event_hash TEXT PRIMARY KEY,envelope_json TEXT NOT NULL,envelope_hash TEXT NOT NULL);
''')
        rows=self.db.execute('SELECT scope FROM context').fetchall()
        if not rows:
            self.db.execute('INSERT INTO context VALUES(?)',(scope,))
            self.db.execute('PRAGMA application_id=1465074227');self.db.execute('PRAGMA user_version=3')
        elif rows!=[(scope,)]:self.db.close();raise ValueError('scope mismatch')
    def close(self):self.db.close()
    def claim(self,session):
        if len(session)!=32 or any(c not in '0123456789abcdef' for c in session):raise ValueError('session')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            prior=self.db.execute('SELECT generation FROM owner WHERE singleton=1').fetchone();g=1 if prior is None else prior[0]+1
            self.db.execute('INSERT OR REPLACE INTO owner VALUES(1,?,?)',(g,session));self.db.execute('COMMIT');return g
        except BaseException:self.db.execute('ROLLBACK');raise
    def commit(self,e,generation,session,crash=None,envelope=None):
        # Admission must be performed in the receiver; independently validate fields here too.
        from transport import Receiver,signed
        if e['producer_session']!=session or e['is_final'] is not True:raise ValueError('unqualified final')
        if e.get('provenance')!='SYNTHETIC_FIXTURE':raise ValueError('genuine custody verifier unavailable')
        now=e['local_receipt_time_utc'];key=b'x'*32
        verifier=Receiver(session,key,[e['logical_symbol']],lambda:now)
        if verifier.ingest(signed(e,key))!='ACCEPTED':raise ValueError('invalid finalized event')
        symbol=e['logical_symbol'];minute=e['candle_open_time_utc'];values=json.dumps([exact(e[k]) for k in ('open','high','low','close','base_volume')])
        raw=json.dumps(e,sort_keys=True,separators=(',',':'));digest=hashlib.sha256(raw.encode()).hexdigest()
        receipt=None
        if envelope is not None:
            if envelope.get('schema_version')!=3 or envelope.get('candle')!=e:raise ValueError('envelope linkage')
            from transport import envelope as reconstruct
            original=reconstruct(envelope['source_event'],session,e['local_receipt_time_utc'],{symbol:('UM','PERPETUAL')})
            if original!=e:raise ValueError('source event linkage')
            receipt=json.dumps(envelope,sort_keys=True,separators=(',',':'))
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if self.db.execute('SELECT generation,session FROM owner WHERE singleton=1').fetchone()!=(generation,session):raise ValueError('stale writer epoch')
            prior=self.db.execute('SELECT values_json,source,receipt_required,event_hash FROM finals WHERE symbol=? AND minute=? AND interval=?',(symbol,minute,'1m')).fetchone()
            if prior:
                if prior[:2]!=(values,'SYNTHETIC_FIXTURE'):raise ValueError('immutable final conflict')
                if envelope is not None and (not prior[2] or not self.db.execute('SELECT 1 FROM receipts WHERE event_hash=?',(prior[3],)).fetchone()):raise ValueError('missing original integrated receipt')
                result='IDEMPOTENT'
            else:
                self.db.execute('INSERT INTO finals VALUES(?,?,?,?,?,?,?,?,?)',(symbol,minute,'1m',values,'SYNTHETIC_FIXTURE',raw,digest,generation,int(envelope is not None)));result='COMMITTED'
            if receipt is not None and result=='COMMITTED':self.db.execute('INSERT INTO receipts VALUES(?,?,?)',(digest,receipt,hashlib.sha256(receipt.encode()).hexdigest()))
            self.db.execute('INSERT INTO checkpoint VALUES(?,?) ON CONFLICT(symbol) DO UPDATE SET last_committed=max(last_committed,excluded.last_committed)',(symbol,minute))
            if crash=='before':os._exit(71)
            self.db.execute('COMMIT')
            if crash=='after':os._exit(72)
            return result
        except BaseException:
            if self.db.in_transaction:self.db.execute('ROLLBACK')
            raise
    def rows(self,symbol,require_receipt=False):
        records=self.db.execute('SELECT minute,values_json,source,event_hash,event_json,interval,receipt_required FROM finals WHERE symbol=? ORDER BY minute',(symbol,)).fetchmany(600001)
        if len(records)>600000:raise ValueError('history read admission limit')
        result=[]
        for minute,values,source,digest,raw,interval,required in records:
            e=json.loads(raw)
            if hashlib.sha256(raw.encode()).hexdigest()!=digest or e['logical_symbol']!=symbol or e['candle_open_time_utc']!=minute or interval!='1m' or e['is_final'] is not True or source!=e['provenance']:raise ValueError('ledger linkage')
            if json.loads(values)!=[exact(e[k]) for k in ('open','high','low','close','base_volume')]:raise ValueError('ledger values')
            receipt=self.db.execute('SELECT envelope_json,envelope_hash FROM receipts WHERE event_hash=?',(digest,)).fetchone()
            if (required or require_receipt) and not receipt:raise ValueError('missing required V3 receipt')
            if receipt:
                full,fullhash=receipt
                if hashlib.sha256(full.encode()).hexdigest()!=fullhash or json.loads(full)['candle']!=e:raise ValueError('envelope ledger linkage')
            result.append((minute,values,source,digest))
        return result
    def coverage(self,symbol,listing,cutoff):
        start=((listing+59999)//60000)*60000
        if cutoff%60000 or cutoff<start:raise ValueError('cutoff')
        rows=self.rows(symbol);minutes=[r[0] for r in rows if start<=r[0]<cutoff]
        expected=(cutoff-start)//60000
        structural=len(minutes)==expected and all(t==start+i*60000 for i,t in enumerate(minutes))
        return {'structural_complete':structural,'expected_minutes':expected,'observed_minutes':len(minutes),
                'verified_provenance':False,'full_prefix_qualified':False,'live_ready':False,
                'reason':'Synthetic ledger cannot establish archive/REST/WS custody; bootstrap require_r3_admission remains denied'}
    def daily(self,symbol,day):
        if day%86400000:raise ValueError('UTC day boundary')
        rows=[r for r in self.rows(symbol) if day<=r[0]<day+86400000]
        if len(rows)!=1440 or any(r[0]!=day+i*60000 for i,r in enumerate(rows)):return None
        values=[list(map(Decimal,json.loads(r[1]))) for r in rows]
        with localcontext() as ctx:
            ctx.prec=64
            return (values[0][0],max(v[1] for v in values),min(v[2] for v in values),values[-1][3],sum(v[4] for v in values))
