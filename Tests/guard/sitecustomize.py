"""RC2 test-process guard, inherited by disposable Python children only."""
import os,socket,sys
from pathlib import Path
ROOT=Path(os.environ['RC2_WORKSPACE']).resolve()
owned_ports=set()
_bind=socket.socket.bind
def bind(sock,address):
    host,port=address[:2]
    if host not in ('127.0.0.1','::1','localhost') or port!=0:
        raise PermissionError('RC2 tests require loopback ephemeral listeners')
    value=_bind(sock,address)
    owned_ports.add(sock.getsockname()[1])
    return value
socket.socket.bind=bind
def audit(event,args):
    if event=='socket.connect':
        address=args[1]
        if not isinstance(address,tuple) or address[0] not in ('127.0.0.1','::1','localhost') or address[1] not in owned_ports:
            raise PermissionError('RC2 denies external/protected/non-owned endpoint')
    elif event=='socket.getaddrinfo':
        if args[0] not in (None,'127.0.0.1','::1','localhost'):
            raise PermissionError('RC2 denies external DNS')
    elif event=='subprocess.Popen':
        command=args[1]
        executable=args[0] or (command[0] if isinstance(command,(tuple,list)) else None)
        if executable is None:
            import shlex
            executable=shlex.split(command,posix=False)[0].strip('"')
        exe=Path(executable).resolve()
        if exe!=Path(sys.executable).resolve() or not exe.is_relative_to(ROOT):
            raise PermissionError('RC2 permits only its own disposable Python children')
    elif event=='open':
        path,mode,flags=args
        writing=(isinstance(mode,str) and any(x in mode for x in 'wax+')) or (isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC))
        if writing and isinstance(path,(str,bytes,os.PathLike)):
            if os.fsdecode(path).lower()==os.devnull.lower():return
            p=Path(os.fsdecode(path)).resolve()
            if str(p).lower()!='nul' and not p.is_relative_to(ROOT):
                raise PermissionError('RC2 file writes are confined to its workspace')
    elif event in ('os.remove','os.rmdir','os.mkdir','os.rename'):
        paths=args[:2] if event=='os.rename' else args[:1]
        for path in paths:
            if isinstance(path,(str,bytes,os.PathLike)) and not Path(os.fsdecode(path)).resolve().is_relative_to(ROOT):
                raise PermissionError('RC2 filesystem mutation outside workspace')
sys.addaudithook(audit)
