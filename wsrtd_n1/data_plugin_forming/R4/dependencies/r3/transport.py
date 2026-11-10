"""Version 2 offline receiver. No network dialing, producer launching or production writes."""
import json,hmac,hashlib,re,time,threading,struct,sqlite3
from decimal import Decimal,InvalidOperation
from pathlib import Path
MAX_FRAME=16384
MAX_SYMBOLS=1024
MAX_BUCKETS=4
TTL=5000
STATES={'SQLITE_FINALIZED':1,'LIVE_FORMING':2,'LIVE_FINALIZED_PENDING_STORAGE':3}
DEC=re.compile(r'(?:0|[1-9][0-9]{0,19})(?:\.[0-9]{1,18})?\Z')
SYMBOL=re.compile(r'[A-Z0-9]{3,30}\Z')
def canonical(o):return json.dumps(o,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def signed(event,key):
    b=canonical(event)
    if len(b)>MAX_FRAME:raise ValueError('frame limit')
    return hmac.digest(key,b,'sha256')+b
def decimal(s):
    if not isinstance(s,str) or not DEC.fullmatch(s):raise ValueError('decimal format')
    d=Decimal(s)
    if not d.is_finite() or d>Decimal('1e30'):raise ValueError('decimal range')
    return d
def envelope(raw,session,receipt_ms,identity,synthetic=True):
    """No REST/WS execution. Convert an already supplied full Binance kline event."""
    e=raw.get('data',raw); k=e['k']; s=e['s']
    if e.get('e')!='kline' or k['s']!=s or k['i']!='1m':raise ValueError('event kind/identity')
    if identity.get(s)!=('UM','PERPETUAL'):raise ValueError('unqualified contract identity')
    if e.get('st','UM')!='UM':raise ValueError('CM identity rejected')
    return dict(schema_version=2,producer_session=session,exchange='BINANCE',market_type='USD_M_PERPETUAL',
        raw_symbol=s,logical_symbol=s,interval='1m',candle_open_time_utc=k['t'],candle_close_time_utc=k['T'],
        exchange_event_time_utc=e['E'],local_receipt_time_utc=receipt_ms,
        open=k['o'],high=k['h'],low=k['l'],close=k['c'],base_volume=k['v'],
        quote_volume_if_available=k.get('q'),trade_count_if_available=k.get('n'),is_final=k['x'],
        source_event_id_if_available=None,source_type='BINANCE_KLINE_WS',
        provenance='SYNTHETIC_FIXTURE' if synthetic else 'UNQUALIFIED_CAPTURE',quality_status='UNQUALIFIED')
FIELDS=set(envelope({'e':'kline','s':'BTCUSDT','E':0,'k':{'s':'BTCUSDT','i':'1m','t':0,'T':59999,'o':'1','h':'1','l':'1','c':'1','v':'0','x':False}},'a',0,{'BTCUSDT':('UM','PERPETUAL')}))
class Receiver:
    def __init__(self,session,key,symbols,clock=None):
        if not re.fullmatch('[a-f0-9]{32}',session) or len(key)!=32:raise ValueError('custody binding')
        if not 1<=len(symbols)<=MAX_SYMBOLS or any(not SYMBOL.fullmatch(s) for s in symbols):raise ValueError('universe')
        self.session=session;self.key=key;self.symbols=frozenset(symbols);self.clock=clock or (lambda:int(time.time()*1000))
        self.lock=threading.RLock();self.buckets={};self.history={};self.connected=True;self.serial=0
        self.errors={};self.missing_finals=set();self.accepted=0;self.rejected=0;self.last_binary_state=None
    def ingest(self,packet):
        try:
            if not 32<len(packet)<=MAX_FRAME+32:raise ValueError('frame length')
            sig,b=packet[:32],packet[32:]
            if not hmac.compare_digest(sig,hmac.digest(self.key,b,'sha256')):raise ValueError('authentication')
            e=json.loads(b,object_pairs_hook=self._pairs)
            if canonical(e)!=b or set(e)!=FIELDS:raise ValueError('noncanonical/incomplete envelope')
            s=e['logical_symbol'];t=e['candle_open_time_utc'];now=self.clock()
            if e['schema_version']!=2 or type(e['schema_version']) is not int or e['producer_session']!=self.session:raise ValueError('version/session')
            if s not in self.symbols or e['raw_symbol']!=s or e['exchange']!='BINANCE' or e['market_type']!='USD_M_PERPETUAL' or e['interval']!='1m':raise ValueError('identity')
            if e['provenance']!='SYNTHETIC_FIXTURE' or e['quality_status']!='UNQUALIFIED' or e['source_type']!='BINANCE_KLINE_WS':raise ValueError('live custody not qualified')
            for f in ('candle_open_time_utc','candle_close_time_utc','exchange_event_time_utc','local_receipt_time_utc'):
                if type(e[f]) is not int or not 0<=e[f]<4102444800000:raise ValueError('timestamp range')
            if t%60000 or e['candle_close_time_utc']!=t+59999 or type(e['is_final']) is not bool:raise ValueError('bucket/finality')
            et=e['exchange_event_time_utc'];rt=e['local_receipt_time_utc']
            if et<t or et>rt+2000 or rt>now+2000 or now-rt>TTL or now-et>120000:raise ValueError('stale/future event')
            if e['is_final'] and et<t+59999:raise ValueError('premature final')
            if not e['is_final'] and t<now//60000*60000:raise ValueError('expired forming bucket')
            o,h,l,c,v=[decimal(e[f]) for f in ('open','high','low','close','base_volume')]
            if not 0<l<=min(o,c)<=max(o,c)<=h or v<0:raise ValueError('OHLCV')
            if e['quote_volume_if_available'] is not None:decimal(e['quote_volume_if_available'])
            n=e['trade_count_if_available']
            if n is not None and (type(n)is not int or not 0<=n<2**53):raise ValueError('trade count')
            if e['source_event_id_if_available'] is not None:raise ValueError('unsupported source event ID')
            with self.lock:
                if not self.connected:raise ValueError('disconnected session')
                key=(s,t);old=self.buckets.get(key)
                if old:
                    if canonical(old)==b:return 'DUPLICATE'
                    if old['is_final']:raise ValueError('final immutable')
                    if et<old['exchange_event_time_utc'] or (et==old['exchange_event_time_utc'] and not e['is_final']):raise ValueError('out of order/conflicting event')
                    if o!=decimal(old['open']) or h<decimal(old['high']) or l>decimal(old['low']) or v<decimal(old['base_volume']):raise ValueError('cumulative regression')
                else:
                    count=sum(k[0]==s for k in self.buckets)
                    if count>=MAX_BUCKETS:raise ValueError('backpressure: pending buckets retained')
                hist=self.history.get(key)
                if hist and self.values(e)!=hist:raise ValueError('SQLite conflict')
                for k,prior in self.buckets.items():
                    if k[0]==s and k[1]<t and not prior['is_final']:self.missing_finals.add(k)
                self.buckets[key]=e
                if e['is_final']:self.missing_finals.discard(key)
                self.serial+=1;self.accepted+=1;self.errors.pop(s,None)
                return 'ACCEPTED'
        except (ValueError,KeyError,TypeError,InvalidOperation,json.JSONDecodeError,RecursionError) as exc:
            self.rejected+=1
            # Invalid events never replace good state; record an explicit failure.
            with self.lock:self.errors['last']=str(exc)
            return 'INVALID:'+str(exc)
    @staticmethod
    def _pairs(pairs):
        d={}
        for k,v in pairs:
            if k in d:raise ValueError('duplicate JSON key')
            d[k]=v
        return d
    @staticmethod
    def values(e):return tuple(decimal(e[f]) for f in ('open','high','low','close','base_volume'))
    def disconnect(self):
        with self.lock:self.connected=False;self.serial+=1
    def load_history(self,path,dbkey):
        p=Path(path).resolve();root=Path(__file__).parent.resolve()/'disposable'
        if root not in p.parents:raise ValueError('disposable only')
        db=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)
        try:
            db.execute('PRAGMA query_only=ON')
            if db.execute('PRAGMA user_version').fetchone()[0]!=2 or db.execute('PRAGMA application_id').fetchone()[0]!=1465074229:raise ValueError('SQLite identity')
            if db.execute('SELECT database_id FROM database_context').fetchall()!=[(dbkey,)]:raise ValueError('database scope')
            rows=db.execute('SELECT symbol,ts_ms,o,h,l,c,v FROM bars WHERE database_id=? AND interval=? AND finalized=1 ORDER BY symbol,ts_ms',(dbkey,'1m')).fetchmany(65537)
            if len(rows)>65536:raise ValueError('history admission limit')
            result={}
            for s,t,*vals in rows:
                if s not in self.symbols or type(t)is not int or t%60000:raise ValueError('history identity')
                vals=tuple(decimal(str(v)) for v in vals);o,h,l,c,v=vals
                if not 0<l<=min(o,c)<=max(o,c)<=h or v<0:raise ValueError('history OHLCV')
                if (s,t) in result:raise ValueError('duplicate history')
                result[s,t]=vals
            with self.lock:
                for k,v in self.history.items():
                    if k not in result or result[k]!=v:raise ValueError('immutable historical regression')
                for k,e in self.buckets.items():
                    if k in result and self.values(e)!=result[k]:raise ValueError('history/live conflict')
                self.history=result
                for k in list(self.buckets):
                    if k in result and self.buckets[k]['is_final']:del self.buckets[k]
                self.serial+=1
        finally:db.close()
    def snapshot(self):
        now=self.clock()
        with self.lock:
            out={k:(v,'SQLITE_FINALIZED') for k,v in self.history.items()};statuses={s:'MISSING' for s in self.symbols}
            for s,t in self.history:statuses[s]='SQLITE_FINALIZED'
            for k,e in self.buckets.items():
                if e['is_final']:
                    if k not in out:out[k]=(self.values(e),'LIVE_FINALIZED_PENDING_STORAGE')
                    if statuses[k[0]]!='LIVE_FORMING':statuses[k[0]]='LIVE_FINALIZED_PENDING_STORAGE'
                elif not self.connected or now-e['local_receipt_time_utc']>TTL or k[1]!=now//60000*60000:statuses[k[0]]='STALE';continue
                elif k not in out:out[k]=(self.values(e),'LIVE_FORMING');statuses[k[0]]='LIVE_FORMING'
            return out,statuses
    def status(self):
        with self.lock:
            return {'connected':self.connected,'symbol_states':self.snapshot()[1],
                    'invalid_events':dict(self.errors),'missing_final_buckets':sorted(self.missing_finals),
                    'full_prefix_complete':False,'provenance':'SYNTHETIC_FIXTURE',
                    'native_history_readback_proven':False}
    def binary(self,dbkey):
        with self.lock:
            rows,status=self.snapshot()
            if len(rows)>65536:raise ValueError('snapshot limit')
            # Header and records explicitly little-endian packed. Synthetic custody only.
            data=[]
            for (s,t),(v,state) in sorted(rows.items()):
                data.append(struct.pack('<32sQ5dII',s.encode(),t,*map(float,v),STATES[state],0))
            payload=b''.join(data)
            state=(self.connected,payload)
            if self.last_binary_state!=state:self.serial+=1;self.last_binary_state=state
            header=struct.pack('<IIIIQQ64s80s',0x32434E57,2,len(rows),int(self.connected),self.serial,self.clock(),self.session.encode(),dbkey.encode())
            return header+payload
