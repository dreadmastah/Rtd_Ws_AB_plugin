import pathlib,sys,tempfile,secrets,json,time,os,unittest,hashlib
R=pathlib.Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'src'),str(R/'tests')]
from admission import Controller,Refused
from network import Backend,Endpoint
from servers import Server
class Tests(unittest.TestCase):
 def setUp(self):self.objects=[]
 def tearDown(self):
  for x in reversed(self.objects):x.close()
 def setup(self,mode='http',**caps):
  now=time.time_ns()//1000000;c=dict(authority=secrets.token_hex(16),producer_session=secrets.token_hex(16),receiver_session=secrets.token_hex(16),symbols=['BTCUSDT'],universe_version='a'*64,start_ms=now,end_ms=now+120000,rest_requests=2,rest_weight=4,connection_attempts=4,subscriptions=2,reconnects=0,max_frames=20,max_bytes=100000,receiver_pid=os.getpid(),receiver_creation=123);c.update(caps)
  s=Server(mode);self.objects.append(s);p=pathlib.Path(tempfile.mkdtemp(prefix='independent_',dir=R/'disposable'))/'ledger.sqlite';Controller.provision(p,c);ctl=Controller(p,c);self.objects.append(ctl)
  bind={k:c[k] for k in ('producer_session','receiver_session','receiver_pid','receiver_creation')};b=Backend(ctl,bind,Endpoint(s.port));self.objects.append(b);return b,s,p,c
 def test_http_exact_count(self):
  b,s,_,_=self.setup(rest_requests=1);self.assertEqual(b.http('metadata'),b'{}')
  with self.assertRaises(Refused):b.http('metadata')
  self.assertEqual(s.count,1);self.assertFalse(b.sockets)
 def test_zero_rest_zero_connections(self):
  b,s,_,_=self.setup(rest_requests=0,rest_weight=0)
  with self.assertRaises(Refused):b.http('metadata')
  self.assertEqual(s.count,0)
 def test_redirect_no_follow(self):
  b,s,_,_=self.setup('redirect')
  with self.assertRaises(Refused):b.http('metadata')
  self.assertEqual(s.count,1);self.assertFalse(b.sockets)
 def test_failure_no_retry(self):
  b,s,_,_=self.setup('broken')
  with self.assertRaises(EOFError):b.http('metadata')
  time.sleep(.1);self.assertEqual(s.count,1)
 def test_timeout_cleanup(self):
  b,s,_,_=self.setup('timeout');start=time.monotonic()
  with self.assertRaises((TimeoutError,OSError)):b.http('metadata')
  self.assertLess(time.monotonic()-start,1.5);self.assertFalse(b.sockets);self.assertEqual(s.count,1)
 def test_ws_restart_no_reconnect_bypass(self):
  b,s,p,c=self.setup('ws_quiet',reconnects=0);b.connect_ws();b.close()
  ctl=Controller(p,c);self.objects.append(ctl);n=Backend(ctl,b.bindings,b.endpoint);self.objects.append(n)
  with self.assertRaises(Refused):n.connect_ws(False)
  self.assertEqual(s.count,1)
 def test_http_not_ws_reconnect(self):
  b,s,p,c=self.setup('http',reconnects=0);b.http('metadata');b.close()
  # HTTP debit must not itself prohibit the first separately admitted WS attempt.
  ctl=Controller(p,c);self.objects.append(ctl);n=Backend(ctl,b.bindings,b.endpoint);self.objects.append(n)
  with self.assertRaises(Refused):n.connect_ws(False) # HTTP server rejects upgrade, not pre-dispatch policy.
  self.assertEqual(s.count,2)
 def test_subscription_refusal_closes(self):
  b,s,_,_=self.setup('ws_quiet',subscriptions=1);b.connect_ws();b.subscribe('BTCUSDT')
  with self.assertRaises(Refused):b.subscribe('BTCUSDT')
  self.assertFalse(b.sockets);self.assertEqual(s.count,1)
 def test_oversized_body_before_read(self):
  b,s,_,_=self.setup('ws_oversize');b.connect_ws();b.subscribe('BTCUSDT')
  with self.assertRaises(Refused):b.receive()
  self.assertFalse(b.sockets)
 def test_quiet_expiry_closes(self):
  now=time.time_ns()//1000000;b,s,_,_=self.setup('ws_quiet',end_ms=now+700);b.connect_ws();time.sleep(.9)
  self.assertTrue(b.closed.is_set());self.assertFalse(b.sockets)
 def test_protected_endpoint_denied(self):
  for port in (10101,18101):
   with self.assertRaises(Refused):Endpoint(port)
 def test_corrupt_budget_no_dispatch(self):
  b,s,_,_=self.setup();b.control.db.execute('UPDATE state SET connections=-1')
  with self.assertRaises(Refused):b.http('metadata')
  self.assertEqual(s.count,0)
if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 (R/'independent/socket_results.json').write_text(json.dumps({'passed':result.wasSuccessful(),'tests':result.testsRun,'failures':[(str(t),e) for t,e in result.failures+result.errors],'source_hashes':{p:hashlib.sha256((R/p).read_bytes()).hexdigest() for p in ['src/admission.py','src/network.py']},'actual_loopback':True,'external_requests':0,'production_changes':0},indent=2));sys.exit(not result.wasSuccessful())
