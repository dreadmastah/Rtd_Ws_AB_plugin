"""R6 independent loopback V3 relay. Fixture custody only; no production dialing."""
import sys,json,struct,socket,hmac,hashlib,base64,time,sqlite3,secrets
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'dependencies/r3'))
from transport import Receiver,envelope,canonical,signed
MAX=24000
def recv(s,n,deadline):
 out=b''
 while len(out)<n:
  remaining=deadline-time.monotonic()
  if remaining<=0:raise TimeoutError('aggregate frame deadline')
  s.settimeout(remaining);b=s.recv(n-len(out))
  if not b:raise EOFError('truncated frame')
  out+=b
 return out
def read(s):
 deadline=time.monotonic()+3
 n=struct.unpack('!I',recv(s,4,deadline))[0]
 if not 32<n<=MAX:raise ValueError('frame size')
 return recv(s,n,deadline)
def send(s,b):
 if not 32<len(b)<=MAX:raise ValueError('frame size')
 s.sendall(struct.pack('!I',len(b))+b)
def pack(o,key):
 b=canonical(o);return hmac.digest(key,b,'sha256')+b
def unpack(b,key):
 if not hmac.compare_digest(b[:32],hmac.digest(key,b[32:],'sha256')):raise ValueError('MAC')
 o=json.loads(b[32:],object_pairs_hook=Receiver._pairs)
 if canonical(o)!=b[32:]:raise ValueError('canonical')
 return o
def encode(raw,c,key,sequence):
 e=envelope(raw,c['session'],int(time.time()*1000),{s:('UM','PERPETUAL') for s in c['symbols']})
 packet=pack(dict(schema_version=3,universe_version=c['universe'],source_event=raw,candle=e),key)
 return pack(dict(schema=3,session=c['session'],receiver=c['receiver'],generation=c['generation'],sequence=sequence,receipt=secrets.token_hex(16),packet=base64.b64encode(packet).decode()),key)
class Validator:
 def __init__(self,c,key):
  self.c=c;self.key=key;self.last=0
  self.receiver=Receiver(c['session'],key,c['symbols'])
 def validate(self,b):
  o=unpack(b,self.key)
  if set(o)!={'schema','session','receiver','generation','sequence','receipt','packet'}:raise ValueError('outer schema')
  if type(o['schema'])is not int or o['schema']!=3 or any(o[k]!=self.c[k] for k in ('session','receiver','generation')):raise ValueError('session generation')
  if type(o['sequence'])is not int or o['sequence']!=self.last+1:raise ValueError('sequence/replay')
  if not isinstance(o['receipt'],str) or len(o['receipt'])!=32 or any(x not in '0123456789abcdef' for x in o['receipt']):raise ValueError('receipt')
  p=base64.b64decode(o['packet'],validate=True);v=unpack(p,self.key)
  if set(v)!={'schema_version','universe_version','source_event','candle'} or type(v['schema_version'])is not int or v['schema_version']!=3 or v['universe_version']!=self.c['universe']:raise ValueError('V3 identity')
  e=v['candle'];expected=envelope(v['source_event'],self.c['session'],e['local_receipt_time_utc'],{s:('UM','PERPETUAL') for s in self.c['symbols']})
  if canonical(e)!=canonical(expected):raise ValueError('source linkage')
  result=self.receiver.ingest(signed(e,self.key))
  if result.startswith('INVALID'):raise ValueError(result)
  self.last=o['sequence'];return o,p
def main():
 c=json.loads(sys.stdin.readline());key=bytes.fromhex(c.pop('key'));root=Path(__file__).resolve().parents[1]/'disposable';path=Path(c.pop('ledger')).resolve()
 if root not in path.parents or path.exists():raise ValueError('new relay generation ledger required')
 db=sqlite3.connect(path);db.execute('PRAGMA synchronous=FULL');db.execute('CREATE TABLE seen(receipt TEXT PRIMARY KEY, seq INTEGER UNIQUE, hash TEXT)');db.commit()
 listener=socket.socket();listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
 if port in (10101,18101):raise ValueError('protected port')
 listener.listen(2);listener.settimeout(5);print(json.dumps({'port':port}),flush=True)
 sockets=[]
 try:
  # Roles are authenticated by a secret inherited through the controller-owned stdin pipe.
  roles={}
  for _ in range(2):
   s,_=listener.accept();s.settimeout(3);sockets.append(s);hello=unpack(read(s),key)
   if set(hello)!={'role','generation'} or hello['generation']!=c['generation'] or hello['role'] not in ('sender','receiver') or hello['role'] in roles:raise ValueError('role binding')
   roles[hello['role']]=s
  v=Validator(c,key)
  while True:
   b=read(roles['sender']);o,p=v.validate(b)
   db.execute('INSERT INTO seen VALUES(?,?,?)',(o['receipt'],o['sequence'],hashlib.sha256(b).hexdigest()));db.commit()
   send(roles['receiver'],b)
   ack=unpack(read(roles['receiver']),key)
   if ack!={'ack':o['sequence'],'receipt':o['receipt']}:raise ValueError('receiver ack')
   send(roles['sender'],pack(ack,key))
 except (EOFError,TimeoutError,ValueError,OSError,sqlite3.Error) as e:
  print(json.dumps({'stopped':type(e).__name__,'reason':str(e)}),flush=True)
 finally:
  for s in sockets:s.close()
  listener.close();db.close()
if __name__=='__main__':main()
