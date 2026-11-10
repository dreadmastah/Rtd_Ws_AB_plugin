import sys,pathlib,unittest,json,hashlib,ssl,os,types,socket,threading,base64
R=pathlib.Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'src'),str(R/'tests'),str(R/'independent')]
from test_socket import Tests as Base
from network import Backend,Endpoint
from servers import Server
from custody import Attestation
from handoff import Handoff
from admission import Refused
from controller import ControlledSession
class Edges(Base):
 def test_controller_identity_and_flow(self):
  a=Attestation(os.getpid());identity=a.check();a.close()
  old,s,_,c=self.setup('ws',receiver_creation=identity['creation']);old.close()
  digest=hashlib.sha256(json.dumps(c,sort_keys=True,separators=(',',':')).encode()).hexdigest()
  with self.assertRaises(Refused):ControlledSession(old.control,old.endpoint,identity,dict(identity,pid=identity['pid']+1),digest)
  self.assertEqual(s.count,0)
  session=ControlledSession(old.control,old.endpoint,identity,identity,digest);self.objects.append(session)
  session.start();self.assertEqual(session.read(),b'{}');self.assertEqual(s.count,1)
 def test_ping_pong_real_socket(self):
  b,_,_,_=self.setup();listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen();port=listener.getsockname()[1];self.assertNotIn(port,(10101,18101));seen=[]
  def server():
   c,_=listener.accept();c.settimeout(2)
   try:
    raw=b''
    while not raw.endswith(b'\r\n\r\n'):raw+=c.recv(1)
    key=[x.split(':',1)[1].strip() for x in raw.decode().split('\r\n') if x.startswith('Sec-WebSocket-Key:')][0]
    accept=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
    c.sendall(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: '+accept+b'\r\n\r\n')
    def frame():
     head=c.recv(2);n=head[1]&127;mask=c.recv(4);data=b''
     while len(data)<n:data+=c.recv(n-len(data))
     return head[0],bytes(v^mask[i%4] for i,v in enumerate(data))
    frame();c.sendall(b'\x89\x03abc');seen.append(frame());c.sendall(b'\x81\x02{}')
   finally:c.close()
  thread=threading.Thread(target=server);thread.start();b.endpoint=Endpoint(port)
  try:b.connect_ws();b.subscribe('BTCUSDT');self.assertEqual(b.receive(),b'{}');thread.join(3);self.assertEqual(seen,[(0x8a,b'abc')])
  finally:b.close();listener.close();thread.join(3)
 def test_tls_trusted(self):self.tls('localhost',True)
 def test_tls_wrong_hostname(self):self.tls('wrong.local',False)
 def tls(self,host,success):
  old,_,_,_=self.setup();old.close();s=Server(cert=str(R/'disposable/tls/cert.pem'),key=str(R/'disposable/tls/key.pem'));self.objects.append(s)
  b=Backend(old.control,old.bindings,Endpoint(s.port,True,host,str(R/'disposable/tls/cert.pem')));self.objects.append(b)
  if success:self.assertEqual(b.http('metadata'),b'{}')
  else:
   with self.assertRaises(ssl.SSLCertVerificationError):b.http('metadata')
  self.assertFalse(b.sockets);self.assertEqual(s.count,1)
 def test_custody_exact_and_mismatch(self):
  a=Attestation(os.getpid());self.objects.append(a);identity=a.check();b=Attestation(os.getpid(),identity);self.objects.append(b)
  for field,value in [('creation',identity['creation']+1),('sha256','0'*64),('path','wrong')]:
   with self.assertRaises(ValueError):Attestation(os.getpid(),dict(identity,**{field:value}))
 def test_handoff_current_authority_and_subscription(self):
  for mode in ['changed_session','unsubscribed','duplicate']:
   cfg=dict(producer_session='a',universe_version='b',symbols=['BTCUSDT'])
   p=types.SimpleNamespace(session='a',universe='b',receiver=types.SimpleNamespace(symbols=frozenset(['BTCUSDT'])))
   called=[];p.encode=lambda raw:called.append(raw);p.receive=lambda packet:'OK'
   b=types.SimpleNamespace(control=types.SimpleNamespace(c=cfg),subscribed={'BTCUSDT'},shutdown=lambda:called.append('closed'),receive=lambda:b'{"s":"BTCUSDT"}')
   h=Handoff(b,p)
   if mode=='changed_session':p.session='c'
   elif mode=='unsubscribed':b.subscribed.clear()
   else:b.receive=lambda:b'{"s":"BTCUSDT","s":"BTCUSDT"}'
   with self.assertRaises(Refused):h.receive_one()
   self.assertEqual(called,['closed'])
if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Edges))
 (R/'independent/final_edges_results.json').write_text(json.dumps(dict(passed=result.wasSuccessful(),tests=result.testsRun,failures=[(str(t),e) for t,e in result.failures+result.errors],source_hashes={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (R/'src').glob('*.py')},external_requests=0,production_changes=0),indent=2));sys.exit(not result.wasSuccessful())
