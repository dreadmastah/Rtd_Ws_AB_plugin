#!/usr/bin/env python3
"""Supervisor and watchdog helper for WSRTD R2.1 automatic recovery."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
CFG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
RUNTIME = BASE / "runtime"
LOGS = BASE / "logs"
PIDFILE = RUNTIME / "stack_pids.json"
PAUSEFILE = RUNTIME / "maintenance_pause"
RUNTIME.mkdir(exist_ok=True)
LOGS.mkdir(exist_ok=True)

WINDOWS_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
WINDOWS_CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


def windows_hidden_flags(*, new_process_group: bool = False) -> int:
    if os.name != "nt":
        return 0
    flags = WINDOWS_CREATE_NO_WINDOW
    if new_process_group:
        flags |= WINDOWS_CREATE_NEW_PROCESS_GROUP
    return flags


def console_python() -> str:
    if os.name == "nt":
        candidates = [
            BASE / ".venv" / "Scripts" / "python.exe",
            Path(sys.executable).with_name("python.exe"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
    return sys.executable


if os.name == "nt" and sys.stdout is None:
    sys.stdout = open(LOGS / "headless_entrypoint.log", "a", encoding="utf-8", buffering=1)
if os.name == "nt" and sys.stderr is None:
    sys.stderr = sys.stdout


def instance_key(dbname: str, relay_port: int) -> str:
    return f"{dbname.strip().upper()}:{int(relay_port)}"


def instance_token(dbname: str, relay_port: int) -> str:
    return hashlib.sha256(instance_key(dbname, relay_port).encode("utf-8")).hexdigest()[:24]


def instance_lock_identity(dbname: str, relay_port: int) -> str:
    token = instance_token(dbname, relay_port)
    if os.name == "nt":
        return f"Local\\WSRTD.Stack.{token}"
    return str(RUNTIME / f"instance_{token}.lock")


def stop_request_path(dbname: str, relay_port: int) -> Path:
    return RUNTIME / f"stop_{instance_token(dbname, relay_port)}.request"


class InstanceLock:
    """Pair-scoped launcher ownership, using an auto-released Windows mutex."""

    def __init__(self, dbname: str, relay_port: int) -> None:
        self.dbname = dbname.strip() or "WSRTD"
        self.relay_port = int(relay_port)
        self.identity = instance_lock_identity(self.dbname, self.relay_port)
        self._handle = None
        self._fd: int | None = None
        self._path = RUNTIME / f"instance_{instance_token(self.dbname, self.relay_port)}.lock"

    def acquire(self) -> bool:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
            kernel32.CreateMutexW.restype = wintypes.HANDLE
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            handle = kernel32.CreateMutexW(None, False, self.identity)
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())
            if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
                kernel32.CloseHandle(handle)
                return False
            self._handle = handle
            return True

        payload = json.dumps({
            "pid": os.getpid(),
            "dbname": self.dbname,
            "relay_port": self.relay_port,
        }) + "\n"
        for _attempt in range(2):
            try:
                self._fd = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(self._fd, payload.encode("utf-8"))
                return True
            except FileExistsError:
                try:
                    owner = json.loads(self._path.read_text(encoding="utf-8"))
                    owner_pid = int(owner.get("pid", 0) or 0)
                except Exception:
                    owner_pid = 0
                if owner_pid and pid_alive(owner_pid):
                    return False
                try:
                    self._path.unlink()
                except OSError:
                    return False
        return False

    def release(self) -> None:
        if os.name == "nt" and self._handle is not None:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            if not kernel32.CloseHandle(self._handle):
                raise ctypes.WinError(ctypes.get_last_error())
            self._handle = None
        if self._fd is not None:
            try:
                os.close(self._fd)
            finally:
                self._fd = None
            try:
                self._path.unlink()
            except OSError:
                pass


def instance_running(dbname: str, relay_port: int) -> bool:
    probe = InstanceLock(dbname, relay_port)
    acquired = probe.acquire()
    if acquired:
        probe.release()
        return False
    return True


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        cp = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=windows_hidden_flags(),
        )
        out = (cp.stdout or "").strip()
        return bool(out) and not out.upper().startswith("INFO:")
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def process_name_running(image_name: str) -> bool:
    if os.name != "nt":
        return False
    cp = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        check=False,
        creationflags=windows_hidden_flags(),
    )
    out = (cp.stdout or "").strip()
    return bool(out) and not out.upper().startswith("INFO:")


def wait_port(host: str, port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    request = (
        "GET /receiver HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Key: MDEyMzQ1Njc4OWFiY2RlZg==\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    ).encode("ascii")
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.8) as s:
                s.sendall(request)
                response = s.recv(512)
                if b" 101 " in response:
                    return True
        except OSError:
            pass
        time.sleep(0.25)
    return False


def load_pidfile() -> dict[str, object]:
    if not PIDFILE.exists():
        return {}
    try:
        raw = json.loads(PIDFILE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def pid_value(data: dict[str, object], name: str) -> int:
    try:
        return max(0, int(data.get(name, 0) or 0))
    except (TypeError, ValueError):
        return 0


def save_pids(
    children: dict[str, subprocess.Popen],
    *,
    dbname: str,
    relay_port: int,
    lock_identity: str,
) -> None:
    data: dict[str, object] = {
        "launcher": os.getpid(),
        "dbname": dbname,
        "relay_port": relay_port,
        "instance_lock": lock_identity,
        "python_executable": sys.executable,
        "working_directory": str(BASE),
        **{k: v.pid for k, v in children.items() if v is not None},
    }
    tmp = PIDFILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, PIDFILE)


def critical_stack_alive() -> tuple[bool, dict[str, object]]:
    data = load_pidfile()
    if not data:
        return False, data
    required = ["launcher", "relay", "server"]
    if bool(CFG.get("identity_bridge", {}).get("enabled", False)):
        required.append("identity")
    return all(pid_alive(pid_value(data, k)) for k in required), data


def status_from_pidfile() -> int:
    if PAUSEFILE.exists():
        print("WSRTD_MAINTENANCE_PAUSED=YES")
    alive, data = critical_stack_alive()
    if not data:
        print("WSRTD_STACK_STATUS=STOPPED")
        return 1
    for name in ("launcher", "relay", "server", "identity", "amibroker"):
        pid = pid_value(data, name)
        if pid:
            print(f"{name.upper()}_PID={pid} ALIVE={pid_alive(pid)}")
    for name in ("dbname", "relay_port", "instance_lock", "python_executable", "working_directory"):
        if name in data:
            print(f"{name.upper()}={data[name]}")
    print(f"WSRTD_STACK_STATUS={'RUNNING' if alive else 'STALE_OR_DEGRADED'}")
    return 0 if alive else 1


def stop_from_pidfile(dbname: str, relay_port: int) -> int:
    data = load_pidfile()
    if not data:
        PAUSEFILE.write_text("manual-stop\n", encoding="utf-8")
        print("WSRTD_STACK_STATUS=NOT_RUNNING")
        return 0
    recorded_dbname = str(data.get("dbname", dbname))
    recorded_port = int(data.get("relay_port", relay_port) or relay_port)
    if instance_key(recorded_dbname, recorded_port) != instance_key(dbname, relay_port):
        print(
            f"WSRTD_STOP_REFUSED=INSTANCE_MISMATCH "
            f"REQUESTED={instance_key(dbname, relay_port)} "
            f"RUNNING={instance_key(recorded_dbname, recorded_port)}"
        )
        return 2
    PAUSEFILE.write_text("manual-stop\n", encoding="utf-8")
    launcher = pid_value(data, "launcher")
    request = stop_request_path(dbname, relay_port)
    request.write_text(
        json.dumps({"requested_by_pid": os.getpid(), "requested_unix_ms": int(time.time() * 1000)}) + "\n",
        encoding="utf-8",
    )
    print(f"WSRTD_STOP_REQUEST_FILE={request}")
    deadline = time.time() + 12
    while launcher and pid_alive(launcher) and time.time() < deadline:
        time.sleep(0.2)
    if launcher and pid_alive(launcher):
        print(f"WSRTD_STOP_GRACEFUL_TIMEOUT LAUNCHER_PID={launcher}")
        for name in ("identity", "server", "relay"):
            child = pid_value(data, name)
            if child and pid_alive(child):
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(child), "/T", "/F"],
                        check=False,
                        creationflags=windows_hidden_flags(),
                    )
                else:
                    try:
                        os.kill(child, signal.SIGKILL)
                    except OSError:
                        pass
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(launcher), "/F"],
                check=False,
                creationflags=windows_hidden_flags(),
            )
        else:
            try:
                os.kill(launcher, signal.SIGKILL)
            except OSError:
                pass
    try:
        PIDFILE.unlink()
    except OSError:
        pass
    try:
        request.unlink()
    except OSError:
        pass
    print("WSRTD_STACK_STOP_REQUESTED=YES")
    return 0


def configure_registry(dbname: str, relay_port: int) -> bool:
    if os.name != "nt":
        return True
    script = BASE / "configure_plugin_registry.cmd"
    cp = subprocess.run(
        ["cmd.exe", "/d", "/c", str(script), dbname, str(relay_port)],
        cwd=BASE,
        check=False,
        creationflags=windows_hidden_flags(),
    )
    return cp.returncode == 0


def ensure_running(dbname: str, relay_port: int) -> int:
    if PAUSEFILE.exists():
        print("WSRTD_ENSURE_RUNNING=MAINTENANCE_PAUSED")
        return 0
    if instance_running(dbname, relay_port):
        print("WSRTD_ENSURE_RUNNING=ALREADY_RUNNING")
        return 0
    try:
        PIDFILE.unlink()
    except OSError:
        pass
    if not configure_registry(dbname, relay_port):
        print("WSRTD_ENSURE_RUNNING=FAIL_REGISTRY")
        return 2

    log_path = LOGS / "autostart_supervisor.log"
    fh = open(log_path, "a", encoding="utf-8", buffering=1)
    flags = windows_hidden_flags(new_process_group=True)
    kwargs: dict[str, object] = {}
    if os.name != "nt":
        kwargs["start_new_session"] = True
    p = subprocess.Popen(
        [
            console_python(),
            "-u",
            str(Path(__file__).resolve()),
            "--dbname",
            dbname,
            "--relay-port",
            str(relay_port),
        ],
        cwd=BASE,
        stdout=fh,
        stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        creationflags=flags,
        **kwargs,
    )
    print(f"WSRTD_ENSURE_RUNNING=STARTED LAUNCHER_PID={p.pid}")
    return 0


def run_supervisor(dbname: str, relay_port: int | None = None) -> int:
    host = str(os.getenv("WSRTD_RELAY_HOST", CFG["relay"].get("host", "127.0.0.1")))
    port = int(
        relay_port
        if relay_port is not None
        else os.getenv("WSRTD_RELAY_PORT", CFG["relay"].get("port", 10101))
    )
    lock = InstanceLock(dbname, port)
    if not lock.acquire():
        print(f"Another WSRTD stack instance is already running for {dbname} / port {port}.")
        print(f"INSTANCE_LOCK={lock.identity}")
        return 3

    request = stop_request_path(dbname, port)
    try:
        request.unlink()
    except OSError:
        pass
    data = load_pidfile()
    if data and pid_value(data, "launcher") != os.getpid():
        prior_launcher = pid_value(data, "launcher")
        if prior_launcher and pid_alive(prior_launcher):
            print(
                f"WSRTD_STACK_STATUS=RUNTIME_DIRECTORY_ALREADY_OWNED "
                f"LAUNCHER_PID={prior_launcher}"
            )
            lock.release()
            return 4
        print(f"STALE_PIDFILE_REMOVED={PIDFILE}")
        try:
            PIDFILE.unlink()
        except OSError:
            pass

    print(f"LAUNCHER_PID={os.getpid()}")
    print(f"PYTHON_EXECUTABLE={sys.executable}")
    print(f"WORKING_DIRECTORY={BASE}")
    print(f"DBNAME={dbname}")
    print(f"RELAY_PORT={port}")
    print(f"INSTANCE_LOCK={lock.identity}")
    try:
        return run_supervisor_locked(dbname, host, port, lock.identity, request)
    finally:
        lock.release()
        print(f"INSTANCE_LOCK_RELEASED={lock.identity}")


def run_supervisor_locked(
    dbname: str,
    host: str,
    port: int,
    lock_identity: str,
    stop_request: Path,
) -> int:
    restart_delay = float(CFG["launcher"].get("restart_delay_seconds", 3))
    start_amibroker = bool(CFG["launcher"].get("start_amibroker", False))
    keep_amibroker_running = bool(CFG["launcher"].get("keep_amibroker_running", start_amibroker))
    amibroker_delay = max(0.0, float(CFG["launcher"].get("amibroker_start_delay_seconds", 2)))
    amibroker_exe = Path(str(CFG["launcher"].get("amibroker_exe", "")))
    stop = False
    children: dict[str, subprocess.Popen] = {}
    log_handles: dict[str, object] = {}

    def on_signal(sig, _frame):
        nonlocal stop
        print(f"WSRTD_STACK_SIGNAL={sig} STOPPING=YES")
        stop = True

    signal.signal(signal.SIGINT, on_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, on_signal)

    child_python = console_python()
    specs = {
        "relay": [child_python, "-u", str(BASE / "wsrtd_relay.py")],
        "server": [child_python, "-u", str(BASE / "binance_usdm_server.py")],
    }
    if bool(CFG.get("identity_bridge", {}).get("enabled", False)):
        specs["identity"] = [child_python, "-u", str(BASE / "identity_bridge.py")]

    child_env = {
        **os.environ,
        "PYTHONUNBUFFERED": "1",
        "WSRTD_RELAY_HOST": host,
        "WSRTD_RELAY_PORT": str(port),
        "WSRTD_RELAY_URI": f"ws://{host}:{port}/sender",
    }

    def start_one(name: str) -> subprocess.Popen:
        path = LOGS / f"{name}_supervisor.log"
        fh = open(path, "a", encoding="utf-8", buffering=1)
        log_handles[name] = fh
        flags = windows_hidden_flags(new_process_group=True)
        p = subprocess.Popen(
            specs[name],
            cwd=BASE,
            stdout=fh,
            stderr=subprocess.STDOUT,
            env=child_env,
            creationflags=flags,
        )
        print(
            f"STARTED_{name.upper()}_PID={p.pid} "
            f"PYTHON={specs[name][0]} SCRIPT={specs[name][-1]}"
        )
        return p

    def start_amibroker_if_needed() -> None:
        if not start_amibroker or not amibroker_exe.exists():
            if start_amibroker and not amibroker_exe.exists():
                print(f"AMIBROKER_NOT_STARTED=EXE_NOT_FOUND {amibroker_exe}")
            return
        if process_name_running(amibroker_exe.name):
            return
        if amibroker_delay:
            time.sleep(amibroker_delay)
        amibroker_env = {
            **os.environ,
            "ASTU_STATUS_DIR": str((BASE / "runtime" / "autotrader_status").resolve()),
        }
        p = subprocess.Popen(
            [str(amibroker_exe)],
            cwd=amibroker_exe.parent,
            env=amibroker_env,
        )
        children["amibroker"] = p
        save_pids(
            children,
            dbname=dbname,
            relay_port=port,
            lock_identity=lock_identity,
        )
        print(f"STARTED_AMIBROKER_PID={p.pid}")

    try:
        children["relay"] = start_one("relay")
        save_pids(children, dbname=dbname, relay_port=port, lock_identity=lock_identity)
        if not wait_port(host, port, 15):
            raise RuntimeError(f"relay did not listen on {host}:{port}")
        print(f"RELAY_READY=YES {host}:{port}")
        children["server"] = start_one("server")
        save_pids(children, dbname=dbname, relay_port=port, lock_identity=lock_identity)
        if "identity" in specs:
            children["identity"] = start_one("identity")
            save_pids(children, dbname=dbname, relay_port=port, lock_identity=lock_identity)
        start_amibroker_if_needed()

        print("WSRTD_STACK_STATUS=RUNNING")
        print(f"LOG_DIR={LOGS}")
        while not stop:
            time.sleep(1)
            if stop_request.exists():
                print(f"WSRTD_STOP_REQUEST_DETECTED={stop_request}")
                stop = True
                continue
            for name in tuple(specs):
                p = children[name]
                if p.poll() is not None and not stop:
                    print(f"{name.upper()}_EXITED={p.returncode} RESTARTING_IN={restart_delay}s")
                    time.sleep(restart_delay)
                    try:
                        log_handles[name].close()
                    except Exception:
                        pass
                    children[name] = start_one(name)
                    save_pids(children, dbname=dbname, relay_port=port, lock_identity=lock_identity)
            if keep_amibroker_running and not process_name_running(amibroker_exe.name):
                start_amibroker_if_needed()
    except Exception as exc:
        print(f"WSRTD_STACK_FATAL={exc}")
        return 2
    finally:
        owned_services = [
            (name, children[name])
            for name in ("relay", "server", "identity")
            if name in children
        ]
        for name, p in owned_services:
            if p.poll() is None:
                try:
                    print(f"STOPPING_{name.upper()}_PID={p.pid}")
                    p.terminate()
                except Exception:
                    pass
        deadline = time.time() + 5
        for name, p in owned_services:
            while p.poll() is None and time.time() < deadline:
                time.sleep(0.1)
            if p.poll() is None:
                try:
                    print(f"FORCE_STOPPING_{name.upper()}_PID={p.pid}")
                    p.kill()
                except Exception:
                    pass
        for fh in log_handles.values():
            try:
                fh.close()
            except Exception:
                pass
        try:
            PIDFILE.unlink()
        except OSError:
            pass
        try:
            stop_request.unlink()
        except OSError:
            pass
        print("WSRTD_STACK_STATUS=STOPPED")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stop", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--ensure-running", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--dbname", default="WSRTD")
    ap.add_argument("--relay-port", type=int)
    args = ap.parse_args()
    relay_port = args.relay_port if args.relay_port is not None else int(
        os.getenv("WSRTD_RELAY_PORT", CFG["relay"].get("port", 10101))
    )
    if args.stop:
        return stop_from_pidfile(args.dbname, relay_port)
    if args.status:
        return status_from_pidfile()
    if args.resume:
        try:
            PAUSEFILE.unlink()
        except OSError:
            pass
        print("WSRTD_MAINTENANCE_PAUSED=NO")
        return 0
    if args.ensure_running:
        return ensure_running(args.dbname, relay_port)
    return run_supervisor(args.dbname, relay_port)


if __name__ == "__main__":
    raise SystemExit(main())
