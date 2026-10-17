"""Windows-owned supervisor for the isolated WSRTD test feed on port 18101."""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import socket
import subprocess
import sys
import time

import psutil

PORT = 18101
MUTEX = 'Local\\WSRTD_PR3_Test_18101_Supervisor'
LOG = logging.getLogger('test-supervisor')


def kernel32():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    return kernel


def acquire_mutex(name=MUTEX):
    kernel = kernel32()
    handle = kernel.CreateMutexW(None, False, name)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        kernel.CloseHandle(handle)
        return None
    return handle


def contain_process_tree():
    """The private, noninherited handle dies with this supervisor, killing children.

    Keep the returned handle open until process exit. Closing it explicitly
    would also terminate the supervisor itself. Children inherit membership,
    not the handle, and cannot keep the job alive after a supervisor crash.
    """
    class Basic(ctypes.Structure):
        _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
                    ('flags', wintypes.DWORD), ('min_ws', ctypes.c_size_t),
                    ('max_ws', ctypes.c_size_t), ('active_limit', wintypes.DWORD),
                    ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD),
                    ('scheduling', wintypes.DWORD)]
    class IO(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in
                    ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]
    class Extended(ctypes.Structure):
        _fields_ = [('basic', Basic), ('io', IO), ('process_memory', ctypes.c_size_t),
                    ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t),
                    ('peak_job', ctypes.c_size_t)]
    kernel = kernel32()
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                               ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = Extended()
    limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        error = ctypes.get_last_error()
        kernel.CloseHandle(job)
        raise ctypes.WinError(error)
    if not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
        error = ctypes.get_last_error()
        kernel.CloseHandle(job)
        raise ctypes.WinError(error)
    return job


def launch(root, runtime, script, args, name):
    with (runtime / f'{name}.log').open('a', encoding='utf-8') as log:
        proc = subprocess.Popen([sys.executable, '-u', '-B', str(root / script), *args],
                                cwd=root, stdout=log, stderr=log,
                                creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
    LOG.info('Started %s pid=%s', name, proc.pid)
    return proc


def stop_owned(proc):
    if proc is None or proc.poll() is not None:
        return
    try:
        children = psutil.Process(proc.pid).children(recursive=True)
    except psutil.NoSuchProcess:
        return
    for child in children:
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass
    if proc.poll() is None:
        proc.terminate()
    proc.wait(timeout=10)
    psutil.wait_procs(children, timeout=10)


def native_receivers():
    result = []
    for proc in psutil.process_iter(['pid', 'name', 'exe', 'create_time']):
        if (proc.info['name'] or '').lower() != 'broker.exe':
            continue
        if (proc.info['exe'] or '').lower() != r'c:\program files\amibroker\broker.exe':
            continue
        try:
            if any(c.raddr and c.raddr.port == PORT and c.status == 'ESTABLISHED'
                   for c in proc.net_connections(kind='tcp')):
                result.append((proc.pid, proc.create_time()))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return sorted(result)


def run(root, runtime):
    root, runtime = Path(root).resolve(), Path(runtime).resolve()
    for path in (root / 'Binance/sender.py', root / 'Relay/Server/Python/relay.py',
                 runtime / 'selected-symbols.txt'):
        if not path.is_file():
            raise ValueError(f'Required test-feed file missing: {path}')
    if (runtime / 'STOP').exists():
        return
    mutex = acquire_mutex()
    if mutex is None:
        return  # A healthy existing owner is not a failure or takeover target.
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                        handlers=[logging.FileHandler(runtime / 'watchdog-supervisor.log',
                                                      encoding='utf-8')])
    relay = sender = None
    try:
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', PORT))  # Never take over an occupied listener.
        job = contain_process_tree()
        LOG.info('Supervisor started pid=%s job=%s root=%s', psutil.Process().pid, job, root)
        prior_receivers = []
        while not (runtime / 'STOP').exists():
            if relay is None or relay.poll() is not None:
                if relay is not None:
                    LOG.warning('Relay exited code=%s; rebuilding test feed', relay.returncode)
                stop_owned(sender)
                sender = None
                relay = launch(root, runtime, 'Relay/Server/Python/relay.py',
                               [str(PORT), '--protocol', 'path'], 'relay')
                prior_receivers = []
                time.sleep(2)
            receivers = native_receivers()
            if not receivers:
                if sender is not None:
                    LOG.warning('No native receiver; pausing sender until reconnect')
                    stop_owned(sender)
                    sender = None
            elif sender is None or sender.poll() is not None or receivers != prior_receivers:
                if sender is not None:
                    LOG.warning('Sender exit or receiver change; rehydrate from REST')
                    stop_owned(sender)
                sender = launch(root, runtime, 'Binance/sender.py',
                                ['--symbols', str(runtime / 'selected-symbols.txt'), '--limit', '500',
                                 '--relay', f'ws://127.0.0.1:{PORT}/sender',
                                 '--native-history', '--quotes'], 'sender')
            prior_receivers = receivers
            status = dict(utc=datetime.now(timezone.utc).isoformat(),
                          supervisor_pid=psutil.Process().pid,
                          supervisor_created=psutil.Process().create_time(),
                          job_contained=True, source_root=str(root),
                          relay_pid=relay.pid, relay_running=relay.poll() is None,
                          sender_pid=sender.pid if sender else None,
                          sender_running=sender is not None and sender.poll() is None,
                          native_receivers=receivers, symbols=500, port=PORT)
            temp = runtime / 'status.tmp'
            temp.write_text(json.dumps(status, indent=2) + '\n', encoding='utf-8')
            temp.replace(runtime / 'status.json')
            time.sleep(5)
    finally:
        stop_owned(sender)
        stop_owned(relay)
        kernel32().CloseHandle(mutex)
        # Do not close the job here: it includes this process. OS teardown closes it.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--runtime', required=True, type=Path)
    args = parser.parse_args()
    if sys.platform != 'win32':
        parser.error('This supervisor requires Windows')
    run(args.root, args.runtime)


if __name__ == '__main__':
    main()
