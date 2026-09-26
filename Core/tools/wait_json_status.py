#!/usr/bin/env python3
"""Bounded poll for atomically-published JSON status fields."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


def parse_scalar(text: str) -> Any:
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path)
    ap.add_argument("--timeout-seconds", type=float, default=5.0)
    ap.add_argument("--eq", action="append", default=[])
    ap.add_argument("--float-eq", action="append", default=[])
    args = ap.parse_args()

    if args.timeout_seconds <= 0:
        raise SystemExit("timeout must be positive")

    exact: list[tuple[str, Any]] = []
    for item in args.eq:
        key, sep, value = item.partition("=")
        if not sep or not key:
            raise SystemExit(f"invalid --eq expectation: {item}")
        exact.append((key, parse_scalar(value)))

    numeric: list[tuple[str, float, float]] = []
    for item in args.float_eq:
        key, sep, rest = item.partition("=")
        value_text, tol_sep, tol_text = rest.partition(":")
        if not sep or not tol_sep or not key:
            raise SystemExit(f"invalid --float-eq expectation: {item}")
        numeric.append((key, float(value_text), float(tol_text)))

    deadline = time.monotonic() + args.timeout_seconds
    last: Any = None
    while time.monotonic() < deadline:
        try:
            last = json.loads(args.path.read_text(encoding="utf-8"))
            if all(last.get(key) == value for key, value in exact) and all(
                abs(float(last.get(key)) - value) <= tolerance
                for key, value, tolerance in numeric
            ):
                print("WAIT_JSON_STATUS=PASS")
                return 0
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        time.sleep(0.1)

    print(f"WAIT_JSON_STATUS=TIMEOUT LAST={last!r}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
