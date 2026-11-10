from pathlib import Path
import sys,json,secrets,time,unittest,os,concurrent.futures
R=Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'src'),str(R/'dependencies/r3'),str(R/'tests')]
from admission import Controller,Refused
from network import Backend,Endpoint
from servers import Server
from handoff import Handoff
from pipeline import Pipeline
from durable import Store
def contract():
 now=time.time_ns()//1000000
 return dict(authority=secrets.token_hex(16),producer_session=secrets.token_hex(16),receiver_session=secrets.token_hex(16),symbols=['BTCUSDT','ETHUSDT'],universe_version='a'*64,start_ms=now,end_ms=now+120000,rest_requests=2,rest_weight=4,connection_attempts=4,subscriptions=2,reconnects=1,max_frames=100,max_bytes=100000,receiver_pid=os.getpid(),receiver_creation=123)
class Tests(unittest.TestCase):
 def setUp(self):self.resources=[];self.c=contract()
 def tearDown(self):
  for o in reversed(self.resources):o.close()
 def setup_backend(self,mode='http',body=b'{}',**changes):
  self.c.update(changes);server=Server(mode,body);self.resources.append(server)
  self.path=R/'disposable'/('ledger_'+secrets.token_hex(6)+'.sqlite');Controller.provision(self.path,self.c);ctl=Controller(self.path,self.c);self.resources.append(ctl)
  bindings={k:self.c[k] for k in ('producer_session','receiver_session','receiver_pid','receiver_creation')}
  b=Backend(ctl,bindings,Endpoint(server.port));self.resources.append(b);return b,server
 def test_http(self):
  b,s=self.setup_backend();self.assertEqual(b.http('metadata'),b'{}');self.assertEqual(len(s.requests),1)
 def test_zero(self):
  b,s=self.setup_backend(rest_requests=0,rest_weight=0)
  with self.assertRaises(Refused):b.http('metadata')
  self.assertEqual(s.count,0)
 def test_count(self):
  b,s=self.setup_backend(rest_requests=1);b.http('metadata')
  with self.assertRaises(Refused):b.http('metadata')
  self.assertEqual(s.count,1)
 def test_weight(self):
  b,s=self.setup_backend(rest_weight=1)
  with self.assertRaises(Refused):b.http('klines','BTCUSDT',0,499*60000-1,499)
  self.assertEqual(s.count,0)
 def test_pagination(self):
  b,s=self.setup_backend(rest_requests=1);b.http('klines','BTCUSDT',0,60000-1,1)
  with self.assertRaises(Refused):b.http('klines','BTCUSDT',60000,120000-1,1)
  self.assertEqual(s.count,1)
 def test_timeout(self):
  b,s=self.setup_backend('timeout');t=time.monotonic()
  with self.assertRaises((TimeoutError,OSError)):b.http('metadata')
  self.assertLess(time.monotonic()-t,1.5);self.assertEqual(s.count,1);self.assertFalse(b.sockets)
 def test_redirect(self):
  b,s=self.setup_backend('redirect')
  with self.assertRaises(Refused):b.http('metadata')
  self.assertEqual(s.count,1)
 def test_broken_no_retry(self):
  b,s=self.setup_backend('broken')
  with self.assertRaises(EOFError):b.http('metadata')
  self.assertEqual(s.count,1)
 def test_ws(self):
  b,s=self.setup_backend('ws',b'{}');b.connect_ws();b.subscribe('BTCUSDT');self.assertEqual(b.receive(),b'{}');self.assertEqual(s.count,1)
 def test_ws_limit(self):
  b,s=self.setup_backend('ws',connection_attempts=1,reconnects=0);b.connect_ws()
  with self.assertRaises(Refused):b.connect_ws(True)
  self.assertEqual(s.count,1);self.assertFalse(b.sockets)
 def test_sub_limit(self):
  b,s=self.setup_backend('ws_quiet',subscriptions=1);b.connect_ws();b.subscribe('BTCUSDT')
  with self.assertRaises(Refused):b.subscribe('ETHUSDT')
  self.assertFalse(b.sockets)
 def test_symbol(self):
  b,s=self.setup_backend('ws');b.connect_ws()
  with self.assertRaises(Refused):b.subscribe('XRPUSDT')
 def test_endpoint(self):
  with self.assertRaises(Refused):Endpoint(18101)
  with self.assertRaises(Refused):Endpoint(10101)
  with self.assertRaises(Refused):Endpoint(20000,hostname='binance.com')
 def test_unexpected_reconnect(self):
  b,s=self.setup_backend('ws');b.connect_ws()
  with self.assertRaises(Refused):b.connect_ws()
  self.assertEqual(s.count,1)
 def test_bad_handshake(self):
  b,s=self.setup_backend('ws_bad')
  with self.assertRaises(Refused):b.connect_ws()
  self.assertFalse(b.sockets)
 def test_oversize(self):
  b,s=self.setup_backend('ws_oversize');b.connect_ws();b.subscribe('BTCUSDT')
  with self.assertRaises(Refused):b.receive()
  self.assertFalse(b.sockets)
 def test_expired(self):
  self.c['end_ms']=self.c['start_ms']+2000;b,s=self.setup_backend('ws_quiet');b.connect_ws();time.sleep(2.2)
  self.assertTrue(b.closed.is_set());self.assertFalse(b.sockets)
 def test_restart(self):
  b,s=self.setup_backend(rest_requests=1);b.http('metadata');b.close()
  ctl=Controller(self.path,self.c);self.resources.append(ctl);n=Backend(ctl,b.bindings,b.endpoint);self.resources.append(n)
  with self.assertRaises(Refused):n.http('metadata')
  self.assertEqual(s.count,1)
 def test_proxy_ignored(self):
  prior=os.environ.get('HTTPS_PROXY');os.environ['HTTPS_PROXY']='http://127.0.0.1:18101'
  try:
   b,s=self.setup_backend();self.assertEqual(b.http('metadata'),b'{}');self.assertEqual(s.count,1)
  finally:
   if prior is None:os.environ.pop('HTTPS_PROXY',None)
   else:os.environ['HTTPS_PROXY']=prior
 def test_concurrent(self):
  b,s=self.setup_backend(rest_requests=1)
  def get(_):
   try:b.http('metadata');return 1
   except Refused:return 0
  with concurrent.futures.ThreadPoolExecutor(max_workers=2) as p:self.assertEqual(sum(p.map(get,range(2))),1)
  self.assertEqual(s.count,1)
 def test_corrupt_ledger(self):
  b,s=self.setup_backend();b.control.db.execute('UPDATE state SET rest=-1')
  with self.assertRaises(Refused):b.http('metadata')
  self.assertEqual(s.count,0)
 def test_two_symbol_pipeline(self):
  for symbol in ('BTCUSDT','ETHUSDT'):
   now=time.time_ns()//1000000;t=now//60000*60000-60000
   raw=dict(e='kline',s=symbol,E=now,st='UM',k=dict(s=symbol,i='1m',t=t,T=t+59999,o='100',h='102',l='99',c='101',v='2',q='202',n=2,x=True))
   b,s=self.setup_backend('ws',json.dumps(raw).encode());st=Store(R/'dependencies/disposable'/('feed_'+secrets.token_hex(5)+'.sqlite'),'fixture');self.resources.append(st)
   p=Pipeline(st,self.c['producer_session'],b'a'*32,self.c['symbols'],self.c['universe_version'],lambda:time.time_ns()//1000000)
   b.connect_ws();b.subscribe(symbol);h=Handoff(b,p);result,packet=h.receive_one();self.assertEqual(result,'DURABLE_FINALIZED:COMMITTED');self.assertEqual(json.loads(packet[32:])['source_event'],raw);self.assertEqual(len(st.rows(symbol,True)),1)
   b.close()
if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 (R/'R6_REAL_SOCKET_ADMISSION_RESULTS.json').write_text(json.dumps({'passed':result.wasSuccessful(),'tests':result.testsRun,'failures':[str(x) for x in result.failures+result.errors],'external_requests':0,'actual_loopback_sockets':True},indent=2));raise SystemExit(not result.wasSuccessful())
