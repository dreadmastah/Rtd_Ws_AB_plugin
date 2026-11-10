"""Observed directory handles; rename-exclusion qualification failed on this host."""
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
K=C.WinDLL('kernel32',use_last_error=True)
K.CreateFileW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE];K.CreateFileW.restype=W.HANDLE;K.CloseHandle.argtypes=[W.HANDLE]
class ParentCustody:
 QUALIFIED_FOR_LIVE_WRITES=False
 def __init__(self,identity):
  self.p=Path(identity['path']);self.expected=identity;self.handles=[]
  try:
   for path in reversed((self.p,*self.p.parents)):
    st=path.lstat()
    if getattr(st,'st_file_attributes',0)&0x400:raise ValueError('reparse ancestor')
    h=K.CreateFileW(str(path),0x80,3,None,3,0x02000000,None)
    if h==C.c_void_p(-1).value:raise C.WinError(C.get_last_error())
    self.handles.append(h)
   self.check()
  except BaseException:self.close();raise
 def check(self):
  st=self.p.stat()
  if dict(path=str(self.p),device=st.st_dev,inode=st.st_ino)!=self.expected:raise ValueError('directory identity changed')
 def close(self):
  for h in reversed(self.handles):K.CloseHandle(h)
  self.handles=[]
