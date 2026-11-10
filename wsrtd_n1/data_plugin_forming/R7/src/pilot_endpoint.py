"""Official raw BTC endpoint allowlist. Runtime external dispatch remains disabled."""
from urllib.parse import urlsplit
from network import Backend,Endpoint,operation
import time
from resolver import resolve
from admission import Refused
URL='wss://fstream.binance.com/market/ws/btcusdt@kline_1m'
def qualify(url):
 u=urlsplit(url)
 if url!=URL or (u.scheme,u.hostname,u.port,u.path,u.query,u.fragment,u.username,u.password)!=('wss','fstream.binance.com',None,'/market/ws/btcusdt@kline_1m','','',None,None):raise Refused('exact one-stream URL required')
 return dict(version=1,scheme='wss',host=u.hostname,port=443,path=u.path,symbol='BTCUSDT',interval='1m',streams=1)
class PilotFixtureBackend(Backend):
 ws_path='/market/ws/btcusdt@kline_1m'
 def __init__(self,controller,bindings,url,test_port,test_ca):
  self.policy=qualify(url)
  c=controller.c
  if c['symbols']!=['BTCUSDT'] or any(c[k]!=v for k,v in dict(rest_requests=0,rest_weight=0,connection_attempts=1,subscriptions=1,reconnects=0).items()):raise Refused('one-shot zero-REST contract')
  super().__init__(controller,bindings,Endpoint(test_port,True,'localhost',test_ca))
 def _connect(self,ticket):
  remaining=self._deadline(ticket)-time.monotonic()
  if remaining<=0:raise TimeoutError('resolution admission deadline')
  resolve('localhost',self.endpoint.port,timeout=min(.5,remaining))
  return super()._connect(ticket)
 @operation
 def connect_ws(self,reconnect=False):
  if reconnect is not False:raise Refused('reconnect prohibited')
  self._reserve('SUBSCRIBE',symbol='BTCUSDT') # URL stream is debited before opening socket.
  result=super().connect_ws(False);self.subscribed.add('BTCUSDT');return result
 def subscribe(self,symbol):raise Refused('raw-path subscription already consumed; control subscribe prohibited')
 def http(self,*args,**kwargs):raise Refused('zero REST')
