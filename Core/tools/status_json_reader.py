"""Read an atomically published status snapshot without retrying its semantics."""
import json
import errno
import os
from pathlib import Path
import time


def _read_bytes(path):
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
