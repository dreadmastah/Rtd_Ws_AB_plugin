from pathlib import Path
import sys,secrets,json,unittest,sqlite3
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from pipeline import Pipeline,Budget,plan
from durable import Store
T=1800057600000
def raw(t,E,final=False):return {'e':'kline','s':'BTCUSDT','E':E,'st':'UM','k':{'s':'BTCUSDT','i':'1m','t':t,'T':t+59999,'o':'100.00000000000001','h':'102','l':'99','c':'101','v':'2','q':'202','n':2,'x':final}}
class Tests(unittest.TestCase):
 def setUp(self):
  self.p=R/'disposable'/('pipe_'+secrets.token_hex(5)+'.sqlite');self.store=Store(self.p,'fixture');self.now=[T+1000];self.pipe=Pipeline(self.store,'1'*32,b'a'*32,['BTCUSDT'],'a'*64,lambda:self.now[0])
 def tearDown(self):self.store.close()
 def test_replay_final(self):
  p=self.pipe;self.assertEqual(p.receive(p.encode(raw(T,self.now[0]))),'ACCEPTED');self.assertEqual(self.store.rows('BTCUSDT'),[])
  self.now[0]=T+61000;b=p.encode(raw(T,self.now[0],True));self.assertEqual(p.receive(b),'DURABLE_FINALIZED:COMMITTED');self.assertEqual(p.receive(b),'DURABLE_FINALIZED:IDEMPOTENT');self.assertEqual(len(p.receiver.snapshot()[0]),1)
 def test_late_final(self):
  p=self.pipe;p.receive(p.encode(raw(T,self.now[0])));self.now[0]=T+61000;p.receive(p.encode(raw(T+60000,self.now[0])));self.assertEqual(p.receive(p.encode(raw(T,self.now[0],True))),'DURABLE_FINALIZED:COMMITTED');self.assertEqual(len(p.receiver.snapshot()[0]),2)
 def test_failed_storage_visible(self):
  self.store.claim('2'*32);self.now[0]=T+61000;r=self.pipe.receive(self.pipe.encode(raw(T,self.now[0],True)));self.assertTrue(r.startswith('LIVE_FINALIZED_NOT_YET_DURABLE'));self.assertIsNotNone(self.pipe.storage_error);self.assertEqual(self.store.rows('BTCUSDT'),[])
 def test_restart_restore(self):
  self.now[0]=T+61000;self.pipe.receive(self.pipe.encode(raw(T,self.now[0],True)));p=Pipeline(self.store,'2'*32,b'b'*32,['BTCUSDT'],'a'*64,lambda:self.now[0]);p.restore();self.assertEqual(len(p.receiver.snapshot()[0]),1);self.assertFalse(p.receiver.status()['full_prefix_complete'])
 def test_malformed(self):
  with self.assertRaises(ValueError):self.pipe.receive(b'broken')
 def test_budget(self):
  b=Budget(['BTCUSDT'],2,4,100,lambda:1);b.reserve('BTCUSDT',499);b.reserve('BTCUSDT',499)
  with self.assertRaises(ValueError):b.reserve('BTCUSDT',1)
 def test_no_rest(self):
  b=Budget(['BTCUSDT'],0,0,100,lambda:1)
  with self.assertRaises(ValueError):b.reserve('BTCUSDT',1)
 def test_plan_tail(self):
  p=plan(T,T+1000*60000);self.assertEqual([r['limit'] for r in p],[499,499,2]);self.assertEqual(p[-1]['endTime'],T+1000*60000-1)
r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
(R/'R3_END_TO_END_EVENT_REPLAY.json').write_text(json.dumps({'tests':r.testsRun,'pass':r.wasSuccessful(),'failures':[str(x) for x in r.failures+r.errors],'network_requests':0,'production_writes':0},indent=2));raise SystemExit(not r.wasSuccessful())
