#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import binance_usdm_readonly_gateway as gateway


def base_account() -> dict:
    return {
        "availableBalance": "9000",
        "totalMarginBalance": "10000",
        "totalInitialMargin": "200",
        "totalWalletBalance": "9800",
        "positions": [
            {
                "symbol": "BTCUSDT",
                "positionSide": "LONG",
                "positionAmt": "1",
                "notional": "100",
            },
            {
                "symbol": "ETHUSDT",
                "positionSide": "SHORT",
                "positionAmt": "2",
                "notional": "40",
            },
            {
                "symbol": "SOLUSDT",
                "positionSide": "BOTH",
                "positionAmt": "-3",
                "notional": "-20",
            },
            {
                "symbol": "BNBUSDT",
                "positionSide": "BOTH",
                "positionAmt": "0",
                "notional": "0",
            },
        ],
    }


def main() -> int:
    snapshot = gateway.account_to_risk_snapshot(
        base_account(),
        max_gross_notional=100_000.0,
        max_open_positions=10,
        source="DIRECTIONAL_FIXTURE",
    )
    assert snapshot["reconciled"] is True
    assert snapshot["openPositions"] == 3
    assert abs(snapshot["grossNotional"] - 160.0) < 1e-12
    assert abs(snapshot["netDirectionalNotional"] - 40.0) < 1e-12
    assert abs(snapshot["marginBalance"] - 10_000.0) < 1e-12
    assert abs(snapshot["initialMargin"] - 200.0) < 1e-12

    invalid = base_account()
    invalid["positions"][0]["positionSide"] = "INVALID"
    failed = False
    try:
        gateway.account_to_risk_snapshot(
            invalid,
            max_gross_notional=100_000.0,
            max_open_positions=10,
            source="DIRECTIONAL_FIXTURE",
        )
    except gateway.GatewayError:
        failed = True
    assert failed

    print("DIRECTIONAL_RISK_SNAPSHOT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
