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
DEFAULT_POSITIONS_OUTPUT = Path("Core/runtime/position_status")
DEFAULT_SYMBOLS_FILE = Path("CleanRoomR2/stack/bootstrap_symbols.tls")


class GatewayError(RuntimeError):
    pass


def load_symbols(path: Path) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        symbol = line.strip().upper()
        if not symbol or symbol.startswith("#") or symbol in seen:
            continue
        seen.add(symbol)
        out.append(symbol)
    if not out:
        raise GatewayError("position symbol list is empty")
    return out


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
        # Do not echo private USER_DATA response bodies into logs.
        raise GatewayError(
            f"Binance USER_DATA HTTP {exc.code}"
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
    margin_balance = as_float(account, "totalMarginBalance")
    initial_margin = as_float(account, "totalInitialMargin")

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
    net_directional_notional = 0.0
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
        absolute_notional = abs(as_position_float(raw, "notional"))
        gross_notional += absolute_notional
        position_side = str(raw.get("positionSide", "BOTH")).upper()
        if position_side == "LONG":
            direction = 1.0
        elif position_side == "SHORT":
            direction = -1.0
        elif position_side == "BOTH":
            direction = 1.0 if position_amt > 0.0 else -1.0
        else:
            raise GatewayError(
                f"unsupported positionSide={position_side} for directional exposure"
            )
        net_directional_notional += direction * absolute_notional

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
        "marginBalance": max(0.0, margin_balance),
        "initialMargin": max(0.0, initial_margin),
        "grossNotional": max(0.0, gross_notional),
        "netDirectionalNotional": float(net_directional_notional),
        "maxGrossNotional": float(max_gross_notional),
        "openPositions": int(open_positions),
        "maxOpenPositions": int(max_open_positions),
        "detail": "; ".join(detail_parts),
    }


def account_to_position_snapshots(
    account: dict[str, Any],
    *,
    symbols: list[str],
    source: str,
) -> dict[str, dict[str, Any]]:
    positions = account.get("positions", [])
    if not isinstance(positions, list):
        raise GatewayError("account positions is not a list")

    grouped: dict[str, list[dict[str, Any]]] = {}
    for raw in positions:
        if not isinstance(raw, dict):
            raise GatewayError("account position entry is not an object")
        symbol = str(raw.get("symbol", "")).upper()
        if symbol:
            grouped.setdefault(symbol, []).append(raw)

    missing = [symbol for symbol in symbols if symbol not in grouped]
    if missing:
        raise GatewayError(
            "account snapshot missing selected position symbols: " + ",".join(missing)
        )

    now_ms = int(time.time() * 1000)
    snapshots: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        active: list[tuple[str, float, float]] = []
        for raw in grouped[symbol]:
            amount = as_position_float(raw, "positionAmt")
            if abs(amount) <= 0.0:
                continue
            if "notional" not in raw:
                raise GatewayError(
                    f"{symbol}: non-zero position missing notional"
                )
            notional = abs(as_position_float(raw, "notional"))
            position_side = str(raw.get("positionSide", "BOTH")).upper()
            if position_side == "LONG":
                mode = "LONG"
            elif position_side == "SHORT":
                mode = "SHORT"
            elif position_side == "BOTH":
                mode = "LONG" if amount > 0 else "SHORT"
            else:
                raise GatewayError(
                    f"{symbol}: unsupported positionSide={position_side}"
                )
            active.append((mode, abs(amount), notional))

        if not active:
            mode = "FLAT"
            quantity = 0.0
            notional = 0.0
            detail = "private account position reconciled flat"
        else:
            modes = {item[0] for item in active}
            quantity = sum(item[1] for item in active)
            notional = sum(item[2] for item in active)
            if len(modes) == 1:
                mode = next(iter(modes))
                detail = f"private account position reconciled {mode.lower()}"
            else:
                mode = "HEDGED"
                detail = "private account position reconciled hedged"

        snapshots[symbol] = {
            "schemaVersion": 1,
            "messageType": "PositionSnapshot.v1",
            "generatedUnixMs": now_ms,
            "source": source,
            "reconciled": True,
            "symbol": symbol,
            "mode": mode,
            "quantity": quantity,
            "notional": notional,
            "detail": detail,
        }
    return snapshots


