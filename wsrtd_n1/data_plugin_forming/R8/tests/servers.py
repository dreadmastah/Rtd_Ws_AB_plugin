import socket,threading,ssl,time,base64,hashlib,struct,json
class Server:
 def __init__(self,mode='http',body=b'{}',cert=None,key=None):
  self.mode=mode;self.body=body;self.count=0;self.requests=[];self.active=set();self.stop=threading.Event();self.threads=[]
  self.s=socket.socket();self.s.bind(('127.0.0.1',0));self.port=self.s.getsockname()[1]
  assert self.port not in (10101,18101)
  self.s.listen();self.s.settimeout(.1);self.context=None
  if cert:
   self.context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);self.context.load_cert_chain(cert,key)
  self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
 def run(self):
  while not self.stop.is_set():
   try:c,_=self.s.accept()
   except (TimeoutError,OSError):continue
   self.count+=1;self.active.add(c);t=threading.Thread(target=self.handle,args=(c,),daemon=True);self.threads.append(t);t.start()
 def handle(self,c):
  original=c
  try:
   c.settimeout(1)
   if self.context:c=self.context.wrap_socket(c,server_side=True)
   buf=b''
   while not buf.endswith(b'\r\n\r\n'):
    b=c.recv(1)
    if not b:return
    buf+=b
    if len(buf)>8192:return
   self.requests.append(buf.decode())
   if self.mode=='timeout':self.stop.wait(1.5);return
   if self.mode=='redirect':c.sendall(b'HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1:18101/\r\nContent-Length: 0\r\n\r\n');return
   if self.mode=='broken':return
   if self.mode.startswith('ws'):
    key=[x.split(':',1)[1].strip() for x in buf.decode().split('\r\n') if x.lower().startswith('sec-websocket-key:')][0]
    accept=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
    if self.mode=='ws_bad':accept=b'bad'
    c.sendall(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: '+accept+b'\r\n\r\n')
    if self.mode=='ws_bad':return
    # Receive actual masked subscription.
    for _ in range(0 if self.mode.startswith('ws_raw') else 2 if self.mode=='ws_two' else 1):
     h=c.recv(2)
     if len(h)!=2:return
     n=h[1]&127;mask=c.recv(4);data=b''
     while len(data)<n:
      chunk=c.recv(n-len(data))
      if not chunk:return
      data+=chunk
     self.requests.append(bytes(v^mask[i%4] for i,v in enumerate(data)).decode())
    if self.mode=='ws_oversize':c.sendall(b'\x81\x7e'+struct.pack('!H',17000));self.stop.wait(.2);return
    if self.mode=='ws_quiet':self.stop.wait(2);return
    if self.mode=='ws_ping':c.sendall(b'\x89\x01p')
    if self.mode=='ws_raw_oversize':c.sendall(b'\x81\x7e'+struct.pack('!H',17000));self.stop.wait(.2);return
    if self.mode=='ws_raw_fragment':c.sendall(b'\x01\x02{}');self.stop.wait(.2);return
    if self.mode in ('ws_raw_ping','ws_raw_flood'):
     for _ in range(6 if self.mode=='ws_raw_flood' else 1):
      c.sendall(b'\x89\x01p');reply=c.recv(7)
      if len(reply)!=7:return
      self.requests.append('PONG:'+str(reply[0]))
    bodies=self.body if isinstance(self.body,list) else [self.body]
    for body in bodies:
     prefix=bytes([0x81,len(body)]) if len(body)<126 else b'\x81\x7e'+struct.pack('!H',len(body))
     c.sendall(prefix+body)
    self.stop.wait(.3);return
   c.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: '+str(len(self.body)).encode()+b'\r\n\r\n'+self.body)
  except (OSError,ValueError):pass
  finally:
   c.close();self.active.discard(original)
 def close(self):
  self.stop.set();self.s.close()
  for c in list(self.active):
   try:c.shutdown(socket.SHUT_RDWR)
   except OSError:pass
   c.close()
  self.thread.join(2)
  for t in self.threads:t.join(2)
