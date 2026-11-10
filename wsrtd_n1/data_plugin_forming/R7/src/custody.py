"""Read-only Windows process attestation. Observation is not authorization."""
import ctypes as C,hashlib,os
from ctypes import wintypes as W
from pathlib import Path
K=C.WinDLL('kernel32',use_last_error=True)
K.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];K.OpenProcess.restype=W.HANDLE
K.CloseHandle.argtypes=[W.HANDLE];K.WaitForSingleObject.argtypes=[W.HANDLE,W.DWORD]
K.GetProcessTimes.argtypes=[W.HANDLE]+[C.POINTER(W.FILETIME)]*4
K.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,C.POINTER(W.DWORD)]
class Attestation:
 def __init__(self,pid,expected=None):
  if type(pid)is not int or pid<=0:raise ValueError('PID')
  self.h=K.OpenProcess(0x1000|0x100000,False,pid)
  if not self.h:raise C.WinError(C.get_last_error())
  try:
   f=[W.FILETIME() for _ in range(4)];name=C.create_unicode_buffer(32768);n=W.DWORD(len(name))
   if not K.GetProcessTimes(self.h,*[C.byref(x) for x in f]) or not K.QueryFullProcessImageNameW(self.h,0,name,C.byref(n)):raise C.WinError(C.get_last_error())
   self.identity={'pid':pid,'creation':(f[0].dwHighDateTime<<32)|f[0].dwLowDateTime,'path':str(Path(name.value).resolve()),'sha256':hashlib.sha256(Path(name.value).read_bytes()).hexdigest()}
   if expected is not None and self.identity!=expected:raise ValueError('process custody mismatch')
   self.check()
  except BaseException:self.close();raise
 def check(self):
  if not self.h or K.WaitForSingleObject(self.h,0)!=258:raise ValueError('process exited')
  return dict(self.identity)
 def close(self):
  if self.h:K.CloseHandle(self.h);self.h=None
