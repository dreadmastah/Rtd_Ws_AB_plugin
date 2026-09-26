#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def load_json(path: Path) -> dict:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise AssertionError(f"{path} root is not an object")
    return obj


def verify_ready(view_path: Path, symbol_path: Path, html_path: Path) -> None:
    if not (view_path.exists() and symbol_path.exists() and html_path.exists()):
        raise AssertionError("operator-view artifacts missing")

    view = load_json(view_path)
    account = view["accountRiskObservation"]
    symbol_view = view["symbolRisk"]
    rows = {row["symbol"]: row for row in symbol_view["symbols"]}
    raw_symbol = load_json(symbol_path)
    html = html_path.read_text(encoding="utf-8")

    assert view["messageType"] == "AccountRiskView.v1"
    assert view["orderRoutingEnabled"] is False
    assert view["sourceFresh"] is True

    assert account["ready"] is True
    assert account["riskState"] == "NORMAL"
    assert abs(account["riskCapital"] - 10250.0) < 1e-9
    assert abs(account["availableBalance"] - 9150.0) < 1e-9
    assert abs(account["grossNotional"] - 1000.0) < 1e-9
    assert abs(account["projectedGrossNotional"] - 1000.0) < 1e-9
    assert abs(account["marginBalance"] - 10250.0) < 1e-9
    assert abs(account["initialMargin"] - 100.0) < 1e-9
    assert abs(
        account["projectedEffectiveLeverage"] - (1000.0 / 10250.0)
    ) < 1e-9
    assert abs(
        account["projectedMarginUtilization"] - (100.0 / 10250.0)
    ) < 1e-9
    assert abs(account["projectedNetDirectionalNotional"] - 1000.0) < 1e-9

    assert symbol_view["ready"] is True
    assert len(rows) == 12
    assert rows["BTCUSDT"]["positionMode"] == "LONG"
    assert abs(rows["BTCUSDT"]["currentNotional"] - 1000.0) < 1e-9
    assert rows["ETHUSDT"]["positionMode"] == "FLAT"
    assert abs(rows["ETHUSDT"]["currentNotional"]) < 1e-9

    assert raw_symbol["orderRoutingEnabled"] is False
    assert len(raw_symbol["symbols"]) == 12

    assert "READ ONLY" in html
    assert "No order controls exist in this view." in html
    assert "Live account and projected headroom" in html
    assert "Per-symbol projected exposure" in html


def verify_reservation(view_path: Path) -> None:
    view = load_json(view_path)
    rows = {row["symbol"]: row for row in view["symbolRisk"]["symbols"]}
    btc = rows["BTCUSDT"]

    assert view["orderRoutingEnabled"] is False
    assert btc["positionReady"] is True
    assert btc["activeReservations"] == 1, btc
    assert btc["reservedGrossNotional"] > 0, btc
    assert btc["projectedNotional"] > btc["currentNotional"], btc


def wait_until(
    check,
    *,
    timeout_seconds: float,
    poll_seconds: float,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            check()
            return
        except Exception as exc:
            last_error = exc
            time.sleep(poll_seconds)

    if last_error is None:
        raise AssertionError("verification timed out")
    raise AssertionError(
        f"verification timed out; last error: {last_error!r}"
    ) from last_error


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("ready", "reservation"), required=True)
    ap.add_argument("--view-json", required=True)
    ap.add_argument("--symbol-json")
    ap.add_argument("--html")
    ap.add_argument("--timeout-seconds", type=float, default=15.0)
    ap.add_argument("--poll-seconds", type=float, default=0.25)
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    if args.timeout_seconds <= 0 or args.poll_seconds <= 0:
        raise SystemExit("timeout/poll must be positive")

    view_path = Path(args.view_json)
    if args.mode == "ready":
        if not args.symbol_json or not args.html:
            raise SystemExit("ready mode requires --symbol-json and --html")
        symbol_path = Path(args.symbol_json)
        html_path = Path(args.html)
        wait_until(
            lambda: verify_ready(view_path, symbol_path, html_path),
            timeout_seconds=args.timeout_seconds,
            poll_seconds=args.poll_seconds,
        )
        print("ACCOUNT_RISK_VIEW_SUPERVISED=PASS")
    else:
        wait_until(
            lambda: verify_reservation(view_path),
            timeout_seconds=args.timeout_seconds,
            poll_seconds=args.poll_seconds,
        )
        print("SYMBOL_RISK_RESERVATION_PROJECTION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
