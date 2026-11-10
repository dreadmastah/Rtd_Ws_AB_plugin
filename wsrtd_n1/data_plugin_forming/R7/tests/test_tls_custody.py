from pathlib import Path
import sys,json,secrets,time,os,ssl,subprocess
R=Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'src'),str(R/'tests')]
from network import Backend,Endpoint
from admission import Controller
from servers import Server
from custody import Attestation
def c():
 now=time.time_ns()//1000000
 return dict(authority=secrets.token_hex(16),producer_session=secrets.token_hex(16),receiver_session=secrets.token_hex(16),symbols=['BTCUSDT'],universe_version='a'*64,start_ms=now,end_ms=now+120000,rest_requests=1,rest_weight=1,connection_attempts=1,subscriptions=1,reconnects=0,max_frames=10,max_bytes=10000,receiver_pid=os.getpid(),receiver_creation=1)
results=[];cert=R/'disposable/tls/cert.pem';key=R/'disposable/tls/key.pem'
other=R/'disposable/tls/unrelated.pem'
subprocess.run(['C:/Program Files/Git/usr/bin/openssl.exe','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(other.with_suffix('.key')),'-out',str(other),'-days','2','-subj','/CN=unrelated-test-ca'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
for hostname,trust,expected in [('localhost',str(cert),True),('wrong.local',str(cert),False),('localhost',None,False)]:
 server=Server(cert=str(cert),key=str(key));cfg=c();path=R/'disposable'/('tls_'+secrets.token_hex(5)+'.sqlite');Controller.provision(path,cfg);ctl=Controller(path,cfg)
 # Valid unrelated CA forces actual certificate-chain rejection during TLS handshake.
 if trust is None:
  trust=str(other)
 b=Backend(ctl,{k:cfg[k] for k in ('producer_session','receiver_session','receiver_pid','receiver_creation')},Endpoint(server.port,True,hostname,trust))
 success=False
 try:success=b.http('metadata')==b'{}'
 except (ssl.SSLError,OSError):pass
 finally:b.close();ctl.close();server.close()
 assert success==expected
 results.append({'hostname':hostname,'trusted_fixture_ca':expected,'expected_success':expected,'passed':True})
a=Attestation(os.getpid());identity=a.check();b=Attestation(os.getpid(),identity);b.close();a.close()
try:Attestation(os.getpid(),dict(identity,creation=identity['creation']+1));raise AssertionError('stale accepted')
except ValueError:pass
(R/'evidence/TLS_CUSTODY.json').write_text(json.dumps({'tls_cases':results,'process_identity':identity,'wrong_creation_rejected':True,'observed_identity_is_not_authorization':True,'external_connections':0},indent=2));print('TLS and Windows custody cases PASS')
