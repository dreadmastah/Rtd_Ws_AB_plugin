from pathlib import Path
import sys,time,secrets,json,subprocess,dataclasses
R=Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'src'),str(R/'tests')]
from pilot_endpoint import qualify,URL,PilotFixtureBackend
from admission import Controller,Refused
from test_network import contract
from servers import Server
from resolver import resolve
rows=[]
for url in [URL.replace('wss:','ws:'),URL.replace('fstream','dstream'),URL.replace('/market',''),URL+'/ethusdt@kline_1m',URL+'?streams=evil',URL.replace('.com/','.com:444/'),URL+'#x',URL.replace('btcusdt','ethusdt')]:
 try:qualify(url);raise AssertionError(url)
 except Refused:rows.append(dict(case=url,pass_case=True))
for mode in ('success','zero_rest','extra_subscription','reconnect','expired'):
 s=Server('ws_raw',b'{}',cert=str(R/'disposable/tls/cert.pem'),key=str(R/'disposable/tls/key.pem'))
 c=contract();c.update(symbols=['BTCUSDT'],rest_requests=0,rest_weight=0,connection_attempts=1,subscriptions=1,reconnects=0)
 if mode=='expired':c['start_ms']-=130000;c['end_ms']-=130000
 path=R/'disposable'/('pilot_'+secrets.token_hex(5)+'.sqlite');Controller.provision(path,c);ctl=Controller(path,c);b=PilotFixtureBackend(ctl,{k:c[k] for k in ('producer_session','receiver_session','receiver_pid','receiver_creation')},URL,s.port,str(R/'disposable/tls/cert.pem'))
 try:
  if mode=='zero_rest':b.http('metadata')
  elif mode=='extra_subscription':b.subscribe('ETHUSDT')
  elif mode=='reconnect':b.connect_ws(True)
  else:b.connect_ws();assert b.receive()==b'{}'
  assert mode=='success'
 except Refused:assert mode!='success'
 finally:b.close();ctl.close();s.close()
 assert s.count==(1 if mode=='success' else 0)
 rows.append(dict(case=mode,pass_case=True,connections=s.count))
dns=[]
for delay in (0,2):
 start=time.monotonic();cancelled=False
 try:addresses=resolve('localhost',45001,timeout=.8,fixture_delay=delay)
 except TimeoutError:cancelled=True
 assert cancelled==bool(delay);dns.append(dict(delay=delay,cancelled=cancelled,elapsed=time.monotonic()-start))
(R/'R7_EXTERNAL_ENDPOINT_ADMISSION.json').write_text(json.dumps(dict(status='PASS_ISOLATED_EXACT_POLICY_ONLY',cases=rows,external_dispatch_implemented=False,live_activation=False),indent=2))
(R/'R7_DNS_AND_DEADLINE_REGRESSION.json').write_text(json.dumps(dict(status='PASS_ISOLATED_WITH_OS_LIMITATION',cases=dns,method='owned resolver subprocess terminated/reaped on timeout',limitations=['No Windows hard real-time termination guarantee','OS DNS infrastructure may outlive caller cancellation; no external resolution tested','External address policy and actual TLS route remain unqualified']),indent=2));print('13 endpoint and 2 resolver cases PASS')
