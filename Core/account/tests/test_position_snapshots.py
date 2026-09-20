#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parent
MODULE = ROOT / "account" / "binance_usdm_readonly_gateway.py"
FIXTURE = ROOT / "account" / "tests" / "fixtures" / "binance_usdm_account_v3.json"
SYMBOLS_FILE = REPO / "CleanRoomR2" / "stack" / "bootstrap_symbols.tls"

spec = importlib.util.spec_from_file_location("account_gateway", MODULE)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load account gateway")
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)


def main() -> int:
    symbols = gateway.load_symbols(SYMBOLS_FILE)
    assert len(symbols) == 12

    account = gateway.load_fixture(FIXTURE)
    snapshots = gateway.account_to_position_snapshots(
        account,
        symbols=symbols,
        source="TEST",
    )
    assert set(snapshots) == set(symbols)

    btc = snapshots["BTCUSDT"]
    assert btc["reconciled"] is True
    assert btc["mode"] == "LONG"
    assert abs(btc["quantity"] - 0.01) < 1e-12
    assert abs(btc["notional"] - 1000.0) < 1e-12

    eth = snapshots["ETHUSDT"]
    assert eth["mode"] == "FLAT"
    assert eth["quantity"] == 0.0
    assert eth["notional"] == 0.0

    short_account = copy.deepcopy(account)
    btc_raw = next(x for x in short_account["positions"] if x["symbol"] == "BTCUSDT")
    btc_raw["positionAmt"] = "-0.020"
    btc_raw["notional"] = "-2000"
    short = gateway.account_to_position_snapshots(
        short_account,
        symbols=symbols,
        source="TEST",
    )
    assert short["BTCUSDT"]["mode"] == "SHORT"
    assert abs(short["BTCUSDT"]["quantity"] - 0.02) < 1e-12

    hedged_account = copy.deepcopy(account)
    hedged_account["positions"] = [
        x for x in hedged_account["positions"] if x["symbol"] != "BTCUSDT"
    ] + [
        {
            "symbol": "BTCUSDT",
            "positionSide": "LONG",
            "positionAmt": "0.010",
            "notional": "1000",
        },
        {
            "symbol": "BTCUSDT",
            "positionSide": "SHORT",
            "positionAmt": "-0.005",
            "notional": "-500",
        },
    ]
    hedged = gateway.account_to_position_snapshots(
        hedged_account,
        symbols=symbols,
        source="TEST",
    )
    assert hedged["BTCUSDT"]["mode"] == "HEDGED"
    assert abs(hedged["BTCUSDT"]["quantity"] - 0.015) < 1e-12
    assert abs(hedged["BTCUSDT"]["notional"] - 1500.0) < 1e-12

    missing_account = copy.deepcopy(account)
    missing_account["positions"] = [
        x for x in missing_account["positions"] if x["symbol"] != "DOTUSDT"
    ]
    try:
        gateway.account_to_position_snapshots(
            missing_account,
            symbols=symbols,
            source="TEST",
        )
        raise AssertionError("missing selected position symbol was not rejected")
    except gateway.GatewayError as exc:
        assert "DOTUSDT" in str(exc)

    failed = gateway.fail_closed_position_snapshots(
        symbols=symbols,
        source="TEST_FAILURE",
        reason="synthetic failure",
    )
    assert len(failed) == 12
    assert all(not x["reconciled"] for x in failed.values())
    assert all(x["mode"] == "UNKNOWN" for x in failed.values())

    print("POSITION_SNAPSHOT_RECONCILIATION_TEST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
