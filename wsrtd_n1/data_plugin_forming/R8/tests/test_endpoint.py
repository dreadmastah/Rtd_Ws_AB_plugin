from pathlib import Path
import sys,json,secrets,dataclasses,socket
from unittest.mock import patch
R=Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'src'),str(R/'tests')]
from test_network import contract
from endpoint_policy import Policy,PolicyBackend
from admission import Controller,Refused
from servers import Server
cert=R/'disposable/tls/cert.pem';key=R/'disposable/tls/key.pem';rows=[]
for mode in ('success','scheme','host','port','path','credentials','fragment','query','external','proxy','dns_rebind','redirect'):
 server=Server('redirect' if mode=='redirect' else 'http',cert=str(cert),key=str(key));c=contract();p=R/'disposable'/('endpoint_'+secrets.token_hex(6)+'.sqlite');Controller.provision(p,c);ctl=Controller(p,c);backend=None
 policy=Policy('https','localhost',server.port,'/fapi/v1/exchangeInfo','127.0.0.1',str(cert),'a'*64)
 url=f'https://localhost:{server.port}/fapi/v1/exchangeInfo'
 if mode=='scheme':url=url.replace('https','http')
 if mode=='host':url=url.replace('localhost','other.local')
 if mode=='port':url=url.replace(str(server.port),'18101')
 if mode=='path':url+='/evil'
 if mode=='credentials':url=url.replace('localhost','user@localhost')
 if mode=='fragment':url+='#evil'
 if mode=='query':url+='?redirect=evil'
 if mode=='external':policy=dataclasses.replace(policy,hostname='unverified.invalid',pinned_ip='8.8.8.8');url=url.replace('localhost','unverified.invalid')
 ok=False;error=None
 try:
  backend=PolicyBackend(ctl,{k:c[k] for k in ('producer_session','receiver_session','receiver_pid','receiver_creation')},policy,url,'http')
  if mode=='dns_rebind':
   with patch('socket.getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.2',server.port))]):backend.http('metadata')
  elif mode=='proxy':
   with patch.dict('os.environ',{'HTTPS_PROXY':'http://127.0.0.1:18101','ALL_PROXY':'http://127.0.0.1:10101'}):ok=backend.http('metadata')==b'{}'
  else:ok=backend.http('metadata')==b'{}'
 except Refused as e:error=str(e)
 finally:
  if backend:backend.close()
  ctl.close();server.close()
 assert ok==(mode in ('success','proxy')),(mode,error)
 if mode not in ('success','proxy','redirect'):assert server.count==0
 rows.append(dict(case=mode,pass_case=True,connections=server.count,error=error))
(R/'R7_ENDPOINT_NEGATIVE_TESTS.json').write_text(json.dumps(dict(passed=True,cases=rows,external_requests=0,production_endpoint_authority=False),indent=2));print('12 endpoint cases PASS')
