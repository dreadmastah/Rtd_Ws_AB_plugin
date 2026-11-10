from pathlib import Path
import sys,json,secrets,unittest,time,hashlib,concurrent.futures
R=Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'src'),str(R/'dependencies/r3')]
from admission import Controller,Refused
from sender import Sender,FixtureBackend,IsolatedRelay
from pipeline import Pipeline
from durable import Store
def contract(now):return dict(authority=secrets.token_hex(16),producer_session=secrets.token_hex(16),receiver_session=secrets.token_hex(16),symbols=['BTCUSDT','ETHUSDT'],universe_version='a'*64,start_ms=now,end_ms=now+120000,rest_requests=2,rest_weight=4,connection_attempts=2,subscriptions=2,reconnects=1,max_frames=100,max_bytes=100000,receiver_pid=1,receiver_creation=123)
def bindings(c):return {k:c[k] for k in ('producer_session','receiver_session','receiver_pid','receiver_creation')}
class Tests(unittest.TestCase):
 def setUp(self):
  self.now=[1800057600000];self.c=contract(self.now[0]);self.path=R/'disposable'/('budget_'+secrets.token_hex(6)+'.sqlite');self.ctl=None
 def start(self):
  Controller.provision(self.path,self.c);self.ctl=Controller(self.path,self.c,lambda:self.now[0],lambda:0);self.backend=FixtureBackend();self.s=Sender(self.ctl,self.backend,bindings(self.c));return self.s
 def tearDown(self):
  if self.ctl:self.ctl.close()
 def test_rest_caps(self):
  s=self.start();s.history('BTCUSDT',0,499*60000-1,499);s.history('ETHUSDT',0,499*60000-1,499)
  with self.assertRaises(Refused):s.metadata()
  self.assertEqual(len(self.backend.calls),2);self.assertTrue(self.backend.closed)
 def test_no_rest_all_paths(self):
  self.c['rest_requests']=self.c['rest_weight']=0;s=self.start()
  with self.assertRaises(Refused):s.metadata()
  self.assertEqual(self.backend.calls,[])
 def test_failed_attempt_consumed_restart(self):
  self.c['connection_attempts']=1;self.c['reconnects']=0;s=self.start();self.backend.fail=True
  with self.assertRaises(OSError):s.connect()
  self.ctl.close();self.ctl=Controller(self.path,self.c,lambda:self.now[0],lambda:0);s=Sender(self.ctl,FixtureBackend(),bindings(self.c))
  with self.assertRaises(Refused):s.connect(True)
  self.assertEqual(s.backend.calls,[])
 def test_session_binding(self):
  self.start();b=bindings(self.c);b['receiver_session']='0'*32
  with self.assertRaises(Refused):self.ctl.reserve('WS_CONNECT',**b)
 def test_clock_rollback(self):
  s=self.start();s.connect();self.now[0]-=1
  with self.assertRaises(Refused):s.subscribe('BTCUSDT')
 def test_expiry(self):
  s=self.start();self.now[0]=self.c['end_ms']
  with self.assertRaises(Refused):s.connect()
 def test_reconnect(self):
  s=self.start();s.connect();s.subscribe('BTCUSDT');s.connect(True);s.subscribe('ETHUSDT')
  with self.assertRaises(Refused):s.connect(True)
 def test_allowlist(self):
  s=self.start();s.connect()
  with self.assertRaises(Refused):s.subscribe('XRPUSDT')
 def test_invalid_budget(self):
  self.c['rest_requests']=float('nan')
  with self.assertRaises(Refused):self.start()
 def test_changed_authority(self):
  self.start();other=dict(self.c,rest_requests=20)
  with self.assertRaises(Refused):Controller(self.path,other)
 def test_concurrent_reserve(self):
  self.start()
  def call(_):
   try:self.ctl.reserve('REST_METADATA',**bindings(self.c));return 1
   except Refused:return 0
  with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:self.assertEqual(sum(pool.map(call,range(8))),2)
 def test_two_symbol_roundtrip(self):
  s=self.start();s.connect();s.subscribe('BTCUSDT');s.subscribe('ETHUSDT')
  path=R/'dependencies/disposable'/('integrated_'+secrets.token_hex(5)+'.sqlite');st=Store(path,'r4fixture');p=Pipeline(st,self.c['producer_session'],b'a'*32,self.c['symbols'],self.c['universe_version'],lambda:self.now[0]);relay=IsolatedRelay(self.ctl,bindings(self.c))
  try:
   for symbol in self.c['symbols']:
    t=self.c['start_ms'];self.now[0]=t+1000
    raw=dict(e='kline',s=symbol,E=self.now[0],st='UM',k=dict(s=symbol,i='1m',t=t,T=t+59999,o='100',h='102',l='99',c='101',v='2',q='202',n=2,x=False))
    packet=s.source_event(json.dumps(raw).encode(),p);self.assertEqual(json.loads(packet[32:])['source_event'],raw);self.assertEqual(relay.forward(packet,p),'ACCEPTED');self.assertEqual(st.rows(symbol),[])
   self.now[0]=t+61000
   for symbol in self.c['symbols']:
    raw=dict(e='kline',s=symbol,E=self.now[0],st='UM',k=dict(s=symbol,i='1m',t=t,T=t+59999,o='100',h='103',l='98',c='102',v='3',q='306',n=3,x=True))
    packet=s.source_event(json.dumps(raw).encode(),p);self.assertEqual(relay.forward(packet,p),'DURABLE_FINALIZED:COMMITTED');self.assertEqual(relay.forward(packet,p),'DURABLE_FINALIZED:IDEMPOTENT');self.assertEqual(len(st.rows(symbol,True)),1)
    self.assertIsNone(st.daily(symbol,t//86400000*86400000));self.assertFalse(st.coverage(symbol,t,t+60000)['full_prefix_qualified'])
   bad=dict(raw);bad.pop('E')
   with self.assertRaises(KeyError):s.source_event(json.dumps(bad).encode(),p)
  finally:st.close()
result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
(R/'evidence/AUTHOR_TESTS.json').write_text(json.dumps({'tests':result.testsRun,'passed':result.wasSuccessful(),'failures':[str(x) for x in result.failures+result.errors],'network_requests':0,'actual_amibroker':False},indent=2));raise SystemExit(not result.wasSuccessful())
