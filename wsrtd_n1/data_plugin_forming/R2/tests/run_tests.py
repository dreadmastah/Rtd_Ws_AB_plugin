from pathlib import Path
import sys,os,time,json,secrets,sqlite3,ctypes as C,subprocess,hashlib,concurrent.futures,tracemalloc,statistics,socket,threading
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
from transport import *
from fixture_pipe import Pipe,creation,K,W
results=[]
def check(name,cond):
    results.append({'test':name,'pass':bool(cond)})
    if not cond:raise AssertionError(name)
def event(s,t,E,session,**kw):
    k={'s':s,'i':'1m','t':t,'T':t+59999,'o':'100','h':'102','l':'99','c':'101','v':'1','q':'101','n':1,'x':False};k.update(kw)
    return envelope({'e':'kline','s':s,'E':E,'st':'UM','k':k},session,E,{s:('UM','PERPETUAL')})
def scope(p):
    K.CreateFileW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE];K.CreateFileW.restype=W.HANDLE
    class FI(C.Structure):_fields_=[('attributes',W.DWORD),('created',W.FILETIME),('access',W.FILETIME),('write',W.FILETIME),('vol',W.DWORD),('sizehigh',W.DWORD),('sizelow',W.DWORD),('links',W.DWORD),('high',W.DWORD),('low',W.DWORD)]
    K.GetFileInformationByHandle.argtypes=[W.HANDLE,C.POINTER(FI)]
    h=K.CreateFileW(str(p),0x80,3,None,3,0x02000000,None)
    if h==C.c_void_p(-1).value:raise C.WinError(C.get_last_error())
    try:
        f=FI();assert K.GetFileInformationByHandle(h,C.byref(f));return f'{f.vol:08x}:{f.high:08x}{f.low:08x}'
    finally:K.CloseHandle(h)
def database(folder,symbols,t):
    folder.mkdir();key=scope(folder);p=folder/'feed.sqlite';db=sqlite3.connect(p)
    db.executescript('PRAGMA application_id=1465074229;PRAGMA user_version=2;CREATE TABLE database_context(database_id TEXT);CREATE TABLE bars(database_id TEXT,symbol TEXT,interval TEXT,ts_ms INTEGER,o TEXT,h TEXT,l TEXT,c TEXT,v TEXT,finalized INTEGER,PRIMARY KEY(database_id,symbol,interval,ts_ms));')
    db.execute('INSERT INTO database_context VALUES(?)',(key,))
    db.executemany('INSERT INTO bars VALUES(?,?,?,?,?,?,?,?,?,1)',[(key,s,'1m',t-60000,'100','102','99','101','1') for s in symbols]);db.commit();db.close();return p,key
def functional(s):
    t=1800000000000;clock=[t+1000];session=secrets.token_hex(16);key=secrets.token_bytes(32);r=Receiver(session,key,[s],lambda:clock[0])
    send=lambda e:r.ingest(signed(e,key))
    check(s+'_missing',r.snapshot()[1][s]=='MISSING')
    a=event(s,t,clock[0],session);check(s+'_first',send(a)=='ACCEPTED')
    check(s+'_duplicate',send(a)=='DUPLICATE')
    clock[0]+=1000;b=event(s,t,clock[0],session,h='104',l='98',c='103',v='2');check(s+'_OHLCV_replace',send(b)=='ACCEPTED' and len(r.snapshot()[0])==1)
    check(s+'_out_of_order',send(a).startswith('INVALID'))
    bad=dict(b,producer_session=secrets.token_hex(16));check(s+'_old_session',send(bad).startswith('INVALID'))
    check(s+'_auth',r.ingest(b'x'*32+canonical(b)).startswith('INVALID'))
    check(s+'_version',send(dict(b,schema_version=3)).startswith('INVALID'))
    check(s+'_final_before_close',send(dict(b,is_final=True)).startswith('INVALID'))
    clock[0]=t+61000;c=event(s,t+60000,clock[0],session);check(s+'_new_minute',send(c)=='ACCEPTED')
    check(s+'_missing_final_not_promoted',(s,t) in r.missing_finals and (s,t) not in r.snapshot()[0])
    late=event(s,t,clock[0],session,x=True,h='104',l='98',c='103',v='2');check(s+'_late_final',send(late)=='ACCEPTED' and r.snapshot()[0][s,t][1]=='LIVE_FINALIZED_PENDING_STORAGE')
    check(s+'_final_no_duplicate',len(r.snapshot()[0])==2)
    check(s+'_final_immutable',send(dict(late,close='102')).startswith('INVALID'))
    r.disconnect();check(s+'_disconnect',r.snapshot()[1][s]=='STALE' and (s,t) in r.snapshot()[0] and (s,t+60000) not in r.snapshot()[0])
    check(s+'_disconnected_reject',send(c).startswith('INVALID'))
    out=R/f'R2_{s}_FORMING_BAR_TESTS.json';out.write_text(json.dumps({'synthetic':True,'tests':[x for x in results if x['test'].startswith(s)],'status':r.status()},indent=2))
