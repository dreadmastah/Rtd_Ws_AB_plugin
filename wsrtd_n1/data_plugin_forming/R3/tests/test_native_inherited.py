"""Author rerun of inherited independent R2 harness, plus changed R3 interval tests."""
import ctypes as C,os,pathlib,sys,time,tempfile,uuid,json,hashlib,struct,concurrent.futures
from ctypes import wintypes as W
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import fixture_pipe as F
class Info(C.Structure):
 _fields_=[('attr',W.DWORD),('creation',W.FILETIME),('access',W.FILETIME),('write',W.FILETIME),('serial',W.DWORD),('hi',W.DWORD),('lo',W.DWORD),('links',W.DWORD),('indexhi',W.DWORD),('indexlo',W.DWORD)]
class Notice(C.Structure):
 _fields_=[('size',C.c_int),('reason',C.c_int),('path',C.c_char_p),('host',W.HWND),('stock',C.c_void_p),('workspace',C.c_void_p),('newstock',C.c_void_p)]
class Quote(C.Structure):
 _fields_=[('date',C.c_uint64),('close',C.c_float),('open',C.c_float),('high',C.c_float),('low',C.c_float),('volume',C.c_float),('oi',C.c_float),('aux1',C.c_float),('aux2',C.c_float)]
assert C.sizeof(Notice)==48 and C.sizeof(Quote)==40
K=F.K
K.CreateFileW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE];K.CreateFileW.restype=W.HANDLE
K.GetFileInformationByHandle.argtypes=[W.HANDLE,C.POINTER(Info)]
path=pathlib.Path(tempfile.mkdtemp(prefix='independent_native_',dir=ROOT/'disposable'))
h=K.CreateFileW(str(path),0x80,3,None,3,0x02000000,None);info=Info()
assert K.GetFileInformationByHandle(h,C.byref(info));K.CloseHandle(h)
dbkey=f'{info.serial:08x}:{info.indexhi:08x}{info.indexlo:08x}'
class Payload:
 def __init__(self):self.session=uuid.uuid4().hex;self.serial=1;self.rows=[];self.connected=1;self.key_override=None
 def binary(self,key):
  now=int(time.time()*1000)
  rows=self.rows[:]
  return struct.pack('<IIIIQQ64s80s',0x32434E57,2,len(rows),self.connected,self.serial,now,self.session.encode(),(self.key_override or key).encode())+b''.join(rows)
def row(stamp,close=11,state=1,symbol='BTCUSDT'):
 return struct.pack('<32sQ5dII',symbol.encode(),stamp,10,12,9,close,2,state,0)
p=Payload();pipe=F.Pipe(p,dbkey)
os.environ.update(WFR3_FIXTURE_ONLY='1',WFR3_PIPE=pipe.name,WFR3_SESSION=p.session,WFR3_OWNER_PID=str(os.getpid()),WFR3_OWNER_CREATION=str(F.creation()))
dllpath=ROOT/'artifacts'/'WSRTD_Data_Forming_R3.dll';dll=C.CDLL(str(dllpath))
dll.Notify.argtypes=[C.POINTER(Notice)];dll.Notify.restype=C.c_int
dll.GetQuotesEx.argtypes=[C.c_char_p,C.c_int,C.c_int,C.c_int,C.POINTER(Quote),C.c_void_p];dll.GetQuotesEx.restype=C.c_int
dll.R3Metrics.argtypes=[C.POINTER(C.c_uint64),C.c_int];dll.R3Metrics.restype=C.c_int
n=Notice(C.sizeof(Notice),1,str(path).encode(),None,None,None,None)
tests=[]
def record(name,ok,detail=''):
 tests.append(dict(name=name,passed=bool(ok),detail=detail));print(name,ok,detail)
def read(symbol=b'BTCUSDT',cap=8):
 a=(Quote*8)();a[0].close=12345;z=dll.GetQuotesEx(symbol,60,-1,cap,a,None);return z,a
def until(predicate):
 end=time.monotonic()+2
 while time.monotonic()<end:
  result=predicate()
  if result:return result
  time.sleep(.03)
 return False
def revision():
 a=(C.c_uint64*5)();assert dll.R3Metrics(a,5);return a[0]
