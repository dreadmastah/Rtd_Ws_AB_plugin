#!/usr/bin/env python3
"""Supervisor for the simulation-only auto-trader runtime.

Processes:
- astu_execution_pipe_host.exe
- optional read-only Binance account reconciler

This launcher never enables exchange order routing. It only supervises the
simulation execution host and the read-only account snapshot producer.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
RUNTIME = ROOT / "runtime"
LOGS = RUNTIME / "logs"
PID_FILE = RUNTIME / "autotrader_sim_pids.json"
RISK_FILE = RUNTIME / "account_risk_status.v1.json"
DEFAULT_STATUS_DIR = REPO / "CleanRoomR2" / "stack" / "runtime" / "autotrader_status"
DEFAULT_HOST = REPO / "build" / "core" / "Release" / "astu_execution_pipe_host.exe"
GATEWAY = ROOT / "account" / "binance_usdm_readonly_gateway.py"
FIXTURE = ROOT / "account" / "tests" / "fixtures" / "binance_usdm_account_v3.json"

RUNTIME.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)


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


def load_pids() -> dict[str, int]:
    if not PID_FILE.exists():
        return {}
    try:
        obj = json.loads(PID_FILE.read_text(encoding="utf-8"))
        return {str(k): int(v) for k, v in obj.items() if int(v) > 0}
    except Exception:
        return {}


def save_pids(children: dict[str, subprocess.Popen]) -> None:
    obj = {
        "launcher": os.getpid(),
        **{name: proc.pid for name, proc in children.items() if proc is not None},
    }
    tmp = PID_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, PID_FILE)


def status() -> int:
    pids = load_pids()
    if not pids:
        print("ASTU_SIM_STACK_STATUS=STOPPED")
        return 1
    all_alive = True
    for name, pid in pids.items():
        alive = pid_alive(pid)
        print(f"{name.upper()}_PID={pid} ALIVE={alive}")
        all_alive = all_alive and alive
    print(f"ASTU_SIM_STACK_STATUS={'RUNNING' if all_alive else 'DEGRADED'}")
    print("ORDER_ROUTING_ENABLED=false")
    return 0 if all_alive else 1


def stop() -> int:
    pids = load_pids()
    launcher = int(pids.get("launcher", 0) or 0)
    if launcher and launcher != os.getpid() and pid_alive(launcher):
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(launcher), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            with contextlib.suppress(OSError):
                os.kill(launcher, signal.SIGTERM)
    try:
        PID_FILE.unlink()
    except OSError:
        pass
    print("ASTU_SIM_STACK_STOP_REQUESTED=YES")
    return 0


def run(args: argparse.Namespace) -> int:
    if os.name != "nt":
        print("ASTU_SIM_STACK_FATAL=Windows Named Pipe host requires Windows")
        return 2

    host = Path(args.host).resolve()
    status_dir = Path(args.status_dir).resolve()
    risk_file = Path(args.risk_file).resolve()
    journal = Path(args.journal).resolve()

    if not host.exists():
        print(f"ASTU_SIM_STACK_FATAL=missing execution host {host}")
        return 2
    if not status_dir.exists():
        print(f"ASTU_SIM_STACK_FATAL=missing WSRTD status directory {status_dir}")
        return 3

    old = load_pids()
    if old and int(old.get("launcher", 0) or 0) != os.getpid():
        if all(pid_alive(pid) for pid in old.values()):
            print("ASTU_SIM_STACK_STATUS=ALREADY_RUNNING")
            return 0
        try:
            PID_FILE.unlink()
        except OSError:
            pass

    stop_requested = False
    children: dict[str, subprocess.Popen] = {}
    logs: dict[str, object] = {}

    def on_signal(_sig, _frame):
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, on_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, on_signal)

    def start_child(name: str, command: list[str]) -> subprocess.Popen:
        log_path = LOGS / f"{name}.log"
        fh = open(log_path, "a", encoding="utf-8", buffering=1)
        logs[name] = fh
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        proc = subprocess.Popen(
            command,
            cwd=REPO,
            stdout=fh,
            stderr=subprocess.STDOUT,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            creationflags=flags,
        )
        print(f"STARTED_{name.upper()}_PID={proc.pid}")
        return proc

    risk_command: list[str] | None = None
    if args.risk_mode == "fixture":
        risk_command = [
            sys.executable,
            "-u",
            str(GATEWAY),
            "--fixture",
            str(FIXTURE),
            "--output",
            str(risk_file),
            "--poll-seconds",
            str(args.risk_poll_seconds),
        ]
    elif args.risk_mode == "readonly":
        risk_command = [
            sys.executable,
            "-u",
            str(GATEWAY),
            "--output",
            str(risk_file),
            "--poll-seconds",
            str(args.risk_poll_seconds),
        ]

    try:
        if risk_command is not None:
            children["risk"] = start_child("risk", risk_command)
            time.sleep(0.5)

        host_command = [
            str(host),
            "--status-dir",
            str(status_dir),
            "--risk-status-file",
            str(risk_file),
            "--journal",
            str(journal),
            "--max-status-age-ms",
            str(args.max_status_age_ms),
            "--max-risk-status-age-ms",
            str(args.max_risk_status_age_ms),
        ]
        children["execution"] = start_child("execution", host_command)
        save_pids(children)

        print("ASTU_SIM_STACK_STATUS=RUNNING")
        print(f"RISK_MODE={args.risk_mode}")
        print(f"STATUS_DIR={status_dir}")
        print(f"RISK_STATUS_FILE={risk_file}")
        print(f"EXECUTION_JOURNAL={journal}")
        print("ORDER_ROUTING_ENABLED=false")

        while not stop_requested:
            time.sleep(1.0)
            for name, proc in list(children.items()):
                if proc.poll() is None:
                    continue
                if stop_requested:
                    break
                print(
                    f"{name.upper()}_EXITED={proc.returncode} "
                    f"RESTARTING_IN={args.restart_delay_seconds}s"
                )
                time.sleep(args.restart_delay_seconds)
                try:
                    logs[name].close()
                except Exception:
                    pass
                command = risk_command if name == "risk" else host_command
                if command is None:
                    continue
                children[name] = start_child(name, command)
                save_pids(children)
    finally:
        for proc in reversed(list(children.values())):
            if proc.poll() is None:
                with contextlib.suppress(Exception):
                    proc.terminate()
        deadline = time.time() + 5.0
        for proc in reversed(list(children.values())):
            while proc.poll() is None and time.time() < deadline:
                time.sleep(0.1)
            if proc.poll() is None:
                with contextlib.suppress(Exception):
                    proc.kill()
        for fh in logs.values():
            with contextlib.suppress(Exception):
                fh.close()
        try:
            PID_FILE.unlink()
        except OSError:
            pass
        print("ASTU_SIM_STACK_STATUS=STOPPED")

    return 0


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--stop", action="store_true")
    ap.add_argument("--host", default=str(DEFAULT_HOST))
    ap.add_argument("--status-dir", default=str(DEFAULT_STATUS_DIR))
    ap.add_argument("--risk-file", default=str(RISK_FILE))
    ap.add_argument(
        "--journal",
        default=str(RUNTIME / "execution_journal.v1.jsonl"),
    )
    ap.add_argument(
        "--risk-mode",
        choices=("disabled", "fixture", "readonly"),
        default="disabled",
    )
    ap.add_argument("--risk-poll-seconds", type=float, default=5.0)
    ap.add_argument("--max-status-age-ms", type=int, default=5000)
    ap.add_argument("--max-risk-status-age-ms", type=int, default=7000)
    ap.add_argument("--restart-delay-seconds", type=float, default=2.0)
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    if args.status:
        return status()
    if args.stop:
        return stop()
    return run(args)


if __name__ == "__main__":
    import contextlib
    raise SystemExit(main())
