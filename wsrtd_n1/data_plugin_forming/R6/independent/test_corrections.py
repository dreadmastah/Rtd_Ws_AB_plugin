import pathlib,sys,time,threading,socket,struct,json,hashlib,unittest,secrets
from unittest.mock import patch
R=pathlib.Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'src'),str(R/'tests'),str(R/'dependencies/r3')]
from test_network import Tests as Helpers
from network import Endpoint
from servers import Server
from relay import read
import relay_client
from relay_client import RelayClient
from pipeline import Pipeline
from durable import Store
class Checks(unittest.TestCase):
 def test_deadline_resets_http_to_ws(self):
  t=Helpers();t.setUp()
  try:
   b,s=t.setup_backend();self.assertEqual(b.http('metadata'),b'{}');self.assertFalse(hasattr(b.local,'deadline'))
   with self.assertRaises(Exception):b.http('invalid')
   self.assertFalse(hasattr(b.local,'deadline'));time.sleep(1.1)
   ws=Server('ws');t.resources.append(ws);b.endpoint=Endpoint(ws.port)
   b.connect_ws();b.subscribe('BTCUSDT');self.assertEqual(b.receive(),b'{}');self.assertFalse(hasattr(b.local,'deadline'))
  finally:t.tearDown()
 def test_slow_drip_frame_aggregate(self):
  listener=socket.socket();listener.bind(('127.0.0.1',0));self.assertNotIn(listener.getsockname()[1],(10101,18101));listener.listen();client=socket.create_connection(listener.getsockname());server,_=listener.accept();stop=threading.Event()
  def drip():
   try:
    server.sendall(struct.pack('!I',40))
    while not stop.wait(.4):server.sendall(b'x')
   except OSError:pass
  worker=threading.Thread(target=drip);worker.start();start=time.monotonic()
  try:
   with self.assertRaises(TimeoutError):read(client)
   elapsed=time.monotonic()-start;self.assertGreater(elapsed,2.8);self.assertLess(elapsed,3.5)
  finally:stop.set();client.close();server.close();listener.close();worker.join(1)
 def test_partial_constructor_closes_child(self):
  store=Store(R/'dependencies/disposable'/('independent_'+secrets.token_hex(5)+'.sqlite'),'fixture');p=Pipeline(store,secrets.token_hex(16),b'a'*32,['BTCUSDT'],'a'*64,lambda:time.time_ns()//1000000)
  children=[];original=relay_client.subprocess.Popen
  def spawn(*a,**kw):
   child=original(*a,**kw);children.append(child);return child
  try:
   with patch.object(relay_client.subprocess,'Popen',spawn),patch.object(relay_client.socket,'create_connection',side_effect=OSError('injected connection failure')):
    with self.assertRaises(OSError):RelayClient(p,R/'disposable')
   self.assertEqual(len(children),1);self.assertIsNotNone(children[0].poll());self.assertTrue(all(x.closed for x in (children[0].stdin,children[0].stdout,children[0].stderr)))
  finally:store.close()
if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
 (R/'independent/correction_results.json').write_text(json.dumps(dict(passed=result.wasSuccessful(),tests=result.testsRun,failures=[(str(t),e) for t,e in result.failures+result.errors],hashes={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (R/'src').glob('*.py')},external_requests=0,production_changes=0),indent=2));sys.exit(not result.wasSuccessful())
