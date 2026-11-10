from pathlib import Path
import sys,os,secrets,json,hashlib
R=Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'src'),str(R/'tests')]
from test_network import contract
from controller import ControlledSession
from custody import Attestation
from admission import Controller,Refused
from network import Endpoint
from servers import Server
a=Attestation(os.getpid());identity=a.check();a.close()
results=[]
for mode in ('ws','ws_bad','wrong_producer','wrong_receiver','wrong_authority'):
 c=contract();c.update(symbols=['BTCUSDT'],receiver_creation=identity['creation'])
 p=R/'disposable'/('controller_'+secrets.token_hex(6)+'.sqlite');Controller.provision(p,c);ledger=Controller(p,c)
 s=Server('ws_bad' if mode=='ws_bad' else 'ws');session=None
 digest=hashlib.sha256(json.dumps(c,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 try:
  producer=dict(identity,pid=0) if mode=='wrong_producer' else identity
  receiver=dict(identity,creation=identity['creation']+1) if mode=='wrong_receiver' else identity
  session=ControlledSession(ledger,Endpoint(s.port),receiver,producer,'0'*64 if mode=='wrong_authority' else digest)
  session.start();assert session.read()==b'{}';assert mode=='ws'
 except (Refused,ValueError):
  assert mode!='ws'
  if mode.startswith('wrong_'):assert s.count==0
 finally:
  if session:session.close()
  ledger.close();s.close()
 results.append({'case':mode,'pass':True})
(R/'evidence/CONTROLLER.json').write_text(json.dumps(results,indent=2));print('5 controller cases PASS')
