"""Own-test-instance nonblocking Windows named-pipe snapshot publisher."""
import ctypes as C,threading,time,os
from ctypes import wintypes as W
K=C.WinDLL('kernel32',use_last_error=True)
K.CreateNamedPipeW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,W.DWORD,W.DWORD,W.DWORD,W.DWORD,C.c_void_p];K.CreateNamedPipeW.restype=W.HANDLE
K.ConnectNamedPipe.argtypes=[W.HANDLE,C.c_void_p];K.ConnectNamedPipe.restype=W.BOOL
K.WriteFile.argtypes=[W.HANDLE,C.c_void_p,W.DWORD,C.POINTER(W.DWORD),C.c_void_p];K.WriteFile.restype=W.BOOL
K.DisconnectNamedPipe.argtypes=[W.HANDLE];K.CloseHandle.argtypes=[W.HANDLE]
K.GetCurrentProcess.restype=W.HANDLE
K.GetProcessTimes.argtypes=[W.HANDLE,C.POINTER(W.FILETIME),C.POINTER(W.FILETIME),C.POINTER(W.FILETIME),C.POINTER(W.FILETIME)]
def creation():
    f=[W.FILETIME() for _ in range(4)]
    if not K.GetProcessTimes(K.GetCurrentProcess(),*[C.byref(x) for x in f]):raise C.WinError(C.get_last_error())
    return (f[0].dwHighDateTime<<32)|f[0].dwLowDateTime
class Pipe:
    def __init__(self,receiver,dbkey):
        self.receiver=receiver;self.dbkey=dbkey;self.name='\\\\.\\pipe\\WSRTD_FORMING_R5_'+receiver.session
        self.stop=threading.Event();self.error=None;self.writes=0
        # Outbound, first instance, byte stream, NOWAIT, reject remote clients.
        self.handle=K.CreateNamedPipeW(self.name,2|0x00080000,1|8,1,8*1024*1024,0,0,None)
        if self.handle in (None,C.c_void_p(-1).value):raise C.WinError(C.get_last_error())
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def run(self):
        try:
            while not self.stop.is_set():
                ok=K.ConnectNamedPipe(self.handle,None);err=C.get_last_error()
                if ok or err==535:
                    b=self.receiver.binary(self.dbkey);buf=C.create_string_buffer(b);n=W.DWORD()
                    if K.WriteFile(self.handle,buf,len(b),C.byref(n),None) and n.value==len(b):self.writes+=1
                    # Nonblocking pipe must retain connection while client reads.
                    self.stop.wait(.08);K.DisconnectNamedPipe(self.handle)
                else:self.stop.wait(.005)
        except Exception as e:self.error=repr(e)
    def close(self):
        self.stop.set();self.thread.join(2)
        if self.thread.is_alive():raise RuntimeError('own pipe thread failed shutdown')
        K.DisconnectNamedPipe(self.handle);K.CloseHandle(self.handle)
