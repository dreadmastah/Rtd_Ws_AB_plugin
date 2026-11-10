from pathlib import Path
import sys,os,secrets,json,time,ctypes as C,subprocess
R=Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'src'),str(R/'dependencies/r3'),str(R/'tests')]
from admission import Controller
from network import Backend,Endpoint
from handoff import Handoff
from relay_client import RelayClient
from servers import Server
from pipeline import Pipeline
from durable import Store
from fixture_pipe import Pipe,creation,K,W
class FI(C.Structure):_fields_=[('a',W.DWORD),('c',W.FILETIME),('x',W.FILETIME),('w',W.FILETIME),('serial',W.DWORD),('hi',W.DWORD),('lo',W.DWORD),('links',W.DWORD),('ih',W.DWORD),('il',W.DWORD)]
K.CreateFileW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE];K.CreateFileW.restype=W.HANDLE;K.GetFileInformationByHandle.argtypes=[W.HANDLE,C.POINTER(FI)]
path=R/'disposable'/('native_'+secrets.token_hex(5));path.mkdir();h=K.CreateFileW(str(path),0x80,3,None,3,0x02000000,None);i=FI();assert K.GetFileInformationByHandle(h,C.byref(i));K.CloseHandle(h);dbkey=f'{i.serial:08x}:{i.ih:08x}{i.il:08x}'
now=time.time_ns()//1000000;t=now//60000*60000
c=dict(authority=secrets.token_hex(16),producer_session=secrets.token_hex(16),receiver_session=secrets.token_hex(16),symbols=['BTCUSDT','ETHUSDT'],universe_version='a'*64,start_ms=now,end_ms=now+120000,rest_requests=0,rest_weight=0,connection_attempts=2,subscriptions=2,reconnects=1,max_frames=100,max_bytes=100000,receiver_pid=os.getpid(),receiver_creation=creation())
ledger=path/'admission.sqlite';Controller.provision(ledger,c);ctl=Controller(ledger,c)
store=Store(R/'dependencies/disposable'/('native_'+secrets.token_hex(5)+'.sqlite'),'fixture');p=Pipeline(store,c['producer_session'],b'a'*32,c['symbols'],c['universe_version'],lambda:time.time_ns()//1000000)
checks=[]
relay=RelayClient(p,R/'disposable')
try:
 bodies=[]
 for stamp,final,close in ((t-60000,True,'101'),(t,False,'101'),(t,False,'102')):
  for symbol in c['symbols']:
   # Events at distinct exchange times to qualify current-minute replacement.
   E=time.time_ns()//1000000+len(bodies)
   raw=dict(e='kline',s=symbol,E=E,st='UM',k=dict(s=symbol,i='1m',t=stamp,T=stamp+59999,o='100',h='103',l='99',c=close,v=str(len(bodies)//2+1),x=final))
   bodies.append(json.dumps(raw).encode())
 server=Server('ws_two',bodies);backend=Backend(ctl,{k:c[k] for k in ('producer_session','receiver_session','receiver_pid','receiver_creation')},Endpoint(server.port))
 try:
  backend.connect_ws(False)
  for symbol in c['symbols']:backend.subscribe(symbol)
  for _ in bodies:checks.append(relay.deliver(json.loads(backend.receive())))
 finally:backend.close();server.close()
 class Pub:
  session=p.session
  def binary(self,key):return p.snapshot(key)
 pipe=Pipe(Pub(),dbkey)
 try:
  env=dict(os.environ,WFR6_FIXTURE_ONLY='1',WFR6_PIPE=pipe.name,WFR6_SESSION=p.session,WFR6_OWNER_PID=str(os.getpid()),WFR6_OWNER_CREATION=str(creation()))
  out=R/'evidence/NATIVE_E2E.json'
  run=subprocess.run([str(R/'build/Release/native_probe.exe'),str(R/'artifacts/WSRTD_Data_Forming_R6.dll'),str(path),'2',str(out)],env=env,capture_output=True,text=True,timeout=15)
  assert run.returncode==0,run.stdout+run.stderr
  results=json.loads(out.read_text());assert all(row['bars']==2 and row['close']==102 and row['volume']==3 for row in results['rows'])
  assert results['notifications']>0
  p.receiver.disconnect()
  staleout=R/'evidence/NATIVE_STALE.json'
  stale=subprocess.run([str(R/'build/Release/native_probe.exe'),str(R/'artifacts/WSRTD_Data_Forming_R6.dll'),str(path),'2',str(staleout)],env=env,capture_output=True,text=True,timeout=15)
  assert stale.returncode==0,stale.stdout+stale.stderr
  stale_result=json.loads(staleout.read_text());assert all(row['bars']==1 and row['close']==101 for row in stale_result['rows'])
  (R/'R6_NATIVE_DATA_PLUGIN_INTEGRATION.json').write_text(json.dumps(dict(passed=True,live_fixture=results,disconnected_fixture=stale_result,forming_removed_on_disconnect=True,durable_history_preserved=True,actual_host=False),indent=2))
 finally:pipe.close()
 (R/'R6_END_TO_END_V3_PIPELINE.json').write_text(json.dumps({'passed':True,'path':'realWSloopback->admittedbackend->TCPsender->independentV3relay->TCPreceiver->disposablecommit->namedpipe->compiledGetQuotesEx','relay_identity':relay.identity,'relay_port':relay.port,'receipts':relay.receipts,'source_events':checks,'native':results,'source_provenance':'SYNTHETIC_FIXTURE','genuine_receipt':False,'actual_amibroker':False},indent=2));print('real relay network to native two-symbol PASS')
finally:relay.close();store.close();ctl.close()
