"""Manifest-gated real external WSS. No live manifest is supplied with this candidate."""
from pathlib import Path
import json,hashlib,time,socket,ssl,base64,secrets,struct,os,ipaddress
from collections import deque
from types import SimpleNamespace
from admission import Refused,Controller,validate as validate_contract
from custody import Attestation
from network import Backend,Endpoint
from external_resolver import resolve
URL='wss://fstream.binance.com/market/ws/btcusdt@kline_1m'
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def validate(m,approved_hash,fixture=False):
 if hashlib.sha256(canonical(m)).hexdigest()!=approved_hash:raise Refused('operator manifest digest')
 fields={'version','scope','url','contract','producer','code_hashes','approved_ips','port','cafile','output_dir','storage_parent_identity','operator_authorization'}
 if set(m)!=fields or m['version']!=1 or type(m['version'])is not int:raise Refused('manifest schema')
 if m['scope']!=('LOCAL_TLS_TEST' if fixture else 'PHASE_A_GENUINE_RECEIPT') or m['operator_authorization'] is not True:raise Refused('explicit scope authorization')
 if m['url']!=URL:raise Refused('exact BTC raw endpoint')
 c=m['contract']
 validate_contract(c)
 if c['symbols']!=['BTCUSDT'] or any(c[k]!=v for k,v in dict(rest_requests=0,rest_weight=0,connection_attempts=1,subscriptions=1,reconnects=0).items()):raise Refused('one-shot contract')
 if not fixture and (m['port']!=443 or m['cafile'] is not None):raise Refused('system TLS / port443 required')
 if fixture and (type(m['port'])is not int or not 1024<=m['port']<=65535 or m['port'] in (10101,18101) or not m['cafile']):raise Refused('test endpoint')
 if type(m['approved_ips'])is not list or not 1<=len(m['approved_ips'])<=16:raise Refused('DNS bindings')
 for ip in m['approved_ips']:
  a=ipaddress.IPv4Address(ip)
  if (fixture and str(a)!='127.0.0.1') or (not fixture and not a.is_global):raise Refused('IP scope')
 root=Path(__file__).resolve().parent
 actual={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.py')}
 actual.update({'dependencies/r3/'+p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root.parent/'dependencies/r3').glob('*.py')})
 if m['code_hashes']!=actual:raise Refused('exact source set')
 if any(os.environ.get(k) for k in ('SSL_CERT_FILE','SSL_CERT_DIR')):raise Refused('TLS environment trust override forbidden')
 if m['producer']['pid']!=os.getpid():raise Refused('current process must own producer socket')
 actor=Attestation(os.getpid(),m['producer']);actor.close()
 if (c['receiver_pid'],c['receiver_creation'])!=(m['producer']['pid'],m['producer']['creation']):raise Refused('Phase A same-process receipt writer custody')
 lexical=Path(m['output_dir']).absolute()
 for component in (lexical,*lexical.parents):
  if component.exists() and getattr(component.lstat(),'st_file_attributes',0)&0x400:raise Refused('reparse storage component')
 out=lexical.resolve();allowed=root.parent/'disposable'
 if allowed not in out.parents or any(p.is_symlink() for p in (out,*out.parents)):raise Refused('disposable output boundary')
 if not out.parent.is_dir():raise Refused('existing approved storage parent required')
 info=out.parent.stat()
 if m['storage_parent_identity']!={'path':str(out.parent),'device':info.st_dev,'inode':info.st_ino}:raise Refused('physical storage parent identity')
 return out
class ExternalWS(Backend):
 def __init__(self,ctl,m,approved_hash,fixture=False):
  validate(m,approved_hash,fixture)
  if ctl.c!=m['contract']:raise Refused('ledger/manifest mismatch')
  self.manifest=json.loads(canonical(m));self.fixture=fixture;self.outbound=deque();self.actor=Attestation(os.getpid(),m['producer'])
  super().__init__(ctl,{k:ctl.c[k] for k in ('producer_session','receiver_session','receiver_pid','receiver_creation')},Endpoint(45001))
 def _reserve(self,kind,**kw):
  self.actor.check();return super()._reserve(kind,**kw)
 def connect_ws(self,reconnect=False):
  if reconnect is not False:raise Refused('reconnect prohibited')
  with self.lock:
   s=None;deadline=min(time.monotonic()+5,time.monotonic()+max(0,(self.control.c['end_ms']-time.time_ns()//1000000)/1000))
   self.local.deadline=deadline
   try:
    self._reserve('SUBSCRIBE',symbol='BTCUSDT');self._reserve('WS_CONNECT',reconnect=False)
    host='localhost' if self.fixture else 'fstream.binance.com'
    address=resolve(host,self.manifest['port'],self.manifest['approved_ips'],deadline,self.fixture)
    self._reserve('HEALTH') # rejects expired/closed gate after late DNS
    s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    with self.socket_lock:
     if self.closed.is_set():s.close();raise Refused('closed before connect')
     self.sockets.add(s)
    self._timeout(s,deadline);s.connect((address,self.manifest['port']))
    ctx=ssl.create_default_context(cafile=self.manifest['cafile'] if self.fixture else None);ctx.minimum_version=ssl.TLSVersion.TLSv1_2
    with self.socket_lock:
     if self.closed.is_set():raise Refused('closed before TLS')
     tls=ctx.wrap_socket(s,server_hostname=host,do_handshake_on_connect=False);self.sockets.discard(s);self.sockets.add(tls);s=tls
    self._timeout(s,deadline);s.do_handshake();self._reserve('HEALTH')
    key=base64.b64encode(secrets.token_bytes(16)).decode()
    request=f'GET /market/ws/btcusdt@kline_1m HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n'.encode()
    self._timeout(s,deadline);s.sendall(request)
    code,h=self._headers(s,deadline);expected=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
    if code!=101 or h.get('sec-websocket-accept')!=expected or h.get('upgrade','').lower()!='websocket' or h.get('connection','').lower()!='upgrade' or 'sec-websocket-extensions' in h:raise Refused('handshake/redirect')
    self._reserve('HEALTH');self.ws=s;self.subscribed={'BTCUSDT'};return True
   except BaseException:
    self._drop(s);self.close();raise
   finally:
    if hasattr(self.local,'deadline'):del self.local.deadline
 def http(self,*a,**k):raise Refused('zero REST')
 def subscribe(self,*a,**k):raise Refused('URL stream only')
 def _pong(self,s,body,deadline):
  now=time.monotonic()
  while self.outbound and now-self.outbound[0]>=1:self.outbound.popleft()
  if len(self.outbound)>=5:raise Refused('outbound control rate')
  self._reserve('FRAME',bytes_count=len(body));self.outbound.append(now)
  mask=secrets.token_bytes(4);frame=bytes([0x8a,0x80|len(body)])+mask+bytes(v^mask[i%4] for i,v in enumerate(body));self._timeout(s,deadline);s.sendall(frame)
 def close(self):
  super().close()
  if getattr(self,'actor',None):self.actor.close();self.actor=None
