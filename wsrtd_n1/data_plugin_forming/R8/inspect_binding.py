from pathlib import Path
import json,ctypes as C
from ctypes import wintypes as W
R=Path(__file__).resolve().parent;v=C.WinDLL('version',use_last_error=True)
v.GetFileVersionInfoSizeW.argtypes=[W.LPCWSTR,C.POINTER(W.DWORD)];v.GetFileVersionInfoW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p];v.VerQueryValueW.argtypes=[C.c_void_p,W.LPCWSTR,C.POINTER(C.c_void_p),C.POINTER(W.UINT)]
exe=r'C:\Program Files\AmiBroker\Broker.exe';dummy=W.DWORD();n=v.GetFileVersionInfoSizeW(exe,C.byref(dummy));buf=C.create_string_buffer(n);assert v.GetFileVersionInfoW(exe,0,n,buf);ptr=C.c_void_p();length=W.UINT();assert v.VerQueryValueW(buf,'\\',C.byref(ptr),C.byref(length));words=C.cast(ptr,C.POINTER(W.DWORD));a,b=words[2],words[3]
paths=[Path(r'D:\Amibroker_myDATA\N1'),Path(r'D:\Amibroker_myDATA\N1.wsrtd-n1\feed.sqlite')]
rows=[]
for p in paths:
 row=dict(path=str(p),exists=p.exists())
 if p.exists():
  st=p.stat();row.update(device=st.st_dev,inode=st.st_ino,bytes=st.st_size)
 rows.append(row)
(R/'evidence/INSTALLED_BINDING.json').write_text(json.dumps(dict(executable=exe,version=f'{a>>16}.{a&65535}.{b>>16}.{b&65535}',paths=rows,sqlite_schema='BLOCKED_EXPECTED_HISTORICAL_PATH_ABSENT',selected_source='UNATTESTED',exclusive_writer='UNATTESTED',production_writes=0),indent=2));print('Version and exact historical-path checks saved')
