"""Fail-closed Windows WSRTD cohort inspection and handle-bound cleanup.

No PID-only or recursive taskkill operations. Command lines stay in memory.
The caller must hold the instance lock throughout cleanup and startup.
"""
from __future__ import annotations

import ctypes
import json
import ntpath
import os
import re
from pathlib import Path
import subprocess
import sys
import time
from dataclasses import dataclass


SCRIPTS = {"relay": "wsrtd_relay.py", "server": "binance_usdm_server.py",
           "identity": "identity_bridge.py"}


def normalized(path):
    return os.path.normcase(os.path.abspath(path))


def absolute_path(path):
    # On Python 3.12 Windows, isabs alone also accepts drive-relative \\foo.
    return (isinstance(path, str) and os.path.isabs(path)
            and (os.name != "nt" or bool(os.path.splitdrive(path)[0])))


def required_roles(identity_enabled):
    return {"launcher", "relay", "server"} | ({"identity"} if identity_enabled else set())


def trusted_conhost_path():
    """Resolve Windows' system directory without environment or PATH lookup."""
    if os.name != "nt":
        raise OSError("console host inspection requires Windows")
    from ctypes import wintypes
    api = ctypes.WinDLL("kernel32", use_last_error=True).GetSystemDirectoryW
    api.argtypes = [wintypes.LPWSTR, wintypes.UINT]
    api.restype = wintypes.UINT
    buffer = ctypes.create_unicode_buffer(32768)
    size = api(buffer, len(buffer))
    if not size or size >= len(buffer):
        raise OSError("system directory unavailable")
    return normalized(Path(buffer.value) / "conhost.exe")


def conhost_argv_path(path):
    """Only the observed NT prefix; never relax Python/script path rules."""
    if not isinstance(path, str):
        return None
    if path.startswith("\\??\\"):
        path = path[4:]
    # Reject relative, UNC, extended-device, and traversal representations.
    if (not re.fullmatch(r"[A-Za-z]:\\[^:]*", path)
            or any(part in (".", "..", "") for part in path[3:].split("\\"))):
        return None
    return ntpath.normcase(path)


def valid_record(record):
    return (isinstance(record, dict)
            and type(record.get("pid")) is int and record["pid"] > 0
            and type(record.get("creationTime100ns")) is int
            and record["creationTime100ns"] > 0
            and isinstance(record.get("executable"), str)
            and os.path.isabs(record["executable"]))


def command_args(command):
    from ctypes import wintypes
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    kernel.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel.LocalFree.restype = wintypes.HLOCAL
    count = ctypes.c_int()
    args = shell.CommandLineToArgvW(command, ctypes.byref(count))
    if not args:
        raise OSError("command line inspection unavailable")
    try:
        return [args[i] for i in range(count.value)]
    finally:
        kernel.LocalFree(ctypes.cast(args, wintypes.HLOCAL))


