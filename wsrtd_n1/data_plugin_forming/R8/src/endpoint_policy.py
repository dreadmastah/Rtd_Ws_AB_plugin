"""Versioned endpoint enforcement. R6 dispatch is local-only; live authority stays closed."""
import socket,ssl,ipaddress,time
from dataclasses import dataclass
from urllib.parse import urlsplit
from network import Backend,Endpoint
from admission import Refused
@dataclass(frozen=True)
class Policy:
 scheme:str
 hostname:str
 port:int
 path:str
 pinned_ip:str
 cafile:str
 protocol_evidence_sha256:str
 version:int=1
 def validate(self,url,kind):
  u=urlsplit(url)
  if self.version!=1 or self.scheme not in ('https','wss') or self.scheme!=('https' if kind=='http' else 'wss'):raise Refused('scheme/version')
  if u.username or u.password or u.fragment or u.query or u.scheme!=self.scheme or u.hostname!=self.hostname or (u.port or 443)!=self.port or u.path!=self.path:raise Refused('exact endpoint')
  if self.path not in ('/fapi/v1/exchangeInfo','/fapi/v1/klines','/market/ws'):raise Refused('path')
  if not self.hostname or self.hostname.endswith('.') or self.hostname.lower()!=self.hostname or self.port in (10101,18101) or not 1024<=self.port<=65535:raise Refused('endpoint scope')
  if self.hostname!='localhost' or ipaddress.ip_address(self.pinned_ip)!=ipaddress.ip_address('127.0.0.1'):raise Refused('external activation prohibited in R6')
  if len(self.protocol_evidence_sha256)!=64 or any(x not in '0123456789abcdef' for x in self.protocol_evidence_sha256):raise Refused('protocol evidence binding')
  if not self.cafile:raise Refused('trust required')
class PolicyBackend(Backend):
 def __init__(self,controller,bindings,policy,url,kind):
  policy.validate(url,kind);self.policy=policy;self.kind=kind
  super().__init__(controller,bindings,Endpoint(policy.port,True,policy.hostname,policy.cafile))
 def _connect(self,ticket):
  # Debit is committed by caller before resolution. Pin once; never iterate fallback addresses.
  deadline=self._deadline(ticket)
  answers=socket.getaddrinfo(self.policy.hostname,self.policy.port,socket.AF_INET,socket.SOCK_STREAM)
  if not answers or any(a[4][0]!=self.policy.pinned_ip for a in answers):raise Refused('DNS pin/rebinding')
  if time.monotonic()>=deadline:raise TimeoutError('DNS deadline')
  return super()._connect(ticket) # literal same pinned 127.0.0.1; TLS uses policy hostname
 def http(self,kind,*args,**kwargs):
  expected='/fapi/v1/exchangeInfo' if kind=='metadata' else '/fapi/v1/klines'
  if self.kind!='http' or self.policy.path!=expected:raise Refused('HTTP route')
  return super().http(kind,*args,**kwargs)
 def connect_ws(self,reconnect=False):
  if self.kind!='ws' or self.policy.path!='/market/ws':raise Refused('WS route')
  return super().connect_ws(reconnect)
