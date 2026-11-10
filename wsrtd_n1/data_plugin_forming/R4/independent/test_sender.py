import pathlib,sys,tempfile,json,unittest,hashlib
R=pathlib.Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'src'),str(R/'dependencies/r3')]
from admission import Controller,Refused
from sender import Sender,FixtureBackend,IsolatedRelay
from pipeline import Pipeline
from durable import Store
T=1800057600000
class Tests(unittest.TestCase):
 def setUp(self):
  self.now=[T+1000];self.c={'authority':'a'*32,'producer_session':'b'*32,'receiver_session':'c'*32,'symbols':['BTCUSDT'],'universe_version':'d'*64,'start_ms':T,'end_ms':T+120000,'rest_requests':0,'rest_weight':0,'connection_attempts':2,'subscriptions':2,'reconnects':1,'max_frames':100,'max_bytes':100000,'receiver_pid':123,'receiver_creation':456}
  self.path=pathlib.Path(tempfile.mkdtemp(prefix='independent_sender_',dir=R/'disposable'))/'admission.sqlite';Controller.provision(self.path,self.c)
  self.ctl=Controller(self.path,self.c,lambda:self.now[0],lambda:0);self.backend=FixtureBackend()
  self.bind={k:self.c[k] for k in ('producer_session','receiver_session','receiver_pid','receiver_creation')};self.sender=Sender(self.ctl,self.backend,self.bind)
  self.dbpath=pathlib.Path(tempfile.mkdtemp(prefix='independent_sender_',dir=R/'dependencies/disposable'))/'history.sqlite';self.store=Store(self.dbpath,'fixture')
  self.pipe=Pipeline(self.store,self.c['producer_session'],b'k'*32,['BTCUSDT'],self.c['universe_version'],lambda:self.now[0]);self.sender.connect();self.sender.subscribe('BTCUSDT')
 def tearDown(self):self.store.close();self.ctl.close()
 def raw(self,final=False):return {'e':'kline','s':'BTCUSDT','E':self.now[0],'st':'UM','k':{'s':'BTCUSDT','i':'1m','t':T,'T':T+59999,'o':'10','h':'12','l':'9','c':'11','v':'2','q':'22','n':2,'x':final,'f':45,'L':46}}
 def test_no_rest_history_dispatch(self):
  before=len(self.backend.calls)
  with self.assertRaises(Refused):self.sender.history('BTCUSDT',T,T+59999,1)
  self.assertEqual(before,len(self.backend.calls));self.assertTrue(self.backend.closed)
 def test_backend_replacement_rejected(self):
  class Other(FixtureBackend):pass
  with self.assertRaises(Refused):Sender(self.ctl,Other(),self.bind)
 def test_exact_metadata_roundtrip(self):
  raw=self.raw();packet=self.sender.source_event(json.dumps(raw).encode(),self.pipe)
  self.assertEqual(json.loads(packet[32:])['source_event'],raw);self.assertEqual(IsolatedRelay(self.ctl,self.bind).forward(packet,self.pipe),'ACCEPTED')
 def test_final_durable_linkage(self):
  self.now[0]=T+61000;raw=self.raw(True);packet=self.sender.source_event(json.dumps(raw).encode(),self.pipe)
  self.assertEqual(IsolatedRelay(self.ctl,self.bind).forward(packet,self.pipe),'DURABLE_FINALIZED:COMMITTED');self.assertEqual(len(self.store.rows('BTCUSDT',True)),1)
  receipt=json.loads(self.store.db.execute('SELECT envelope_json FROM receipts').fetchone()[0]);self.assertEqual(receipt['source_event'],raw)
 def test_duplicate_json_finality_rejected(self):
  data=json.dumps(self.raw()).replace('"x": false','"x": true, "x": false').encode()
  with self.assertRaises((Refused,ValueError)):self.sender.source_event(data,self.pipe)
 def test_nonobject_rejected(self):
  with self.assertRaises((Refused,ValueError)):self.sender.source_event(b'[]',self.pipe)
 def test_pipeline_session_binding(self):
  self.pipe.session='e'*32
  with self.assertRaises(Refused):self.sender.source_event(json.dumps(self.raw()).encode(),self.pipe)
 def test_pipeline_universe_binding(self):
  self.pipe.universe='f'*64
  with self.assertRaises(Refused):self.sender.source_event(json.dumps(self.raw()).encode(),self.pipe)
 def test_relay_frame_size(self):
  with self.assertRaises(Refused):IsolatedRelay(self.ctl,self.bind).forward(b'x'*16417,self.pipe)
 def test_expired_frame_stops(self):
  self.now[0]=T+120000
  with self.assertRaises(Refused):self.sender.source_event(json.dumps(self.raw()).encode(),self.pipe)
  self.assertTrue(self.backend.closed)
if __name__=='__main__':
 r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 (R/'independent/sender_results.json').write_text(json.dumps({'passed':r.wasSuccessful(),'tests':r.testsRun,'failures':[(str(t),e) for t,e in r.failures+r.errors],'source_sha256':hashlib.sha256((R/'src/sender.py').read_bytes()).hexdigest(),'network_calls':0,'production_changes':0},indent=2));sys.exit(not r.wasSuccessful())
