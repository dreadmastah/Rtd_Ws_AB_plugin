"""Read an atomically published status snapshot without retrying its semantics."""
import json
import errno
import os
import sys
from pathlib import Path
import time


if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    _kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                   wintypes.DWORD, ctypes.c_void_p,
                                   wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    _kernel.CreateFileW.restype = wintypes.HANDLE
    _kernel.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    _kernel.ReadFile.restype = wintypes.BOOL
    _kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel.CloseHandle.restype = wintypes.BOOL


def _read_windows_bytes(path):
    # GENERIC_READ, SHARE_READ | SHARE_WRITE | SHARE_DELETE, OPEN_EXISTING.
    # Replacement may detach this handle from the pathname; keep reading the
    # same complete snapshot, never reopen the path midway through the read.
    handle = _kernel.CreateFileW(os.fsdecode(path), 0x80000000, 7, None, 3, 0x80, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        chunks = []
        buffer = ctypes.create_string_buffer(64 * 1024)
        count = wintypes.DWORD()
        while True:
            if not _kernel.ReadFile(handle, buffer, len(buffer), ctypes.byref(count), None):
                raise ctypes.WinError(ctypes.get_last_error())
            if count.value == 0:
                break  # EOF, including an empty file; JSON validation is below.
            chunks.append(buffer.raw[:count.value])
        return b"".join(chunks)
    finally:
        # Do not mask the original read error (including its Windows error code).
        failed = sys.exc_info()[0] is not None
        if not _kernel.CloseHandle(handle) and not failed:
            raise ctypes.WinError(ctypes.get_last_error())


def _read_bytes(path):
    if os.name == "nt":
        return _read_windows_bytes(path)
    return Path(path).read_bytes()


def read_json(path):
    delays = (0.01, 0.02, 0.04, 0.08)
    for attempt in range(len(delays) + 1):
        try:
            payload = _read_bytes(path)
            break
        except PermissionError as exc:
            # Access denied can represent a pending Windows rename/delete.
            # Genuine ACL denial also exhausts promptly and retains its cause.
            winerror = getattr(exc, "winerror", None)
            sharing_error = winerror in (5, 32, 33) or (
                winerror is None and exc.errno == errno.EACCES)
            if os.name != "nt" or not sharing_error:
                raise
            if attempt == len(delays):
                raise PermissionError(f"status read exhausted {attempt + 1} attempts: {path}") from exc
            time.sleep(delays[attempt])
    # Close the handle before parsing. Syntax/schema/assertion failures are not
    # publication races and must reach the caller immediately.
    return json.loads(payload.decode("utf-8"))
