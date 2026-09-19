#!/usr/bin/env python3
"""Binance USD-M read-only account snapshot -> AccountRiskSnapshot.v1.

This gateway intentionally implements USER_DATA reads only. It has no order,
cancel, leverage, transfer, or margin-mutation methods.

Live mode is disabled unless ASTU_BINANCE_PRIVATE_READONLY_ENABLED=1.
Credentials are read only from environment variables and are never written to
output/logs.

Current compatibility endpoint:
  GET /fapi/v3/account

Signed REST requests use HMAC-SHA256 over the query string, X-MBX-APIKEY,
timestamp, and recvWindow.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://fapi.binance.com"
DEFAULT_OUTPUT = Path("Core/runtime/account_risk_status.v1.json")


class GatewayError(RuntimeError):
    pass


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def as_float(obj: dict[str, Any], key: str) -> float:
    if key not in obj:
        raise GatewayError(f"missing required account field: {key}")
    try:
        return float(obj[key])
    except (TypeError, ValueError) as exc:
        raise GatewayError(f"invalid numeric account field: {key}") from exc


def as_position_float(obj: dict[str, Any], key: str) -> float:
    try:
        return float(obj.get(key, 0) or 0)
    except (TypeError, ValueError) as exc:
        raise GatewayError(f"invalid position field: {key}") from exc


def signed_get_account(
    *,
    base_url: str,
    api_key: str,
    api_secret: str,
    recv_window_ms: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    timestamp = int(time.time() * 1000)
    params = [
        ("timestamp", str(timestamp)),
        ("recvWindow", str(recv_window_ms)),
    ]
    query = urllib.parse.urlencode(params)
    signature = hmac.new(
        api_secret.encode("utf-8"),
        query.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    url = (
        base_url.rstrip("/")
        + "/fapi/v3/account?"
        + query
        + "&signature="
        + urllib.parse.quote(signature)
    )
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "X-MBX-APIKEY": api_key,
            "User-Agent": "ASTU-ReadOnly-Reconciler/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise GatewayError(
            f"Binance USER_DATA HTTP {exc.code}: {body}"
        ) from exc
    except urllib.error.URLError as exc:
        raise GatewayError(f"Binance USER_DATA request failed: {exc}") from exc

    try:
        obj = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise GatewayError("Binance USER_DATA returned invalid JSON") from exc
    if not isinstance(obj, dict):
        raise GatewayError("Binance account response is not an object")
    return obj


def load_fixture(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise GatewayError("fixture must contain an account object")
    return obj


def account_to_risk_snapshot(
    account: dict[str, Any],
    *,
    max_gross_notional: float,
    max_open_positions: int,
    source: str,
) -> dict[str, Any]:
    available_balance = as_float(account, "availableBalance")

    if "totalMarginBalance" in account:
        risk_capital = as_float(account, "totalMarginBalance")
    elif "totalWalletBalance" in account:
        risk_capital = as_float(account, "totalWalletBalance")
    else:
        raise GatewayError(
            "account response has neither totalMarginBalance nor totalWalletBalance"
        )

    positions = account.get("positions", [])
    if not isinstance(positions, list):
        raise GatewayError("account positions is not a list")

    gross_notional = 0.0
    open_positions = 0
    for raw in positions:
        if not isinstance(raw, dict):
            raise GatewayError("account position entry is not an object")
        position_amt = as_position_float(raw, "positionAmt")
        if abs(position_amt) <= 0.0:
            continue
        open_positions += 1
        if "notional" not in raw:
            raise GatewayError(
                "non-zero account position missing notional; cannot reconcile gross exposure"
            )
        gross_notional += abs(as_position_float(raw, "notional"))

    if max_gross_notional <= 0.0:
        raise GatewayError("max_gross_notional must be positive")
    if max_open_positions <= 0:
        raise GatewayError("max_open_positions must be positive")

    risk_state = "NORMAL"
    detail_parts = ["private account snapshot reconciled"]
    if open_positions >= max_open_positions:
        risk_state = "BLOCK_NEW_ENTRIES"
        detail_parts.append("max open positions reached")
    if gross_notional >= max_gross_notional:
        risk_state = "BLOCK_NEW_ENTRIES"
        detail_parts.append("max gross notional reached")

    return {
        "schemaVersion": 1,
        "messageType": "AccountRiskSnapshot.v1",
        "generatedUnixMs": int(time.time() * 1000),
        "source": source,
        "reconciled": True,
        "riskState": risk_state,
        "riskCapital": max(0.0, risk_capital),
        "availableBalance": max(0.0, available_balance),
        "grossNotional": max(0.0, gross_notional),
        "maxGrossNotional": float(max_gross_notional),
        "openPositions": int(open_positions),
        "maxOpenPositions": int(max_open_positions),
        "detail": "; ".join(detail_parts),
    }


def fail_closed_snapshot(
    *,
    max_gross_notional: float,
    max_open_positions: int,
    source: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "messageType": "AccountRiskSnapshot.v1",
        "generatedUnixMs": int(time.time() * 1000),
        "source": source,
        "reconciled": False,
        "riskState": "EMERGENCY",
        "riskCapital": 0.0,
        "availableBalance": 0.0,
        "grossNotional": 0.0,
        "maxGrossNotional": max(0.0, float(max_gross_notional)),
        "openPositions": 0,
        "maxOpenPositions": max(0, int(max_open_positions)),
        "detail": reason[:512],
    }


def write_atomic(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(obj, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--fixture", type=Path)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--poll-seconds", type=float, default=5.0)
    ap.add_argument("--max-gross-notional", type=float, default=100_000.0)
    ap.add_argument("--max-open-positions", type=int, default=10)
    ap.add_argument("--recv-window-ms", type=int, default=5_000)
    ap.add_argument("--timeout-seconds", type=float, default=10.0)
    ap.add_argument("--base-url", default=os.getenv("BINANCE_USDM_BASE_URL", DEFAULT_BASE_URL))
    args = ap.parse_args()

    if args.recv_window_ms <= 0 or args.recv_window_ms > 60_000:
        raise SystemExit("recvWindow must be in 1..60000 ms")
    if args.poll_seconds < 1.0:
        raise SystemExit("poll-seconds must be >= 1")

    fixture_mode = args.fixture is not None
    if not fixture_mode and not env_bool("ASTU_BINANCE_PRIVATE_READONLY_ENABLED", False):
        snapshot = fail_closed_snapshot(
            max_gross_notional=args.max_gross_notional,
            max_open_positions=args.max_open_positions,
            source="BINANCE_USDM_PRIVATE_DISABLED",
            reason="read-only private gateway disabled",
        )
        write_atomic(args.output, snapshot)
        print("BINANCE_PRIVATE_READONLY=DISABLED")
        print(f"OUTPUT={args.output}")
        return 3

    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")
    if not fixture_mode and (not api_key or not api_secret):
        snapshot = fail_closed_snapshot(
            max_gross_notional=args.max_gross_notional,
            max_open_positions=args.max_open_positions,
            source="BINANCE_USDM_PRIVATE_MISSING_CREDENTIALS",
            reason="read-only private credentials unavailable",
        )
        write_atomic(args.output, snapshot)
        print("BINANCE_PRIVATE_READONLY=MISSING_CREDENTIALS")
        print(f"OUTPUT={args.output}")
        return 4

    while True:
        source = "BINANCE_USDM_ACCOUNT_V3_FIXTURE" if fixture_mode else "BINANCE_USDM_ACCOUNT_V3"
        try:
            account = (
                load_fixture(args.fixture)
                if fixture_mode
                else signed_get_account(
                    base_url=args.base_url,
                    api_key=api_key,
                    api_secret=api_secret,
                    recv_window_ms=args.recv_window_ms,
                    timeout_seconds=args.timeout_seconds,
                )
            )
            snapshot = account_to_risk_snapshot(
                account,
                max_gross_notional=args.max_gross_notional,
                max_open_positions=args.max_open_positions,
                source=source,
            )
            write_atomic(args.output, snapshot)
            print(
                "BINANCE_PRIVATE_READONLY=RECONCILED "
                f"positions={snapshot['openPositions']} "
                f"grossNotional={snapshot['grossNotional']}"
            )
        except Exception as exc:
            snapshot = fail_closed_snapshot(
                max_gross_notional=args.max_gross_notional,
                max_open_positions=args.max_open_positions,
                source=source,
                reason=f"reconciliation failed: {type(exc).__name__}: {exc}",
            )
            write_atomic(args.output, snapshot)
            print(f"BINANCE_PRIVATE_READONLY=FAIL_CLOSED error={type(exc).__name__}: {exc}")

        if args.once or fixture_mode:
            return 0 if snapshot["reconciled"] else 5
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
