from pathlib import Path
import sys,json,hashlib,datetime,ctypes as C
from ctypes import wintypes as W
R=Path(__file__).resolve().parent
sys.path.insert(0,r'D:\WSRTD_N1_ACTIVE_CHART_RADAR_R1\retirement_controller_r1')
import r3_observer as o
class ME(C.Structure):_fields_=[('size',W.DWORD),('mid',W.DWORD),('pid',W.DWORD),('g',W.DWORD),('p',W.DWORD),('base',C.c_void_p),('length',W.DWORD),('handle',W.HMODULE),('name',W.WCHAR*256),('path',W.WCHAR*260)]
k=C.WinDLL('kernel32',use_last_error=True);k.CreateToolhelp32Snapshot.argtypes=[W.DWORD,W.DWORD];k.CreateToolhelp32Snapshot.restype=W.HANDLE;k.Module32FirstW.argtypes=[W.HANDLE,C.POINTER(ME)];k.Module32NextW.argtypes=[W.HANDLE,C.POINTER(ME)];k.CloseHandle.argtypes=[W.HANDLE]
rows=[]
for pid,p in o.nt_processes().items():
 if p['image'].lower()!='broker.exe':continue
 try:
  with o.opened(pid) as h:identity=o.handle_identity(h)
  row=dict(census=p,identity=identity,exe_sha256=hashlib.sha256(Path(identity[2]).read_bytes()).hexdigest(),modules=[])
  h=k.CreateToolhelp32Snapshot(8|16,pid)
  if h==C.c_void_p(-1).value:raise OSError(C.get_last_error(),'module census')
  try:
   m=ME();m.size=C.sizeof(m);ok=k.Module32FirstW(h,C.byref(m))
   while ok:
    if 'wsrtd' in m.path.lower():row['modules'].append(dict(path=m.path,sha256=hashlib.sha256(Path(m.path).read_bytes()).hexdigest()))
    ok=k.Module32NextW(h,C.byref(m))
  finally:k.CloseHandle(h)
  rows.append(row)
 except Exception as e:rows.append(dict(pid=pid,error=str(e)))
out=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),brokers=rows,listeners10101=o.listeners(10101),listeners18101=o.listeners(18101),current_selected_source='UNATTESTED_READ_ONLY_NO_GUI_OR_COM_CONTROL',current_database='UNATTESTED_OPERATOR_PREVIOUSLY_N1',production_control=0,production_writes=0)
(R/'evidence/HOST_READONLY.json').write_text(json.dumps(out,indent=2))
bootstrap=Path(r'D:\WSRTD_N1_POST_R3_FULL_PREFIX_BOOTSTRAP_20261102_R2\FINAL_DISPOSITION.json')
(R/'R8_HISTORY_ADMISSION_BOUNDARY.json').write_text(json.dumps(dict(status='BLOCKED',source=str(bootstrap),sha256=hashlib.sha256(bootstrap.read_bytes()).hexdigest(),evidence=json.loads(bootstrap.read_text()),LIVE_FORMING_READY='ISOLATED_SYNTHETIC_ONLY',FINALIZED_STORAGE_READY='ISOLATED_SYNTHETIC_ONLY',FULL_PREFIX_COMPLETE=False,NATIVE_CHART_READY=False),indent=2))
status=Path(r'D:\WSRTD_PR3_Test_20261010\persistent-feed-20261010\status.json')
if status.exists():
 data=json.loads(status.read_text());root=data.get('source_root')
 if root:
  p=Path(root)/'Binance/sender.py'
  if p.exists():(R/'evidence/LEGACY_SENDER_ROUTES.json').write_text(json.dumps(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),routes=[dict(line=i,text=line) for i,line in enumerate(p.read_text(encoding='utf-8').splitlines(),1) if 'fstream' in line or '/market' in line or '/stream' in line]),indent=2))
print('Read-only host and historical evidence saved')