functional('BTCUSDT');functional('ETHUSDT')
# A real isolated byte-stream relay, no connection to Binance or production ports.
session=secrets.token_hex(16);key=secrets.token_bytes(32);now=int(time.time()*1000);t=now//60000*60000
r=Receiver(session,key,['BTCUSDT']);e=event('BTCUSDT',t,now,session)
a,b=socket.socketpair();packet=signed(e,key);a.sendall(len(packet).to_bytes(4,'big')+packet)
size=int.from_bytes(b.recv(4),'big');buf=b''
while len(buf)<size:buf+=b.recv(size-len(buf))
check('isolated_relay_frame',r.ingest(buf)=='ACCEPTED');a.close();b.close()
# Preserve history under refresh/reconciliation and pending-final backpressure.
folder=R/'disposable'/('merge_'+secrets.token_hex(4));p,dbkey=database(folder,['BTCUSDT'],t)
r.load_history(p,dbkey);original=hashlib.sha256(p.read_bytes()).hexdigest()
check('history_live_merge',len(r.snapshot()[0])==2)
r.load_history(p,dbkey);check('history_idempotent',len(r.snapshot()[0])==2)
check('history_original_unchanged',hashlib.sha256(p.read_bytes()).hexdigest()==original)
clock=[1800000000000+61000];rx=Receiver(session,key,['BTCUSDT'],lambda:clock[0])
for i in range(4):
    stamp=1800000000000+i*60000;clock[0]=stamp+61000
    check('pending_final_'+str(i),rx.ingest(signed(event('BTCUSDT',stamp,clock[0],session,x=True),key))=='ACCEPTED')
stamp+=60000;clock[0]=stamp+61000
check('bounded_backpressure',rx.ingest(signed(event('BTCUSDT',stamp,clock[0],session,x=True),key)).startswith('INVALID') and len(rx.buckets)==4)
scale=[]
for count in (2,13,100,500,600,1024):
    symbols=['BTCUSDT','ETHUSDT']+[f'SYN{10000+i}USDT' for i in range(2,count)]
    now=int(time.time()*1000);t=now//60000*60000
    folder=R/'disposable'/('scale_'+str(count)+'_'+secrets.token_hex(4));p,dbkey=database(folder,symbols,t)
    session=secrets.token_hex(16);key=secrets.token_bytes(32);rx=Receiver(session,key,symbols)
    rx.load_history(p,dbkey);before=hashlib.sha256(p.read_bytes()).hexdigest()
    tracemalloc.start();start=time.perf_counter();cpu=time.process_time()
    for s in symbols:
        check('scale_ingest_'+str(count)+'_'+s,rx.ingest(signed(event(s,t,int(time.time()*1000),session),key))=='ACCEPTED')
    wall=time.perf_counter()-start;cpu=time.process_time()-cpu;peak=tracemalloc.get_traced_memory()[1];tracemalloc.stop()
    env=dict(os.environ,WFR2_FIXTURE_ONLY='1',WFR2_PIPE='\\\\.\\pipe\\WSRTD_FORMING_R2_'+session,WFR2_SESSION=session,WFR2_OWNER_PID=str(os.getpid()),WFR2_OWNER_CREATION=str(creation()))
    pipe=Pipe(rx,dbkey);output=R/'evidence'/f'native_{count}.json'
    try:
        proc=subprocess.run([str(R/'build/Release/native_probe.exe'),str(R/'artifacts/WSRTD_Data_Forming_R2.dll'),str(folder),str(count),str(output)],env=env,capture_output=True,text=True,timeout=15)
        check('native_exit_'+str(count),proc.returncode==0)
        evidence=json.loads(output.read_text());check('native_all_symbols_'+str(count),evidence['symbols_returned']==count)
        check('native_two_bars_'+str(count),all(row['bars']==2 and row['close']==101 and row['volume']==1 for row in evidence['rows']))
        check('native_refresh_'+str(count),evidence['notifications']>0)
        check('history_no_write_'+str(count),hashlib.sha256(p.read_bytes()).hexdigest()==before)
    finally:pipe.close()
    scale.append({'symbols':count,'synthetic':True,'eligibility_proven':False,'ingest_wall_seconds':wall,'CPU_seconds':cpu,'events_per_second':count/wall,'python_tracemalloc_peak_bytes':peak,'cache_count':len(rx.buckets),'snapshot_bytes':len(rx.binary(dbkey)),**{k:v for k,v in evidence.items() if k!='rows'},'pipe_writes':pipe.writes,'pipe_error':pipe.error})
(R/'R2_SCALE_ACCEPTANCE_MATRIX.json').write_text(json.dumps(scale,indent=2))
(R/'R2_RESOURCE_MEASUREMENTS.json').write_text(json.dumps({'scope':'synthetic short-window; no lifetime capacity claim','scale':scale},indent=2))
(R/'evidence/AUTHOR_TESTS.json').write_text(json.dumps({'passed':sum(x['pass'] for x in results),'tests':results,'native_host':'isolated compiled ADK harness, not AmiBroker'},indent=2))
print('PASS',len(results),'checks; native scales',len(scale))
