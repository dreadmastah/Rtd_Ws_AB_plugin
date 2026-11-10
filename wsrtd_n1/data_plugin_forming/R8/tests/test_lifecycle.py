from pathlib import Path
import sys,os,secrets,json,time,ctypes as C,subprocess,datetime,sqlite3
R=Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'src'),str(R/'dependencies/r3')]
from relay_client import RelayClient
from pipeline import Pipeline
from durable import Store
from fixture_pipe import Pipe,creation,K,W
class FI(C.Structure):_fields_=[('a',W.DWORD),('c',W.FILETIME),('x',W.FILETIME),('w',W.FILETIME),('serial',W.DWORD),('hi',W.DWORD),('lo',W.DWORD),('links',W.DWORD),('ih',W.DWORD),('il',W.DWORD)]
K.CreateFileW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE];K.CreateFileW.restype=W.HANDLE;K.GetFileInformationByHandle.argtypes=[W.HANDLE,C.POINTER(FI)]
path=R/'disposable'/('lifecycle_'+secrets.token_hex(5));path.mkdir();h=K.CreateFileW(str(path),0x80,3,None,3,0x02000000,None);i=FI();assert K.GetFileInformationByHandle(h,C.byref(i));K.CloseHandle(h);dbkey=f'{i.serial:08x}:{i.ih:08x}{i.il:08x}'
store=Store(R/'dependencies/disposable'/('lifecycle_'+secrets.token_hex(5)+'.sqlite'),'fixture');p=Pipeline(store,secrets.token_hex(16),secrets.token_bytes(32),['BTCUSDT'],'a'*64,lambda:time.time_ns()//1000000)
# Begin near minute end so real finality is not fabricated and the relay does not idle out.
remaining=60-time.time()%60
if remaining>8:time.sleep(remaining-8)
relay=RelayClient(p,R/'disposable');minute=time.time_ns()//60000000000*60000
def raw(final=False,stamp=None,price=101,volume=1):
 t=minute if stamp is None else stamp
 return dict(e='kline',s='BTCUSDT',st='UM',E=time.time_ns()//1000000,k=dict(s='BTCUSDT',i='1m',t=t,T=t+59999,o='100',h=str(max(102,price)),l='99',c=str(price),v=str(volume),x=final))
class Pub:
 session=p.session
 def binary(self,key):return p.snapshot(key)
pipe=Pipe(Pub(),dbkey);observed=[]
def probe(label,bars,close,vol):
 out=path/(label+'.json');env=dict(os.environ,WFR7_FIXTURE_ONLY='1',WFR7_PIPE=pipe.name,WFR7_SESSION=p.session,WFR7_OWNER_PID=str(os.getpid()),WFR7_OWNER_CREATION=str(creation()))
 run=subprocess.run([str(R/'build/Release/native_probe.exe'),str(R/'artifacts/WSRTD_Data_Forming_R7.dll'),str(path),'1',str(out)],env=env,capture_output=True,text=True,timeout=10)
 assert run.returncode==0,run.stdout+run.stderr
 row=json.loads(out.read_text())['rows'][0];assert (row['bars'],row['close'],row['volume'],row['open'],row['low'])==(bars,close,vol,100,99),row
 expected_minute=minute+60000 if label=='next_minute' else minute
 assert row['minute']==datetime.datetime.fromtimestamp(expected_minute/1000,datetime.timezone.utc).minute and row['high']==max(102,close),row
 observed.append(dict(stage=label,row=row,utc_ms=time.time_ns()//1000000))
try:
 relay.deliver(raw());probe('first',1,101,1)
 relay.deliver(raw(price=103,volume=2));probe('update',1,103,2)
 while time.time_ns()//1000000<minute+59000:
  relay.deliver(raw(price=103,volume=2));time.sleep(.15)
 while time.time_ns()//1000000<minute+60000:time.sleep(.01)
 final=raw(True,price=103,volume=2)
 original=store.commit
 def failed(*a,**k):raise sqlite3.OperationalError('injected storage failure before transaction')
 store.commit=failed;result=relay.deliver(final);assert result.startswith('LIVE_FINALIZED_NOT_YET_DURABLE');assert store.rows('BTCUSDT',True)==[]
 store.commit=original
 result=relay.deliver(final);assert result=='DURABLE_FINALIZED:COMMITTED';probe('finalized',1,103,2)
 result=relay.deliver(final);assert result.startswith('DURABLE_FINALIZED:');assert len(store.rows('BTCUSDT',True))==1;probe('duplicate',1,103,2)
 relay.deliver(raw(stamp=minute+60000,price=104,volume=1));probe('next_minute',2,104,1)
 relay.close();probe('disconnected',1,103,2)
 (R/'R7_SAME_MINUTE_FINALIZATION.json').write_text(json.dumps(dict(passed=True,minute=minute,observations=observed,relay=relay.identity,receipts=relay.receipts,durable_count=1,storage_failure_rejected=True,source='SYNTHETIC_FIXTURE',real_wall_clock_boundary=True,actual_amibroker=False),indent=2));print('same-minute real relay/native lifecycle PASS')
finally:pipe.close();relay.close();store.close()
