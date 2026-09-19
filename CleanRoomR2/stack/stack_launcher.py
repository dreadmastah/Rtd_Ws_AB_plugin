#!/usr/bin/env python3
"""Supervisor for the local WSRTD relay + Binance USD-M sender."""
from __future__ import annotations

import argparse
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
RUNTIME.mkdir(exist_ok=True)
LOGS.mkdir(exist_ok=True)


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        cp = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, check=False,
        )
        out = (cp.stdout or "").strip()
        return bool(out) and not out.upper().startswith("INFO:")
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


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


def save_pids(children: dict[str, subprocess.Popen]) -> None:
    data = {"launcher": os.getpid(), **{k: v.pid for k, v in children.items()}}
    PIDFILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def stop_from_pidfile() -> int:
    if not PIDFILE.exists():
        print("WSRTD_STACK_STATUS=NOT_RUNNING")
        return 0
    try:
        data = json.loads(PIDFILE.read_text(encoding="utf-8"))
    except Exception:
        print("WSRTD_STACK_STATUS=PIDFILE_INVALID")
        return 1
    launcher = int(data.get("launcher", 0) or 0)
    if os.name == "nt" and launcher:
        subprocess.run(["taskkill", "/PID", str(launcher), "/T", "/F"], check=False)
    elif launcher:
        try:
            os.kill(launcher, signal.SIGTERM)
        except OSError:
            pass
    with contextlib_suppress(Exception):
        PIDFILE.unlink()
    print("WSRTD_STACK_STOP_REQUESTED=YES")
    return 0


def status_from_pidfile() -> int:
    if not PIDFILE.exists():
        print("WSRTD_STACK_STATUS=STOPPED")
        return 1
    data = json.loads(PIDFILE.read_text(encoding="utf-8"))
    for name, pid in data.items():
        print(f"{name.upper()}_PID={pid} ALIVE={pid_alive(int(pid))}")
    return 0


class contextlib_suppress:
    def __init__(self, *exc): self.exc = exc
    def __enter__(self): return self
    def __exit__(self, t, v, tb): return t is not None and issubclass(t, self.exc)


def run_supervisor() -> int:
    host = str(CFG["relay"].get("host", "127.0.0.1"))
    port = int(CFG["relay"].get("port", 10101))
    restart_delay = float(CFG["launcher"].get("restart_delay_seconds", 3))
    stop = False
    children: dict[str, subprocess.Popen] = {}
    log_handles = {}

    def on_signal(_sig, _frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, on_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, on_signal)

    specs = {
        "relay": [sys.executable, "-u", str(BASE / "wsrtd_relay.py")],
        "server": [sys.executable, "-u", str(BASE / "binance_usdm_server.py")],
    }

    def start_one(name: str) -> subprocess.Popen:
        path = LOGS / f"{name}_supervisor.log"
        fh = open(path, "a", encoding="utf-8", buffering=1)
        log_handles[name] = fh
        flags = 0
        if os.name == "nt":
            flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        p = subprocess.Popen(
            specs[name],
            cwd=BASE,
            stdout=fh,
            stderr=subprocess.STDOUT,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            creationflags=flags,
        )
        print(f"STARTED_{name.upper()}_PID={p.pid}")
        return p

    try:
        children["relay"] = start_one("relay")
        save_pids(children)
        if not wait_port(host, port, 15):
            raise RuntimeError(f"relay did not listen on {host}:{port}")
        print(f"RELAY_READY=YES {host}:{port}")
        children["server"] = start_one("server")
        save_pids(children)

        if bool(CFG["launcher"].get("start_amibroker", False)):
            exe = Path(str(CFG["launcher"].get("amibroker_exe", "")))
            if exe.exists():
                p = subprocess.Popen([str(exe)], cwd=exe.parent)
                children["amibroker"] = p
                save_pids(children)
                print(f"STARTED_AMIBROKER_PID={p.pid}")
            else:
                print(f"AMIBROKER_NOT_STARTED=EXE_NOT_FOUND {exe}")

        print("WSRTD_STACK_STATUS=RUNNING")
        print(f"LOG_DIR={LOGS}")
        while not stop:
            time.sleep(1)
            for name in ("relay", "server"):
                p = children[name]
                if p.poll() is not None and not stop:
                    print(f"{name.upper()}_EXITED={p.returncode} RESTARTING_IN={restart_delay}s")
                    time.sleep(restart_delay)
                    with contextlib_suppress(Exception):
                        log_handles[name].close()
                    children[name] = start_one(name)
                    save_pids(children)
    except Exception as exc:
        print(f"WSRTD_STACK_FATAL={exc}")
        return 2
    finally:
        for name, p in reversed(list(children.items())):
            if name == "amibroker":
                continue
            if p.poll() is None:
                with contextlib_suppress(Exception):
                    p.terminate()
        deadline = time.time() + 5
        for name, p in reversed(list(children.items())):
            if name == "amibroker":
                continue
            while p.poll() is None and time.time() < deadline:
                time.sleep(0.1)
            if p.poll() is None:
                with contextlib_suppress(Exception):
                    p.kill()
        for fh in log_handles.values():
            with contextlib_suppress(Exception):
                fh.close()
        with contextlib_suppress(Exception):
            PIDFILE.unlink()
        print("WSRTD_STACK_STATUS=STOPPED")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stop", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()
    if args.stop:
        return stop_from_pidfile()
    if args.status:
        return status_from_pidfile()
    return run_supervisor()


if __name__ == "__main__":
    raise SystemExit(main())