def process_snapshot():
    """Bounded, hidden CIM read; never print raw command lines or stderr."""
    if os.name != "nt":
        raise OSError("orphan recovery requires Windows process inspection")
    command = (
        "$ErrorActionPreference='Stop'; "
        "@(Get-CimInstance Win32_Process | ForEach-Object { "
        "[pscustomobject]@{pid=[int]$_.ProcessId; parent=[int]$_.ParentProcessId; "
        "executable=$_.ExecutablePath; command=$_.CommandLine; "
        "created=if ($_.CreationDate) {$_.CreationDate.ToUniversalTime().ToFileTimeUtc()} "
        "else {0}} }) | ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, text=True, check=True, timeout=15,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    rows = json.loads(result.stdout)
    if not isinstance(rows, list):
        raise ValueError("invalid process snapshot")
    snapshot = {}
    for row in rows:
        pid = row["pid"]
        if type(pid) is not int or pid in snapshot:
            raise ValueError("invalid process snapshot identity")
        row["argv"] = command_args(row["command"]) if row.get("command") else []
        row.pop("command", None)
        snapshot[pid] = row
    return snapshot


@dataclass(eq=True)
class Cohort:
    # Roots precede their descendants: stopping a root prevents further children.
    records: list[dict]
    roots: list[int]


def inspect(data, *, base, dbname, port, lock_identity, identity_enabled,
            child_python, record_status, identity, snapshot=None):
    """Return a complete proven cohort, including an empty all-dead cohort.

    None means refuse. A missing root with a surviving descendant is deliberately
    refused: schema v2 never persisted that descendant's exact identity.
    """
    try:
        nonce = data.get("launchNonce")
        records = data.get("processes")
        required = required_roles(identity_enabled)
        if (data.get("schemaVersion") != 2 or not isinstance(nonce, str)
                or len(nonce) != 32 or any(c not in "0123456789abcdef" for c in nonce)
                or not isinstance(records, dict) or not required <= records.keys()
                or records.keys() - (required | {"identity", "amibroker"})
                or str(data.get("dbname", "")).strip().upper() != dbname.strip().upper()
                or type(data.get("relay_port")) is not int or data["relay_port"] != port
                or data.get("instance_lock") != lock_identity
                or normalized(data.get("working_directory", "")) != normalized(base)):
            return None
        if not all(valid_record(r) and data.get(role) == r["pid"]
                   for role, r in records.items()):
            return None
        # Schema v2 publishes the flat PID and identity together. A flat-only
        # entry is malformed even when that PID happens to be dead now.
        if any(role in data and role not in records
               for role in {"launcher", "amibroker", *SCRIPTS}):
            return None
        if len({r["pid"] for r in records.values()}) != len(records):
            return None
        statuses = {role: record_status(r) for role, r in records.items()}
        if statuses["launcher"] not in ("DEAD", "STALE"):
            return None
        if any(status not in ("MATCH", "DEAD", "STALE") for role, status in statuses.items()
               if role != "launcher"):
            return None
        if statuses.get("amibroker") == "STALE":
            return None
        # Enumeration is defensive only; it never supplies missing ownership.
        rows = process_snapshot() if snapshot is None else snapshot
        base_python = normalized(Path(sys._base_executable).with_name("python.exe"))
        expected_python = normalized(child_python)
        result = Cohort([], [])
        allowed = set()

        def verify(pid, record, role, executable, parent):
            row = rows.get(pid, {})
            args = row.get("argv", [])
            actual = identity(pid)
            return (actual is not None and actual == record
                    and row.get("parent") == parent
                    and normalized(row.get("executable") or "") == executable
                    # CIM timestamps have microsecond precision; native identity
                    # comparisons retain the full 100 ns creation timestamp.
                    and int(row.get("created", 0)) // 10 == record["creationTime100ns"] // 10
                    and len(args) == 3 and args[1] == "-u"
                    and absolute_path(args[0]) and absolute_path(args[2])
                    and normalized(args[0]) == executable
                    and normalized(args[2]) == normalized(base / SCRIPTS[role]))

        for role in SCRIPTS:
            if role not in records:
                continue
            root = records[role]
            root_pid = root["pid"]
            descendants = [r for r in rows.values() if r.get("parent") == root_pid]
            if statuses[role] in ("DEAD", "STALE"):
                if descendants:
                    return None
                continue
            if (normalized(root["executable"]) != expected_python
                    or root["creationTime100ns"] < records["launcher"]["creationTime100ns"]
                    or not verify(root_pid, root, role, expected_python, records["launcher"]["pid"])
                    or len(descendants) > 2):
                return None
            result.roots.append(root_pid)
            result.records.append(root)
            allowed.add(root_pid)
            seen_types = set()
            for row in descendants:
                child = identity(row["pid"])
                if (child is None or child["creationTime100ns"] < root["creationTime100ns"]
                        or any(r.get("parent") == row["pid"] for r in rows.values())):
                    return None
                if normalized(child["executable"]) == base_python:
                    kind = "python"
                    if not verify(row["pid"], child, role, base_python, root_pid):
                        return None
                else:
                    kind = "conhost"
                    trusted = trusted_conhost_path()
                    args = row.get("argv", [])
                    if (not valid_record(child) or child["pid"] != row["pid"]
                            or identity(row["pid"]) != child
                            or row.get("parent") != root_pid
                            or normalized(child["executable"]) != trusted
                            or normalized(row.get("executable") or "") != trusted
                            or int(row.get("created", 0)) // 10 != child["creationTime100ns"] // 10
                            or len(args) != 2
                            or conhost_argv_path(args[0]) != ntpath.normcase(trusted)
                            or not isinstance(args[1], str)
                            or re.fullmatch(r"0x[0-9a-fA-F]+", args[1]) is None):
                        return None
                if kind in seen_types:
                    return None
                seen_types.add(kind)
                result.records.append(child)
                allowed.add(row["pid"])
        # No second copy of these scripts, or unknown child of the dead launcher,
        # may be silently ignored. Broker is preserved, never a cleanup target.
        broker_pid = records.get("amibroker", {}).get("pid")
        for pid, row in rows.items():
            if pid in allowed:
                continue
            args = row.get("argv", [])
            if any(absolute_path(arg) and normalized(arg) in {normalized(base / s) for s in SCRIPTS.values()}
                   for arg in args[1:]):
                return None
            if row.get("parent") == records["launcher"]["pid"]:
                if (pid != broker_pid or not row.get("executable")
                        or Path(row["executable"]).name.lower() != "broker.exe"):
                    return None
        return result
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.SubprocessError):
        return None


