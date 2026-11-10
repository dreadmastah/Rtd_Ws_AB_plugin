from pathlib import Path
import sys,os,secrets,time,json,sqlite3,ctypes as C,subprocess,statistics,tracemalloc
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from pipeline import Pipeline
from durable import Store
from fixture_pipe import Pipe,creation,K,W
class FI(C.Structure):_fields_=[('attr',W.DWORD),('c',W.FILETIME),('a',W.FILETIME),('w',W.FILETIME),('serial',W.DWORD),('hi',W.DWORD),('lo',W.DWORD),('links',W.DWORD),('ih',W.DWORD),('il',W.DWORD)]
K.CreateFileW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE];K.CreateFileW.restype=W.HANDLE
K.GetFileInformationByHandle.argtypes=[W.HANDLE,C.POINTER(FI)]
def dbkey(p):
 h=K.CreateFileW(str(p),0x80,3,None,3,0x02000000,None);f=FI();assert K.GetFileInformationByHandle(h,C.byref(f));K.CloseHandle(h);return f'{f.serial:08x}:{f.ih:08x}{f.il:08x}'
def event(s,t,final=False):
 now=int(time.time()*1000)
 return dict(e='kline',s=s,E=now,st='UM',k=dict(s=s,i='1m',t=t,T=t+59999,o='100',h='102',l='99',c='101',v='1',x=final,q='101',n=1))
measurements=[]
for count in (2,13,100,500,1024):
 # Avoid an unrelated wall-clock minute transition during this short fixture.
 remain=60-time.time()%60
 if remain<5:time.sleep(remain+.05)
 p=R/'disposable'/('scale_'+str(count)+'_'+secrets.token_hex(4));p.mkdir();store=Store(p/'feed.sqlite','fixture')
 symbols=['BTCUSDT','ETHUSDT']+[f'SYN{10000+i}USDT' for i in range(2,count)]
 pipe=Pipeline(store,secrets.token_hex(16),secrets.token_bytes(32),symbols,'b'*64,lambda:int(time.time()*1000))
 t=int(time.time()*1000)//60000*60000;commit=[]
 # Two real disposable SQLite commits per stage, not a claim of500 sustained writers.
 for s in symbols[:2]:
  a=time.perf_counter();result=pipe.receive(pipe.encode(event(s,t-60000,True)));commit.append((time.perf_counter()-a)*1000);assert result=='DURABLE_FINALIZED:COMMITTED'
 a=time.perf_counter();cpu=time.process_time();tracemalloc.start();latency=[]
 for s in symbols:
  tick=time.perf_counter();assert pipe.receive(pipe.encode(event(s,t)))=='ACCEPTED';latency.append((time.perf_counter()-tick)*1000)
 peak=tracemalloc.get_traced_memory()[1];tracemalloc.stop();elapsed=time.perf_counter()-a;cpu=time.process_time()-cpu
 class Publisher:
  session=pipe.session
  def binary(self,k):return pipe.snapshot(k)
 server=Pipe(Publisher(),dbkey(p));out=R/'evidence'/f'scale_{count}.json'
 env=dict(os.environ,WFR3_FIXTURE_ONLY='1',WFR3_PIPE=server.name,WFR3_SESSION=pipe.session,WFR3_OWNER_PID=str(os.getpid()),WFR3_OWNER_CREATION=str(creation()))
 try:
  r=subprocess.run([str(R/'build/Release/native_probe.exe'),str(R/'artifacts/WSRTD_Data_Forming_R3.dll'),str(p),str(count),str(out)],env=env,capture_output=True,text=True,timeout=15);assert r.returncode==0,r.stdout+r.stderr
  n=json.loads(out.read_text());assert n['symbols_returned']==count and all(x['close']==101 for x in n['rows'])
 finally:server.close();store.close()
 measurements.append(dict(symbols=count,synthetic=True,elapsed_seconds=elapsed,cpu_seconds=cpu,python_peak_alloc_bytes=peak,event_ms_p50=statistics.median(latency),event_ms_max=max(latency),commit_latency_ms=commit,queue_depth=0,forming_cache=len(pipe.receiver.buckets),**{k:v for k,v in n.items() if k!='rows'}))
 print('PASS integrated',count,flush=True)
(R/'R3_NATIVE_INTEGRATION_RESULTS.json').write_text(json.dumps({'pass':True,'measurements':measurements,'live_network':False,'actual_amibroker':False,'limitations':['short snapshots','two SQLite commits per stage','13identitysynthetic','fullprefixunqualified']},indent=2))
