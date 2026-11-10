import pathlib,sys,tempfile,json,unittest,hashlib,threading,concurrent.futures
R=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from admission import Controller,Refused
class Tests(unittest.TestCase):
 def setUp(self):
  self.path=pathlib.Path(tempfile.mkdtemp(prefix='independent_',dir=R/'disposable'))/'admission.sqlite'
  self.now=[1000];self.mono=[0]
  self.c={'authority':'a'*32,'producer_session':'b'*32,'receiver_session':'c'*32,'symbols':['BTCUSDT'],'universe_version':'d'*64,'start_ms':1000,'end_ms':121000,'rest_requests':2,'rest_weight':4,'connection_attempts':2,'subscriptions':2,'reconnects':1,'max_frames':4,'max_bytes':400,'receiver_pid':123,'receiver_creation':456}
  Controller.provision(self.path,self.c);self.ctrl=self.open()
 def open(self,c=None):return Controller(self.path,c or self.c,clock=lambda:self.now[0],monotonic=lambda:self.mono[0])
 def tearDown(self):self.ctrl.close()
 def reserve(self,kind,ctrl=None,**kw):
  args={k:self.c[k] for k in ('producer_session','receiver_session','receiver_pid','receiver_creation')};args.update(kw)
  return (ctrl or self.ctrl).reserve(kind,**args)
 def test_rest_persistent_restart(self):
  self.reserve('REST_KLINE',symbol='BTCUSDT',limit=499);self.ctrl.close();self.ctrl=self.open();self.reserve('REST_KLINE',symbol='BTCUSDT',limit=499)
  with self.assertRaises(Refused):self.reserve('REST_METADATA')
 def test_stop_persistent_restart(self):
  self.ctrl.stop('operator');self.ctrl.close();self.ctrl=self.open()
  with self.assertRaises(Refused):self.reserve('HEALTH')
 def test_wrong_session_latches_stop(self):
  with self.assertRaises(Refused):self.reserve('HEALTH',producer_session='f'*32)
  with self.assertRaises(Refused):self.reserve('HEALTH')
 def test_receiver_identity(self):
  with self.assertRaises(Refused):self.reserve('WS_CONNECT',receiver_creation=457)
 def test_ws_reconnect_count(self):
  self.reserve('WS_CONNECT');self.reserve('WS_CONNECT',reconnect=True)
  with self.assertRaises(Refused):self.reserve('WS_CONNECT',reconnect=True)
 def test_second_connect_not_initial(self):
  self.reserve('WS_CONNECT')
  with self.assertRaises(Refused):self.reserve('WS_CONNECT')
 def test_subscriptions_cap(self):
  self.reserve('SUBSCRIBE',symbol='BTCUSDT');self.reserve('SUBSCRIBE',symbol='BTCUSDT')
  with self.assertRaises(Refused):self.reserve('SUBSCRIBE',symbol='BTCUSDT')
 def test_frame_bytes_cap(self):
  self.reserve('FRAME',bytes_count=400)
  with self.assertRaises(Refused):self.reserve('FRAME',bytes_count=1)
 def test_clock_rollback(self):
  self.now[0]=2000;self.reserve('HEALTH');self.now[0]=1999
  with self.assertRaises(Refused):self.reserve('HEALTH')
 def test_monotonic_deadline(self):
  self.mono[0]=120
  with self.assertRaises(Refused):self.reserve('HEALTH')
 def test_wall_deadline(self):
  self.now[0]=121000
  with self.assertRaises(Refused):self.reserve('HEALTH')
 def test_allowlist(self):
  with self.assertRaises(Refused):self.reserve('REST_KLINE',symbol='ETHUSDT',limit=1)
 def test_wrong_contract_no_rebind(self):
  changed=dict(self.c);changed['rest_requests']=3
  with self.assertRaises(Refused):self.open(changed)
 def test_no_reprovision(self):
  with self.assertRaises(Refused):Controller.provision(self.path,self.c)
 def test_nan_contract(self):
  c=dict(self.c);c['rest_requests']=float('nan')
  with self.assertRaises(Refused):self.open(c)
 def test_concurrent_cannot_overconsume(self):
  def attempt(_):
   try:self.reserve('REST_METADATA');return True
   except Refused:return False
  with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:r=list(pool.map(attempt,range(8)))
  self.assertEqual(sum(r),2)
 def test_failures_not_refunded(self):
  self.reserve('REST_METADATA');self.reserve('REST_METADATA')
  # Simulated dispatch failure deliberately does not mutate the persisted budget.
  with self.assertRaises(Refused):self.reserve('REST_METADATA')
 def test_corrupt_negative_counter_rejected(self):
  self.ctrl.db.execute('UPDATE state SET rest=-20 WHERE id=1')
  with self.assertRaises(Refused):self.reserve('REST_METADATA')
 def test_corrupt_fractional_counter_rejected(self):
  self.ctrl.db.execute('UPDATE state SET connections=0.5 WHERE id=1')
  with self.assertRaises(Refused):self.reserve('HEALTH')
if __name__=='__main__':
 r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 (R/'independent/admission_results.json').write_text(json.dumps({'passed':r.wasSuccessful(),'tests':r.testsRun,'failures':[(str(t),e) for t,e in r.failures+r.errors],'source_sha256':hashlib.sha256((R/'src/admission.py').read_bytes()).hexdigest(),'network_calls':0,'production_changes':0},indent=2))
 sys.exit(not r.wasSuccessful())
