#!/usr/bin/env python3
"""Install/remove Windows automatic recovery triggers for WSRTD R2.1."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
CFG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
TASK_NAME = "WSRTD R2.1 Recovery Watchdog"
RUN_VALUE = "WSRTD_R21_AutoRecovery"


def ensure_command(dbname: str, relay_port: int) -> str:
    scripts = BASE / ".venv" / "Scripts"
    py = scripts / "pythonw.exe"
    if not py.exists():
        py = scripts / "python.exe"
    launcher = BASE / "stack_launcher.py"
    return subprocess.list2cmdline([
        str(py),
        str(launcher),
        "--ensure-running",
        "--dbname",
        dbname,
        "--relay-port",
        str(relay_port),
    ])


def install(dbname: str) -> int:
    if os.name != "nt":
        print("WSRTD_AUTOSTART=FAIL_WINDOWS_ONLY")
        return 2
    py = BASE / ".venv" / "Scripts" / "python.exe"
    pause = BASE / "runtime" / "maintenance_pause"
    try:
        pause.unlink()
    except OSError:
        pass
    if not py.exists():
        print("WSRTD_AUTOSTART=FAIL_VENV_MISSING")
        return 2

    import winreg

    relay_port = int(CFG.get("relay", {}).get("port", 10101))
    command = ensure_command(dbname, relay_port)
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, command)

    minutes = max(1, int(CFG.get("launcher", {}).get("watchdog_minutes", 5)))
    cp = subprocess.run(
        [
            "schtasks.exe", "/Create", "/TN", TASK_NAME,
            "/SC", "MINUTE", "/MO", str(minutes),
            "/TR", command,
            "/RL", "LIMITED", "/F",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if cp.returncode != 0:
        print("WSRTD_AUTOSTART=PARTIAL_RUN_KEY_ONLY")
        print((cp.stdout or "").strip())
        print((cp.stderr or "").strip())
        return 1

    (BASE / "runtime").mkdir(exist_ok=True)
    (BASE / "runtime" / "autostart_dbname.txt").write_text(dbname + "\n", encoding="utf-8")
    print(
        f"WSRTD_AUTOSTART=PASS DBNAME={dbname} RELAY_PORT={relay_port} "
        f"WATCHDOG_MINUTES={minutes}"
    )
    print(f"RUN_COMMAND={command}")
    return 0


def uninstall() -> int:
    if os.name != "nt":
        print("WSRTD_AUTOSTART=FAIL_WINDOWS_ONLY")
        return 2
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, RUN_VALUE)
    except FileNotFoundError:
        pass

    subprocess.run(
        ["schtasks.exe", "/Delete", "/TN", TASK_NAME, "/F"],
        check=False,
        capture_output=True,
        text=True,
    )
    print("WSRTD_AUTOSTART=REMOVED")
    return 0


def status() -> int:
    if os.name != "nt":
        print("WSRTD_AUTOSTART=FAIL_WINDOWS_ONLY")
        return 2
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    run_value = ""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            run_value = winreg.QueryValueEx(key, RUN_VALUE)[0]
    except FileNotFoundError:
        pass
    cp = subprocess.run(
        ["schtasks.exe", "/Query", "/TN", TASK_NAME, "/FO", "LIST", "/V"],
        check=False,
        capture_output=True,
        text=True,
    )
    print(f"RUN_KEY_PRESENT={bool(run_value)}")
    if run_value:
        print(f"RUN_COMMAND={run_value}")
    print(f"WATCHDOG_TASK_PRESENT={cp.returncode == 0}")
    if cp.returncode == 0:
        print(cp.stdout.strip())
    return 0 if run_value and cp.returncode == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--install", action="store_true")
    g.add_argument("--uninstall", action="store_true")
    g.add_argument("--status", action="store_true")
    ap.add_argument("--dbname", default="WSRTD")
    args = ap.parse_args()
    if args.install:
        return install(args.dbname)
    if args.uninstall:
        return uninstall()
    return status()


if __name__ == "__main__":
    raise SystemExit(main())
