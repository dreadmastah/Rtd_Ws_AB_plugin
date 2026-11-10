"""Versioned offline sender/receiver and durable handoff. Never dials a feed."""
import json,hmac,hashlib,struct,time,threading
from transport import Receiver,envelope,signed,canonical
class Budget:
    """Fail-closed aggregate admission, not a real shared-IP reservation."""
    def __init__(self,symbols,request_limit,weight_limit,deadline_ms,clock):
        if not 1<=len(symbols)<=2 or any(type(x)is not int or x<0 for x in (request_limit,weight_limit,deadline_ms)):raise ValueError('pilot limits')
        self.lock=threading.Lock()
        self.symbols=frozenset(symbols);self.requests=request_limit;self.weight=weight_limit;self.deadline=deadline_ms;self.clock=clock
    def reserve(self,symbol,limit):
        with self.lock:
            now=self.clock()
            if type(now)is not int or now<0 or symbol not in self.symbols or type(limit)is not int or not 1<=limit<=499 or now>=self.deadline:raise ValueError('admission')
            weight=1 if limit<100 else 2
            if self.requests<1 or self.weight<weight:raise ValueError('budget exhausted')
            self.requests-=1;self.weight-=weight
            return {'limit':limit,'weight':weight,'execution_authorized':False}
def plan(start,end):
    if type(start)is not int or type(end)is not int or start<0 or start%60000 or end%60000 or end<start or end-start>600000*60000:raise ValueError('exact minute range/admission limit')
    out=[]
    while start<end:
        n=min(499,(end-start)//60000);out.append({'startTime':start,'endTime':start+n*60000-1,'limit':n,'weight':1 if n<100 else 2});start+=n*60000
    return out
class Pipeline:
    def __init__(self,store,session,key,symbols,universe_version,clock):
        if len(universe_version)!=64 or any(x not in '0123456789abcdef' for x in universe_version):raise ValueError('universe identity')
        self.store=store;self.session=session;self.key=key;self.universe=universe_version;self.clock=clock
        self.receiver=Receiver(session,key,symbols,clock);self.generation=store.claim(session);self.storage_errors={};self.commits=0
        self.snapshot_serial=0;self.snapshot_state=None
    @property
    def storage_error(self):return '; '.join(self.storage_errors.values()) or None
    def encode(self,raw):
        event=envelope(raw,self.session,self.clock(),{s:('UM','PERPETUAL') for s in self.receiver.symbols})
        body=canonical({'schema_version':3,'universe_version':self.universe,'source_event':raw,'candle':event})
        if len(body)>16384:raise ValueError('frame bound')
        return hmac.digest(self.key,body,'sha256')+body
    def receive(self,packet):
        if not 32<len(packet)<=16416:raise ValueError('frame bound')
        sig,b=packet[:32],packet[32:]
        if not hmac.compare_digest(sig,hmac.digest(self.key,b,'sha256')):raise ValueError('MAC')
        data=json.loads(b,object_pairs_hook=Receiver._pairs)
        if set(data)!= {'schema_version','universe_version','source_event','candle'} or data['schema_version']!=3 or data['universe_version']!=self.universe:raise ValueError('schema/universe')
        e=data['candle'];reconstructed=envelope(data['source_event'],self.session,e['local_receipt_time_utc'],{s:('UM','PERPETUAL') for s in self.receiver.symbols})
        if canonical(reconstructed)!=canonical(e):raise ValueError('raw event linkage')
        result=self.receiver.ingest(signed(e,self.key))
        if result not in ('ACCEPTED','DUPLICATE'):return result
        if e['is_final']:
            k=(e['logical_symbol'],e['candle_open_time_utc'])
            try:
                state=self.store.commit(e,self.generation,self.session,envelope=data);self.commits+=state=='COMMITTED'
                # Only after successful commit can live pending become durable history.
                k=(e['logical_symbol'],e['candle_open_time_utc'])
                with self.receiver.lock:
                    self.receiver.history[k]=self.receiver.values(e);self.receiver.buckets.pop(k,None);self.receiver.serial+=1
                self.storage_errors.pop(k,None)
                return 'DURABLE_FINALIZED:'+state
            except Exception as exc:
                self.storage_errors[k]=str(exc);return 'LIVE_FINALIZED_NOT_YET_DURABLE:'+str(exc)
        return result
    def restore(self):
        with self.receiver.lock:
            for s in self.receiver.symbols:
                for minute,values,source,digest in self.store.rows(s,require_receipt=True):
                    if source!='SYNTHETIC_FIXTURE':raise ValueError('unqualified durable origin')
                    from decimal import Decimal
                    self.receiver.history[s,minute]=tuple(map(Decimal,json.loads(values)))
            self.receiver.serial+=1
    def snapshot(self,dbkey):
        b=self.receiver.binary(dbkey)
        if self.storage_error:
            # Native connection/health flag fails closed; durable history stays visible.
            b=b[:12]+struct.pack('<I',0)+b[16:]
            # Remove forming rows while unhealthy; pending final retains non-durable state.
            header=list(struct.unpack('<IIIIQQ64s80s',b[:176]));rows=[b[i:i+88] for i in range(176,len(b),88) if struct.unpack_from('<I',b,i+80)[0]!=2]
            header[2]=len(rows);b=struct.pack('<IIIIQQ64s80s',*header)+b''.join(rows)
        state=b[8:16]+b[176:]
        if state!=self.snapshot_state:self.snapshot_serial+=1;self.snapshot_state=state
        return b[:16]+struct.pack('<Q',self.snapshot_serial)+b[24:]
