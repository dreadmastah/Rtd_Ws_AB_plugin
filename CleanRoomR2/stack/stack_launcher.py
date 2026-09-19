#!/usr/bin/env python3
"""Supervisor and watchdog helper for WSRTD R2.1 automatic recovery."""
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
PAUSEFILE = RUNTIME / "maintenance_pause"
RUNTIME.mkdir(exist_ok=True)
LOGS.mkdir(exist_ok=True)


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        cp = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            check=False,
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


def load_pidfile() -> dict[str, int]:
    if not PIDFILE.exists():
        return {}
    try:
        raw = json.loads(PIDFILE.read_text(encoding="utf-8"))
        return {str(k): int(v) for k, v in raw.items() if int(v) > 0}
    except Exception:
        return {}


def save_pids(children: dict[str, subprocess.Popen]) -> None:
    data = {"launcher": os.getpid(), **{k: v.pid for k, v in children.items() if v is not None}}
    tmp = PIDFILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, PIDFILE)


def critical_stack_alive() -> tuple[bool, dict[str, int]]:
    data = load_pidfile()
    if not data:
        return False, data
    required = ["launcher", "relay", "server"]
    if bool(CFG.get("identity_bridge", {}).get("enabled", False)):
        required.append("identity")
    return all(pid_alive(int(data.get(k, 0))) for k in required), data


def status_from_pidfile() -> int:
    if PAUSEFILE.exists():
        print("WSRTD_MAINTENANCE_PAUSED=YES")
    alive, data = critical_stack_alive()
    if not data:
        print("WSRTD_STACK_STATUS=STOPPED")
        return 1
    for name, pid in data.items():
        print(f"{name.upper()}_PID={pid} ALIVE={pid_alive(pid)}")
    print(f"WSRTD_STACK_STATUS={'RUNNING' if alive else 'STALE_OR_DEGRADED'}")
    return 0 if alive else 1


def stop_from_pidfile() -> int:
    PAUSEFILE.write_text("manual-stop\n", encoding="utf-8")
    data = load_pidfile()
    if not data:
        print("WSRTD_STACK_STATUS=NOT_RUNNING")
        return 0
    launcher = int(data.get("launcher", 0) or 0)
    if os.name == "nt" and launcher and pid_alive(launcher):
        subprocess.run(["taskkill", "/PID", str(launcher), "/T", "/F"], check=False)
    elif launcher and pid_alive(launcher):
        try:
            os.kill(launcher, signal.SIGTERM)
        except OSError:
            pass
    try:
        PIDFILE.unlink()
    except OSError:
        pass
    print("WSRTD_STACK_STOP_REQUESTED=YES")
    return 0


def configure_registry(dbname: str) -> bool:
    if os.name != "nt":
        return True
    script = BASE / "configure_plugin_registry.cmd"
    cp = subprocess.run(["cmd.exe", "/d", "/c", str(script), dbname], cwd=BASE, check=False)
    return cp.returncode == 0


def ensure_running(dbname: str) -> int:
    if PAUSEFILE.exists():
        print("WSRTD_ENSURE_RUNNING=MAINTENANCE_PAUSED")
        return 0
    alive, _data = critical_stack_alive()
    if alive:
        print("WSRTD_ENSURE_RUNNING=ALREADY_RUNNING")
        return 0
    try:
        PIDFILE.unlink()
    except OSError:
        pass
    if not configure_registry(dbname):
        print("WSRTD_ENSURE_RUNNING=FAIL_REGISTRY")
        return 2

    log_path = LOGS / "autostart_supervisor.log"
    fh = open(log_path, "a", encoding="utf-8", buffering=1)
    flags = 0
    kwargs: dict[str, object] = {}
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    else:
        kwargs["start_new_session"] = True
    p = subprocess.Popen(
        [sys.executable, "-u", str(Path(__file__).resolve())],
        cwd=BASE,
        stdout=fh,
        stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        creationflags=flags,
        **kwargs,
    )
    print(f"WSRTD_ENSURE_RUNNING=STARTED LAUNCHER_PID={p.pid}")
    return 0


def run_supervisor() -> int:
    already, data = critical_stack_alive()
    if already and int(data.get("launcher", 0)) != os.getpid():
        print(f"WSRTD_STACK_STATUS=ALREADY_RUNNING LAUNCHER_PID={data.get('launcher')}")
        return 0
    if data and not already:
        try:
            PIDFILE.unlink()
        except OSError:
            pass

    host = str(CFG["relay"].get("host", "127.0.0.1"))
    port = int(CFG["relay"].get("port", 10101))
    restart_delay = float(CFG["launcher"].get("restart_delay_seconds", 3))
    start_amibroker = bool(CFG["launcher"].get("start_amibroker", False))
    keep_amibroker_running = bool(CFG["launcher"].get("keep_amibroker_running", start_amibroker))
    amibroker_delay = max(0.0, float(CFG["launcher"].get("amibroker_start_delay_seconds", 2)))
    amibroker_exe = Path(str(CFG["launcher"].get("amibroker_exe", "")))
    stop = False
    children: dict[str, subprocess.Popen] = {}
    log_handles: dict[str, object] = {}

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
    if bool(CFG.get("identity_bridge", {}).get("enabled", False)):
        specs["identity"] = [sys.executable, "-u", str(BASE / "identity_bridge.py")]

    def start_one(name: str) -> subprocess.Popen:
        path = LOGS / f"{name}_supervisor.log"
        fh = open(path, "a", encoding="utf-8", buffering=1)
        log_handles[name] = fh
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
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
        save_pids(children)
        print(f"STARTED_AMIBROKER_PID={p.pid}")

    try:
        children["relay"] = start_one("relay")
        save_pids(children)
        if not wait_port(host, port, 15):
            raise RuntimeError(f"relay did not listen on {host}:{port}")
        print(f"RELAY_READY=YES {host}:{port}")
        children["server"] = start_one("server")
        save_pids(children)
        if "identity" in specs:
            children["identity"] = start_one("identity")
            save_pids(children)
        start_amibroker_if_needed()

        print("WSRTD_STACK_STATUS=RUNNING")
        print(f"LOG_DIR={LOGS}")
        while not stop:
            time.sleep(1)
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
                    save_pids(children)
            if keep_amibroker_running and not process_name_running(amibroker_exe.name):
                start_amibroker_if_needed()
    except Exception as exc:
        print(f"WSRTD_STACK_FATAL={exc}")
        return 2
    finally:
        for name, p in reversed(list(children.items())):
            if name == "amibroker":
                continue
            if p.poll() is None:
                try:
                    p.terminate()
                except Exception:
                    pass
        deadline = time.time() + 5
        for name, p in reversed(list(children.items())):
            if name == "amibroker":
                continue
            while p.poll() is None and time.time() < deadline:
                time.sleep(0.1)
            if p.poll() is None:
                try:
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
        print("WSRTD_STACK_STATUS=STOPPED")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stop", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--ensure-running", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--dbname", default="WSRTD")
    args = ap.parse_args()
    if args.stop:
        return stop_from_pidfile()
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
        return ensure_running(args.dbname)
    return run_supervisor()


if __name__ == "__main__":
    raise SystemExit(main())