def fail_closed_position_snapshots(
    *,
    symbols: list[str],
    source: str,
    reason: str,
) -> dict[str, dict[str, Any]]:
    now_ms = int(time.time() * 1000)
    return {
        symbol: {
            "schemaVersion": 1,
            "messageType": "PositionSnapshot.v1",
            "generatedUnixMs": now_ms,
            "source": source,
            "reconciled": False,
            "symbol": symbol,
            "mode": "UNKNOWN",
            "quantity": 0.0,
            "notional": 0.0,
            "detail": reason[:512],
        }
        for symbol in symbols
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
        "marginBalance": 0.0,
        "initialMargin": 0.0,
        "grossNotional": 0.0,
        "netDirectionalNotional": 0.0,
        "maxGrossNotional": max(0.0, float(max_gross_notional)),
        "openPositions": 0,
        "maxOpenPositions": max(0, int(max_open_positions)),
        "detail": reason[:512],
    }


def write_position_snapshots(
    output_dir: Path,
    snapshots: dict[str, dict[str, Any]],
) -> None:
    for symbol, snapshot in snapshots.items():
        write_atomic(output_dir / f"{symbol}.json", snapshot)


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
    ap.add_argument(
        "--positions-output-dir",
        type=Path,
        default=DEFAULT_POSITIONS_OUTPUT,
    )
    ap.add_argument(
        "--symbols-file",
        type=Path,
        default=DEFAULT_SYMBOLS_FILE,
    )
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

    symbols = load_symbols(args.symbols_file)
    fixture_mode = args.fixture is not None
    if not fixture_mode and not env_bool("ASTU_BINANCE_PRIVATE_READONLY_ENABLED", False):
        snapshot = fail_closed_snapshot(
            max_gross_notional=args.max_gross_notional,
            max_open_positions=args.max_open_positions,
            source="BINANCE_USDM_PRIVATE_DISABLED",
            reason="read-only private gateway disabled",
        )
        write_atomic(args.output, snapshot)
        write_position_snapshots(
            args.positions_output_dir,
            fail_closed_position_snapshots(
                symbols=symbols,
                source="BINANCE_USDM_PRIVATE_DISABLED",
                reason="read-only private gateway disabled",
            ),
        )
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
        write_position_snapshots(
            args.positions_output_dir,
            fail_closed_position_snapshots(
                symbols=symbols,
                source="BINANCE_USDM_PRIVATE_MISSING_CREDENTIALS",
                reason="read-only private credentials unavailable",
            ),
        )
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
            position_snapshots = account_to_position_snapshots(
                account,
                symbols=symbols,
                source=source,
            )
            write_atomic(args.output, snapshot)
            write_position_snapshots(
                args.positions_output_dir,
                position_snapshots,
            )
            print(
                "BINANCE_PRIVATE_READONLY=RECONCILED "
                f"positions={snapshot['openPositions']} "
                f"grossNotional={snapshot['grossNotional']} "
                f"positionSnapshots={len(position_snapshots)}"
            )
        except Exception as exc:
            snapshot = fail_closed_snapshot(
                max_gross_notional=args.max_gross_notional,
                max_open_positions=args.max_open_positions,
                source=source,
                reason=f"reconciliation failed: {type(exc).__name__}: {exc}",
            )
            write_atomic(args.output, snapshot)
            write_position_snapshots(
                args.positions_output_dir,
                fail_closed_position_snapshots(
                    symbols=symbols,
                    source=source,
                    reason=f"reconciliation failed: {type(exc).__name__}: {exc}",
                ),
            )
            print(f"BINANCE_PRIVATE_READONLY=FAIL_CLOSED error={type(exc).__name__}: {exc}")

        if args.once:
            return 0 if snapshot["reconciled"] else 5
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
