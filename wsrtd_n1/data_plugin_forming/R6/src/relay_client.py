import subprocess,sys,json,secrets,socket,threading,queue
from pathlib import Path
from custody import Attestation
from relay import pack,unpack,read,send,Validator,encode
class RelayClient:
 def __init__(self,pipeline,root):
  self.p=self.owner=self.sender=self.receiver=None;self.pipeline=pipeline
  try:self._initialize(pipeline,root)
  except BaseException:self.close();raise
 def _initialize(self,pipeline,root):
  self.pipeline=pipeline;self.key=pipeline.key;self.sequence=0
  self.c=dict(session=pipeline.session,receiver=secrets.token_hex(16),generation=secrets.token_hex(16),universe=pipeline.universe,symbols=sorted(pipeline.receiver.symbols))
  self.p=subprocess.Popen([sys.executable,'-B',str(Path(__file__).with_name('relay.py'))],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  self.owner=Attestation(self.p.pid);self.identity=self.owner.check()
  self.p.stdin.write(json.dumps(dict(self.c,key=self.key.hex(),ledger=str(root/('relay_'+secrets.token_hex(8)+'.sqlite'))))+'\n');self.p.stdin.flush();self.p.stdin.close()
  readyq=queue.Queue(maxsize=1)
  def getready():readyq.put(self.p.stdout.readline())
  reader=threading.Thread(target=getready,daemon=True);reader.start()
  ready=json.loads(readyq.get(timeout=5));self.port=ready['port']
  if self.port in (10101,18101):raise ValueError('protected endpoint')
  self.sender=socket.create_connection(('127.0.0.1',self.port),timeout=3)
  send(self.sender,pack(dict(role='sender',generation=self.c['generation']),self.key))
  self.receiver=socket.create_connection(('127.0.0.1',self.port),timeout=3)
  send(self.receiver,pack(dict(role='receiver',generation=self.c['generation']),self.key))
  self.validation=Validator(self.c,self.key);self.receipts=[]
 def deliver(self,raw):
  try:return self._deliver(raw)
  except BaseException:
   self.pipeline.receiver.disconnect()
   raise
 def _deliver(self,raw):
  self.owner.check();self.sequence+=1;b=encode(raw,self.c,self.key,self.sequence);send(self.sender,b)
  received=read(self.receiver);o,packet=self.validation.validate(received)
  if received!=b:raise ValueError('relay changed source packet')
  result=self.pipeline.receive(packet)
  if result.startswith('INVALID'):raise ValueError(result)
  ack=dict(ack=o['sequence'],receipt=o['receipt']);send(self.receiver,pack(ack,self.key))
  if unpack(read(self.sender),self.key)!=ack:raise ValueError('ack mismatch')
  self.owner.check();self.receipts.append(dict(sequence=o['sequence'],receipt=o['receipt'],result=result));return result
 def close(self):
  for name in ('sender','receiver'):
   s=getattr(self,name)
   if s:
    try:s.shutdown(socket.SHUT_RDWR)
    except OSError:pass
    s.close();setattr(self,name,None)
  self.pipeline.receiver.disconnect()
  try:
   if self.p:
    try:self.p.wait(timeout=6)
    except subprocess.TimeoutExpired:
     # Only the exact test-owned Popen process handle, never a production PID/tree.
     self.p.terminate();self.p.wait(timeout=3)
    for stream in (self.p.stdin,self.p.stdout,self.p.stderr):
     if stream and not stream.closed:stream.close()
  finally:
   if self.owner:self.owner.close();self.owner=None
