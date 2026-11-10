"""Versioned bounded sender facade; injected fixture backend ONLY, never production."""
import json,time,threading
from admission import Refused
class FixtureBackend:
    """Deterministic I/O double; no socket, DNS, HTTP or WebSocket dependency."""
    def __init__(self):self.calls=[];self.closed=False;self.fail=False
    def request(self,endpoint,params,timeout_ms):
        self.calls.append(('rest',endpoint,params,timeout_ms))
        if self.fail:raise OSError('fixture failure')
        return {'fixture':True}
    def connect(self,endpoint,timeout_ms):
        self.calls.append(('connect',endpoint,timeout_ms))
        if self.fail:raise OSError('fixture failure')
    def subscribe(self,stream,timeout_ms):
        self.calls.append(('subscribe',stream,timeout_ms))
        if self.fail:raise OSError('fixture failure')
    def close(self):self.closed=True
class Sender:
    def __init__(self,controller,backend,bindings,watchdog=False):
        if type(backend)is not FixtureBackend:raise Refused('production backend not qualified')
        self.control=controller;self.backend=backend;self.bindings=dict(bindings);self.connected=False;self.subscribed=set();self.lock=threading.RLock();self.done=threading.Event()
        self.watchdog=None
        # Default tests use deterministic clock. Optional own-instance watchdog
        # closes fixture resource at expiry even when there are no source events.
        if watchdog:
            self.watchdog=threading.Thread(target=self._watch,daemon=True);self.watchdog.start()
    def _watch(self):
        while not self.done.wait(.01):
            try:self.control.reserve('HEALTH',**self.bindings)
            except Exception:self.backend.close();self.done.set();return
    def _admit(self,kind,**kw):
        if self.done.is_set():raise Refused('sender stopped')
        try:return self.control.reserve(kind,**self.bindings,**kw)
        except Exception:self.backend.close();self.done.set();raise
    def metadata(self):
        with self.lock:
            ticket=self._admit('REST_METADATA')
            result=self.backend.request('/fapi/v1/exchangeInfo',{},min(ticket['remaining_ms'],1000));self._admit('HEALTH');return result
    def history(self,symbol,start,end,limit):
        with self.lock:
            if type(start)is not int or type(end)is not int or start<0 or start%60000 or end<start or type(limit)is not int or end!=start+limit*60000-1:raise Refused('bounded range')
            ticket=self._admit('REST_KLINE',symbol=symbol,limit=limit)
            result=self.backend.request('/fapi/v1/klines',{'symbol':symbol,'interval':'1m','startTime':start,'endTime':end,'limit':limit},min(ticket['remaining_ms'],1000));self._admit('HEALTH');return result
    def connect(self,reconnect=False):
        with self.lock:
            ticket=self._admit('WS_CONNECT',reconnect=reconnect)
            self.connected=False;self.subscribed.clear()
            self.backend.connect('wss://fstream.binance.com/market/ws',min(ticket['remaining_ms'],1000));self._admit('HEALTH');self.connected=True
    def subscribe(self,symbol):
        with self.lock:
            if not self.connected:raise Refused('no admitted connection')
            ticket=self._admit('SUBSCRIBE',symbol=symbol)
            self.backend.subscribe(symbol.lower()+'@kline_1m',min(ticket['remaining_ms'],1000));self._admit('HEALTH');self.subscribed.add(symbol)
    def source_event(self,raw_bytes,pipeline):
        with self.lock:
            self._admit('FRAME',bytes_count=len(raw_bytes))
            if not self.connected:raise Refused('not connected')
            def unique(pairs):
                out={}
                for k,v in pairs:
                    if k in out:raise ValueError('duplicate source key')
                    out[k]=v
                return out
            try:raw=json.loads(raw_bytes,object_pairs_hook=unique)
            except (ValueError,RecursionError) as e:raise Refused('invalid source JSON') from e
            if not isinstance(raw,dict):raise Refused('source object required')
            if pipeline.session!=self.control.c['producer_session'] or pipeline.universe!=self.control.c['universe_version'] or pipeline.receiver.symbols!=frozenset(self.control.c['symbols']):raise Refused('pipeline authority mismatch')
            if raw.get('s') not in self.subscribed:raise Refused('not subscribed')
            # Pipeline.encode retains original x/E; no wall-clock reconstruction.
            # This path is deliberately synthetic because genuine custody is absent.
            return pipeline.encode(raw)
    def shutdown(self):
        self.done.set();self.backend.close()
        if self.watchdog and self.watchdog is not threading.current_thread():self.watchdog.join(1)
        self.control.stop('explicit sender shutdown')

class IsolatedRelay:
    """Bounded exact-byte frame handoff, never uses protected18101 listener."""
    def __init__(self,controller,bindings):self.control=controller;self.bindings=dict(bindings);self.frames=0;self.bytes=0
    def forward(self,packet,receiver):
        # Relay attempts consume the same aggregate budget as source ingress.
        # Count both stages explicitly; replay cannot bypass the handoff ceiling.
        self.control.reserve('FRAME',bytes_count=len(packet) if isinstance(packet,bytes) else 16385,**self.bindings)
        if receiver.session!=self.control.c['producer_session'] or receiver.universe!=self.control.c['universe_version'] or receiver.receiver.symbols!=frozenset(self.control.c['symbols']):raise Refused('receiver authority mismatch')
        if type(packet)is not bytes or not 32<len(packet)<=16416:raise Refused('relay frame bound')
        self.frames+=1;self.bytes+=len(packet)
        return receiver.receive(packet)