class _PinnedProcess:
    """Private cleanup handle: query, terminate and wait on the same object."""
    def __init__(self, record):
        from ctypes import wintypes
        if os.name != "nt":
            raise OSError("Windows only")
        self.record = record
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "OpenProcess": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
            "TerminateProcess": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            "WaitForSingleObject": ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
            "QueryFullProcessImageNameW": ([wintypes.HANDLE, wintypes.DWORD,
                                            wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
            "GetProcessTimes": ([wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4,
                                wintypes.BOOL),
        }
        for name, (args, result) in signatures.items():
            method = getattr(self.api, name)
            method.argtypes, method.restype = args, result
        self.handle = self.api.OpenProcess(0x1000 | 0x0001 | 0x00100000, False, record["pid"])
        if not self.handle:
            raise OSError("cannot pin orphan identity")
        try:
            size = wintypes.DWORD(32768)
            image = ctypes.create_unicode_buffer(size.value)
            times = [wintypes.FILETIME() for _ in range(4)]
            if (not self.api.QueryFullProcessImageNameW(self.handle, 0, image, ctypes.byref(size))
                    or not self.api.GetProcessTimes(self.handle, *[ctypes.byref(t) for t in times])):
                raise OSError("cannot verify pinned orphan")
            created = (int(times[0].dwHighDateTime) << 32) | int(times[0].dwLowDateTime)
            if (created != record["creationTime100ns"]
                    or normalized(image.value) != normalized(record["executable"])):
                raise OSError("orphan identity changed")
        except Exception:
            self.close()
            raise

    def terminate(self):
        if self.api.WaitForSingleObject(self.handle, 0) == 0:
            return
        if not self.api.TerminateProcess(self.handle, 1):
            raise OSError("orphan termination failed")

    def wait(self, timeout):
        return self.api.WaitForSingleObject(self.handle, max(0, int(timeout * 1000))) == 0

    def close(self):
        self.api.CloseHandle(self.handle)


def cleanup_verified_orphaned_managed_cohort(plan, *, revalidate, paused, timeout=5.0):
    """Caller retains its instance lock. Failure leaves PID evidence untouched."""
    handles = []
    try:
        for record in plan.records:
            handles.append(_PinnedProcess(record))
        if paused() or revalidate() != plan:
            return False
        print("WSRTD_ORPHAN_RECOVERY=VERIFIED")
        print("WSRTD_ORPHAN_RECOVERY=CLEANUP_STARTED")
        deadline = time.monotonic() + timeout
        for handle in handles:
            if paused():
                return False
            handle.terminate()
        if not all(handle.wait(max(0, deadline - time.monotonic())) for handle in handles):
            return False
        # Re-scan after termination. Any new descendant or untracked service
        # makes completion unproven, even if all pinned handles are signaled.
        remaining = revalidate()
        if paused() or remaining is None or remaining.records:
            return False
        print("WSRTD_ORPHAN_RECOVERY=CLEANUP_COMPLETE")
        return True
    except (OSError, ValueError, subprocess.SubprocessError):
        return False
    finally:
        for handle in handles:
            handle.close()