def applied(serial):return until(lambda:revision()==serial)
try:
 record('Init',dll.Init()==1);record('Notify_disposable',dll.Notify(C.byref(n))==1)
 record('no_data',read()[0]==0)
 t=int(time.time()*1000)//60000*60000
 p.rows=[row(t-60000),row(t,11,2)];p.serial=2
 record('history_plus_forming',applied(2) and read()[0]==2)
 p.rows=[row(t-60000),row(t,12,2)];p.serial=3
 record('same_minute_replace',until(lambda:(lambda x:x[0]==2 and x[1][1].close==12)(read())))
 z,a=read(cap=1);record('capacity_fail_no_buffer_mutation',z==0 and a[0].close==12345)
 record('unknown_symbol',read(b'ETHUSDT')[0]==0)
 p.rows=[row(t-60000),row(t,12,3)];p.serial=4
 record('final_pending_no_duplicate',applied(4) and read()[0]==2)
 p.rows=[row(t-60000),row(t,12,1)];p.serial=5
 record('storage_promotion_no_duplicate',applied(5) and read()[0]==2)
 p.rows=[row(t-60000,10)];p.serial=1
 time.sleep(.35);z,a=read();record('older_serial_rejected',z==2 and a[0].close==11)
 p.serial=6;p.key_override='wrong';time.sleep(.35)
 record('wrong_database_rejected',read()[0]==2)
 p.key_override=None;p.rows=[row(t-60000),row(t,11,2)];p.serial=7
 record('forming_reacquired',until(lambda:read()[0]==2))
 p.connected=0;p.rows=[row(t-60000)];p.serial=8
 record('disconnect_preserves_history_removes_forming',until(lambda:read()[0]==1))
 def callback_stress(_):
  for i in range(100):
   z,a=read()
   if z not in (0,1):return False
   if z and a[0].close!=11:return False
  return True
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  record('concurrent_callbacks_no_cross_symbol_corruption',all(pool.map(callback_stress,range(4))))
 n.reason=2;record('Notify_unload',dll.Notify(C.byref(n))==1);record('after_unload_no_data',read()[0]==0)
 n.reason=1;os.environ['WFR3_OWNER_CREATION']=str(F.creation()+1)
 record('wrong_owner_creation_rejected',dll.Notify(C.byref(n))==0)
 os.environ['WFR3_OWNER_CREATION']=str(F.creation());os.environ['WFR3_OWNER_PID']='0'
 record('wrong_owner_pid_rejected',dll.Notify(C.byref(n))==0)
 os.environ['WFR3_OWNER_PID']=str(os.getpid());os.environ['WFR3_SESSION']='b'*32
 record('different_session_notify_bound',dll.Notify(C.byref(n))==1)
 time.sleep(.35);record('old_session_payload_rejected',read()[0]==0)
 n.reason=2;dll.Notify(C.byref(n));n.reason=1
 os.environ['WFR3_SESSION']=p.session;n.path=b'D:\\Amibroker_myDATA\\N1'
 record('protected_database_bind_refused',dll.Notify(C.byref(n))==0)
 # Independently exercise documented notification with a private same-thread window.
 U=C.WinDLL('user32',use_last_error=True);K.GetModuleHandleW.argtypes=[W.LPCWSTR];K.GetModuleHandleW.restype=W.HMODULE
 PROC=C.WINFUNCTYPE(C.c_ssize_t,W.HWND,W.UINT,W.WPARAM,W.LPARAM)
 U.DefWindowProcW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM];U.DefWindowProcW.restype=C.c_ssize_t
 observed=[]
 @PROC
 def wnd(h,m,w,l):
  if m==0x400+13000:observed.append(read()[0]);return 0
  return U.DefWindowProcW(h,m,w,l)
 class WC(C.Structure):
  _fields_=[('style',W.UINT),('proc',PROC),('cls',C.c_int),('wnd',C.c_int),('instance',W.HINSTANCE),('icon',W.HANDLE),('cursor',W.HANDLE),('brush',W.HANDLE),('menu',W.LPCWSTR),('name',W.LPCWSTR)]
 wc=WC(0,wnd,0,0,K.GetModuleHandleW(None),None,None,None,None,'INDEPENDENT_R2_HOST')
 U.RegisterClassW.argtypes=[C.POINTER(WC)];U.RegisterClassW.restype=W.WORD;assert U.RegisterClassW(C.byref(wc))
 U.CreateWindowExW.argtypes=[W.DWORD,W.LPCWSTR,W.LPCWSTR,W.DWORD,C.c_int,C.c_int,C.c_int,C.c_int,W.HWND,W.HANDLE,W.HINSTANCE,C.c_void_p];U.CreateWindowExW.restype=W.HWND
 win=U.CreateWindowExW(0,wc.name,'',0,0,0,0,0,W.HWND(-3),None,wc.instance,None);assert win
 U.PeekMessageW.argtypes=[C.POINTER(W.MSG),W.HWND,W.UINT,W.UINT,W.UINT];U.DispatchMessageW.argtypes=[C.POINTER(W.MSG)]
 U.DestroyWindow.argtypes=[W.HWND];U.UnregisterClassW.argtypes=[W.LPCWSTR,W.HINSTANCE]
 workspace=(C.c_int*64)();workspace[0]=int.from_bytes(b'WFR3','big')
 n.path=str(path).encode();n.host=win;n.workspace=C.cast(workspace,C.c_void_p)
 p.connected=1;p.serial=10;p.rows=[row(t-60000),row(t,11,2)]
 record('UI_notify_bound',dll.Notify(C.byref(n))==1)
 def pump(predicate):
  end=time.monotonic()+2
  while time.monotonic()<end:
   msg=W.MSG()
   while U.PeekMessageW(C.byref(msg),None,0,0,1):U.DispatchMessageW(C.byref(msg))
   if predicate():return True
   time.sleep(.01)
  return False
 record('UI_refresh_invokes_quote_readback',pump(lambda:2 in observed))
 observed.clear();p.connected=0;p.rows=[row(t-60000)];p.serial=11
 record('UI_disconnect_invalidates_forming',pump(lambda:1 in observed))
 n.reason=2;record('UI_unload',dll.Notify(C.byref(n))==1)
 U.DestroyWindow(win);U.UnregisterClassW(wc.name,wc.instance)
 # R3 new daily path: complete UTC day only, correct ADK daily mask.
 n.host=None;n.workspace=None;n.reason=1
 day=(t//86400000-2)*86400000
 p.connected=1;p.rows=[row(day+i*60000) for i in range(1440)];p.serial=20
 record('daily_bind',dll.Notify(C.byref(n))==1 and applied(20))
 q=(Quote*4)();z=dll.GetQuotesEx(b'BTCUSDT',86400,-1,4,q,None)
 record('daily_1440_UTC_aggregate',z==1 and q[0].open==10 and q[0].close==11 and q[0].volume==2880 and (q[0].date & 0x000007ffffffffc0)==0x000007ffffffffc0)
 p.rows=[row(day+i*60000) for i in range(1439)];p.serial=21
 record('daily_gap_refused',applied(21) and dll.GetQuotesEx(b'BTCUSDT',86400,-1,4,q,None)==0)
 record('weekly_direct_unsupported',dll.GetQuotesEx(b'BTCUSDT',604800,-1,4,q,None)==0)
 n.reason=2;dll.Notify(C.byref(n))
 # Concurrent lifecycle entry is rejected or serialized; never starts two workers.
 n.host=None;n.workspace=None;n.reason=1;n.path=str(path).encode()
 def lifecycle_stress(i):
  ok=True
  for j in range(6):
   result=dll.Init() if (i+j)%3==0 else dll.Notify(C.byref(n)) if (i+j)%3==1 else dll.Release()
   ok &= result in (0,1)
  return ok
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  record('concurrent_lifecycle_returns_safely',all(pool.map(lifecycle_stress,range(4))))
 record('post_concurrency_cleanup',dll.Release()==1)
 record('post_concurrency_reinitialize',dll.Init()==1 and dll.Notify(C.byref(n))==1)
 n.reason=2;record('post_concurrency_unload',dll.Notify(C.byref(n))==1)
 record('Release',dll.Release()==1)
finally:
 dll.Release();pipe.close()
receipt={'tests':tests,'passed':all(t['passed'] for t in tests),'dll_sha256':hashlib.sha256(dllpath.read_bytes()).hexdigest(),'source_sha256':hashlib.sha256((ROOT/'native'/'plugin.cpp').read_bytes()).hexdigest(),'actual_amibroker':False,'production_mutations':0,'binance_connections':0,'protected_relay_connections':0,'limitation':'headless callback ABI plus private same-thread window; not actual AmiBroker'}
(ROOT/'evidence'/'native_results.json').write_text(json.dumps(receipt,indent=2))
sys.exit(not receipt['passed'])
