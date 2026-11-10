"""Admitted real sockets. Isolated loopback endpoint authority only in R5.

No DNS, proxies, redirects, retry, address iteration, compression or auto-reconnect.
External hostname/TLS source authorization remains a separate closed gate.
"""
import socket,ssl,threading,time,hashlib,base64,secrets,struct,json
from collections import deque
from functools import wraps
from dataclasses import dataclass
from urllib.parse import urlencode
from admission import Refused
def operation(fn):
    @wraps(fn)
    def wrapped(self,*args,**kwargs):
        self.local.deadline=time.monotonic()+1.0
        try:return fn(self,*args,**kwargs)
        finally:
            if hasattr(self.local,'deadline'):del self.local.deadline
    return wrapped
@dataclass(frozen=True)
class Endpoint:
    port:int
    tls:bool=False
    hostname:str='localhost'
    cafile:str|None=None
    def __post_init__(self):
        if type(self.port)is not int or not 1024<=self.port<=65535 or self.port in (10101,18101):raise Refused('unapproved port')
        if type(self.tls)is not bool or self.hostname not in ('localhost','wrong.local'):raise Refused('endpoint identity')
        if self.tls and not self.cafile:raise Refused('explicit test CA required')
class Backend:
    def __init__(self,controller,bindings,endpoint):
        if type(endpoint)is not Endpoint:raise Refused('endpoint contract')
        self.control=controller;self.bindings=dict(bindings);self.endpoint=endpoint
        self.lock=threading.RLock();self.socket_lock=threading.Lock();self.sockets=set();self.ws=None;self.closed=threading.Event();self.ws_attempted=False;self.subscribed=set()
        self.local=threading.local();self.trace=deque(maxlen=4096)
        self.watch=threading.Thread(target=self._watch,daemon=True);self.watch.start()
    def _watch(self):
        while not self.closed.wait(.02):
            try:self.control.reserve('HEALTH',**self.bindings)
            except Exception:self._close_sockets();self.closed.set();return
    def _close_sockets(self):
        with self.socket_lock:
            for s in list(self.sockets):
                try:s.shutdown(socket.SHUT_RDWR)
                except OSError:pass
                s.close()
            self.sockets.clear();self.ws=None
    def close(self):
        self.closed.set();self._close_sockets()
        if threading.current_thread()!=self.watch:self.watch.join(1)
    def shutdown(self):
        self.close();self.control.stop('owned backend shutdown')
    def _reserve(self,kind,**kw):
        self.trace.append((time.perf_counter_ns(),'reserve_enter',kind))
        if self.closed.is_set():raise Refused('backend stopped')
        try:
            result=self.control.reserve(kind,**self.bindings,**kw)
            self.trace.append((time.perf_counter_ns(),'reserve_exit',kind))
            if time.monotonic()>getattr(self.local,'deadline',float('inf')):raise TimeoutError('operation admission deadline')
            return result
        except Exception:self.close();raise
    def _deadline(self,ticket):return min(getattr(self.local,'deadline',float('inf')),time.monotonic()+min(ticket['remaining_ms']/1000,1.0))
    def _timeout(self,s,deadline):
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('aggregate operation deadline')
        s.settimeout(remaining)
    def _connect(self,ticket):
        deadline=self._deadline(ticket)
        s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        with self.socket_lock:
            if self.closed.is_set():s.close();raise Refused('closed')
            self.sockets.add(s)
        try:
            self._timeout(s,deadline);s.connect(('127.0.0.1',self.endpoint.port))
            if self.endpoint.tls:
                ctx=ssl.create_default_context(cafile=self.endpoint.cafile)
                ctx.minimum_version=ssl.TLSVersion.TLSv1_2;ctx.check_hostname=True;ctx.verify_mode=ssl.CERT_REQUIRED
                # Own socket set updated under lock; watcher can close during handshake.
                with self.socket_lock:
                    if self.closed.is_set():raise Refused('closed during TLS setup')
                    wrapped=ctx.wrap_socket(s,server_hostname=self.endpoint.hostname,do_handshake_on_connect=False)
                    self.sockets.discard(s);self.sockets.add(wrapped);s=wrapped
                self._timeout(s,deadline);s.do_handshake()
            self._reserve('HEALTH');return s,deadline
        except BaseException:self._drop(s);raise
    def _drop(self,s):
        self.trace.append((time.perf_counter_ns(),'drop_enter',''))
        if s is None:return
        with self.socket_lock:self.sockets.discard(s)
        try:s.shutdown(socket.SHUT_RDWR)
        except OSError:pass
        s.close()
        self.trace.append((time.perf_counter_ns(),'drop_exit',''))
    def _read(self,s,n,deadline):
        out=bytearray()
        while len(out)<n:
            self._timeout(s,deadline);self.trace.append((time.perf_counter_ns(),'recv_enter',n-len(out)))
            try:b=s.recv(n-len(out))
            finally:self.trace.append((time.perf_counter_ns(),'recv_exit',''))
            if not b:raise EOFError('truncated transport')
            out.extend(b)
        return bytes(out)
    def _headers(self,s,deadline):
        b=bytearray()
        while not b.endswith(b'\r\n\r\n'):
            if len(b)>=8192:raise Refused('header limit')
            b.extend(self._read(s,1,deadline))
        lines=b.decode('ascii').split('\r\n');parts=lines[0].split(' ')
        if len(parts)<2 or parts[0]!='HTTP/1.1':raise Refused('HTTP status')
        headers={}
        for line in lines[1:]:
            if not line:continue
            k,sep,v=line.partition(':');k=k.lower()
            if not sep or k in headers:raise Refused('ambiguous headers')
            headers[k]=v.strip()
        return int(parts[1]),headers
    @operation
    def http(self,kind,symbol=None,start=None,end=None,limit=None):
        self.trace.append((time.perf_counter_ns(),'http_enter',''))
        with self.lock:
            if kind=='metadata':
                self._reserve('REST_METADATA');target='/fapi/v1/exchangeInfo'
            elif kind=='klines':
                if type(start)is not int or type(end)is not int or type(limit)is not int or start<0 or start%60000 or end!=start+limit*60000-1:raise Refused('exact range')
                self._reserve('REST_KLINE',symbol=symbol,limit=limit)
                target='/fapi/v1/klines?'+urlencode(dict(symbol=symbol,interval='1m',startTime=start,endTime=end,limit=limit))
            else:raise Refused('unapproved endpoint')
            ticket=self._reserve('NET_CONNECT');s=None
            try:
                s,deadline=self._connect(ticket);self._timeout(s,deadline)
                s.sendall(f'GET {target} HTTP/1.1\r\nHost: {self.endpoint.hostname}\r\nConnection: close\r\n\r\n'.encode())
                status,h=self._headers(s,deadline)
                if status!=200:raise Refused('HTTP status/redirect refused')
                if 'transfer-encoding' in h or 'content-encoding' in h:raise Refused('encoded response unsupported')
                if 'content-length' not in h or not h['content-length'].isdigit():raise Refused('bounded content length required')
                n=int(h['content-length'])
                if n>65536:raise Refused('HTTP payload limit')
                data=self._read(s,n,deadline);self._reserve('HEALTH');return data
            finally:
                if s:self._drop(s)
                self.trace.append((time.perf_counter_ns(),'http_exit',''))
    @operation
    def connect_ws(self,reconnect=False):
        with self.lock:
            if type(reconnect)is not bool:raise Refused('explicit reconnect required')
            ticket=self._reserve('WS_CONNECT',reconnect=reconnect);self.ws_attempted=True
            self.subscribed.clear()
            if self.ws:self._drop(self.ws);self.ws=None
            s=None
            try:
                s,deadline=self._connect(ticket);key=base64.b64encode(secrets.token_bytes(16)).decode();self._timeout(s,deadline)
                s.sendall(f'GET /market/ws HTTP/1.1\r\nHost: {self.endpoint.hostname}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n'.encode())
                code,h=self._headers(s,deadline);expected=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
                if code!=101 or h.get('sec-websocket-accept')!=expected or h.get('upgrade','').lower()!='websocket' or h.get('connection','').lower()!='upgrade' or 'sec-websocket-extensions' in h:raise Refused('WS handshake')
                self._reserve('HEALTH');self.ws=s;return True
            except BaseException:
                if s:self._drop(s)
                raise
    @operation
    def subscribe(self,symbol):
        with self.lock:
            ticket=self._reserve('SUBSCRIBE',symbol=symbol)
            if not self.ws:raise Refused('no WS')
            payload=json.dumps({'method':'SUBSCRIBE','params':[symbol.lower()+'@kline_1m'],'id':1},separators=(',',':')).encode();mask=secrets.token_bytes(4)
            frame=bytes([0x81,0x80|len(payload)])+mask+bytes(v^mask[i%4] for i,v in enumerate(payload))
            s=self.ws
            try:self._timeout(s,self._deadline(ticket));s.sendall(frame);self._reserve('HEALTH');self.subscribed.add(symbol)
            except BaseException:self._drop(s);self.ws=None;raise
    @operation
    def receive(self):
        with self.lock:
            ticket=self._reserve('HEALTH');s=self.ws
            if not s:raise Refused('no WS')
            deadline=self._deadline(ticket)
            try:
                for _ in range(8):
                    a,b=self._read(s,2,deadline)
                    if a not in (0x81,0x89,0x8a,0x88) or b&0x80:raise Refused('unsupported WS framing')
                    n=b&127
                    if a!=0x81 and n>125:raise Refused('control frame length')
                    if n==126:n=struct.unpack('!H',self._read(s,2,deadline))[0]
                    elif n==127:n=struct.unpack('!Q',self._read(s,8,deadline))[0]
                    self._reserve('FRAME',bytes_count=n)
                    body=self._read(s,n,deadline)
                    if a==0x88:raise EOFError('peer close')
                    if a==0x89:
                        self._reserve('FRAME',bytes_count=n) # Outbound pong is admitted too.
                        mask=secrets.token_bytes(4);frame=bytes([0x8a,0x80|n])+mask+bytes(v^mask[i%4] for i,v in enumerate(body));self._timeout(s,deadline);s.sendall(frame);continue
                    if a==0x8a:continue
                    body.decode('utf-8');self._reserve('HEALTH');return body
                raise Refused('control frame flood')
            except BaseException:self._drop(s);self.ws=None;raise
