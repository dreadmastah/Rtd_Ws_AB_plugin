from pathlib import Path
import sys,json,secrets,time,os,subprocess,socket
R=Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'src'),str(R/'dependencies/r3')]
from peer import Peer,owner
from custody import Attestation
from relay_client import RelayClient
from pipeline import Pipeline
from durable import Store
s=Store(R/'dependencies/disposable'/('peer_'+secrets.token_hex(5)+'.sqlite'),'fixture');p=Pipeline(s,secrets.token_hex(16),secrets.token_bytes(32),['BTCUSDT'],'a'*64,lambda:time.time_ns()//1000000);relay=RelayClient(p,R/'disposable');checks=[]
try:
 assert owner(relay.sender)==relay.p.pid;checks.append('reverse tuple resolves distinct relay process')
 a=Attestation(os.getpid());own=a.check();a.close()
 for expected in (own,dict(relay.identity,creation=relay.identity['creation']+1),dict(relay.identity,sha256='0'*64)):
  try:Peer(relay.sender,expected,'relay');raise AssertionError('bad identity accepted')
  except ValueError:checks.append('wrong PID/creation/hash refused')
 relay.close()
 try:owner(relay.sender);raise AssertionError('closed accepted')
 except (AttributeError,OSError,ValueError):checks.append('closed peer refused')
 (R/'R7_WINDOWS_TRANSPORT_CUSTODY.json').write_text(json.dumps(dict(status='PASS_ISOLATED',checks=checks,relay=relay.identity,controller_receiver_writer=own,session=p.session,universe=p.universe,method='Windows AF_INET exact reverse ESTABLISHED tuple and held process creation/path/hash handle',limitations=['point-in-time tuple observations are not atomic lifetime proof','same process owns sender and receiver roles in fixture','no genuine production authority'],production_connections=0),indent=2));print('peer custody 5 checks PASS')
finally:relay.close();s.close()
