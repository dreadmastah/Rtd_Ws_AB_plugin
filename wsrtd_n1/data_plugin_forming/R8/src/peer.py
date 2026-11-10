"""Windows IPv4 established TCP reverse-tuple custody; read-only OS table."""
import ctypes as C,socket,struct
from ctypes import wintypes as W
from custody import Attestation
api=C.WinDLL('iphlpapi').GetExtendedTcpTable
api.argtypes=[C.c_void_p,C.POINTER(W.DWORD),W.BOOL,W.ULONG,C.c_int,W.ULONG];api.restype=W.DWORD
def owner(s):
 local=s.getsockname();remote=s.getpeername();size=W.DWORD()
 status=api(None,C.byref(size),False,socket.AF_INET,5,0)
 if status!=122 or not 4<=size.value<=8*1024*1024:raise ValueError('TCP table bound')
 buf=C.create_string_buffer(size.value)
 status=api(buf,C.byref(size),False,socket.AF_INET,5,0)
 if status:raise OSError(status,'TCP owner query')
 n=struct.unpack_from('<I',buf.raw)[0]
 if 4+n*24>size.value:raise ValueError('TCP rows')
 hits=[]
 for i in range(n):
  r=buf.raw[4+i*24:4+(i+1)*24]
  state,=struct.unpack_from('<I',r)
  source=(socket.inet_ntoa(r[4:8]),int.from_bytes(r[8:10],'big'))
  dest=(socket.inet_ntoa(r[12:16]),int.from_bytes(r[16:18],'big'))
  if state==5 and source==remote and dest==local:hits.append(struct.unpack_from('<I',r,20)[0])
 if len(hits)!=1:raise ValueError('nonunique or absent peer tuple')
 return hits[0]
class Peer:
 def __init__(self,s,expected,role):
  self.socket=s;self.role=role;self.expected=dict(expected);self.handle=None
  if owner(s)!=expected['pid']:raise ValueError('TCP peer PID mismatch')
  self.handle=Attestation(expected['pid'],expected)
  try:self.check()
  except BaseException:self.close();raise
 def check(self):
  self.handle.check()
  if owner(self.socket)!=self.expected['pid']:raise ValueError('TCP tuple custody changed')
  return dict(role=self.role,identity=self.expected)
 def close(self):
  if self.handle:self.handle.close();self.handle=None
