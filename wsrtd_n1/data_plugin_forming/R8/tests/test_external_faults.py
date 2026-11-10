from external_fixture import *
from unittest.mock import patch
from external_resolver import resolve
import ssl,socket,subprocess
rows=[]
for mode in ('ws_raw_ping','ws_raw_flood','ws_raw_oversize','ws_raw_fragment','untrusted','wrong_hostname','dns_timeout','late_dns','connection_refused','frame_budget'):
 s=Server(mode if mode.startswith('ws_raw') else 'ws_raw',b'{}',cert=str(R/'disposable/tls/cert.pem'),key=str(R/'disposable/tls/key.pem'));m=manifest(s.port)
 if mode=='untrusted':m['cafile']=str(R/'disposable/tls/unrelated.pem')
 if mode=='frame_budget':m['contract']['max_frames']=0
 if mode=='late_dns':m['contract']['end_ms']=time.time_ns()//1000000+400
 digest=hashlib.sha256(canonical(m)).hexdigest();path=R/'disposable'/('fault_'+secrets.token_hex(5)+'.sqlite');Controller.provision(path,m['contract']);ctl=Controller(path,m['contract']);b=ExternalWS(ctl,m,digest,True);error=None;start=time.monotonic()
 try:
  if mode=='dns_timeout':
   with patch('external.resolve',side_effect=lambda *args:resolve('localhost',s.port,['127.0.0.1'],time.monotonic()+.1,True,2)):b.connect_ws()
  elif mode=='late_dns':
   with patch('external.resolve',side_effect=lambda *args:(time.sleep(.6),'127.0.0.1')[1]):
    b.connect_ws()
  elif mode=='wrong_hostname':
   original=ssl.SSLContext.wrap_socket
   def wrong(ctx,*args,**kwargs):kwargs['server_hostname']='wrong.local';return original(ctx,*args,**kwargs)
   with patch.object(ssl.SSLContext,'wrap_socket',wrong):b.connect_ws()
  elif mode=='connection_refused':s.close();b.connect_ws()
  else:b.connect_ws();b.receive()
  assert mode=='ws_raw_ping'
 except (Refused,TimeoutError,OSError,ValueError,EOFError) as e:
  error=type(e).__name__+':'+str(e);assert mode!='ws_raw_ping',error
 finally:b.close();ctl.close();s.close()
 assert not b.sockets and not b.watch.is_alive()
 if mode in ('dns_timeout','late_dns'):assert s.count==0
 rows.append(dict(case=mode,passed=True,error=error,seconds=time.monotonic()-start,server_connections=s.count,pongs=sum(str(x).startswith('PONG:138') for x in s.requests),cleanup=True))
(R/'R8_DNS_TLS_WS_ENFORCEMENT.json').write_text(json.dumps(dict(passed=True,cases=rows,external_connections=0,limitations=['OS subprocess termination and fsync not hard real-time','wrong-host test injects TLS SNI solely for negative fixture','late DNS successful result injected after real UTC expiry; zero socket dispatch']),indent=2));print('10 TLS/WS/DNS fault cases PASS')
