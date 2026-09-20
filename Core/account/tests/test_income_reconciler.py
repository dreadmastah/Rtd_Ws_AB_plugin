#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "binance_usdm_income_reconciler.py"
SPEC = importlib.util.spec_from_file_location("income_reconciler", MODULE_PATH)
assert SPEC and SPEC.loader
income = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(income)


def row(
    income_type: str,
    value: float,
    event_time: int,
    tran_id: int,
    trade_id: str = "",
) -> dict[str, object]:
    return {
        "symbol": "BTCUSDT",
        "incomeType": income_type,
        "income": str(value),
        "asset": "USDT",
        "info": income_type,
        "time": event_time,
        "tranId": tran_id,
        "tradeId": trade_id,
    }


def main() -> int:
    now_ms = 1_800_000_000_000
    day_start = income.utc_day_start_ms(now_ms)
    week_start = income.utc_week_start_ms(now_ms)

    rows = [
        row("REALIZED_PNL", -30.0, week_start + 1_000, 1, "1"),
        row("FUNDING_FEE", 2.0, week_start + 2_000, 2),
        row("COMMISSION", -1.0, week_start + 3_000, 3),
        row("TRANSFER", -500.0, week_start + 4_000, 4),
        row("REALIZED_PNL", -25.0, day_start + 1_000, 5, "5"),
        row("REALIZED_PNL", 5.0, day_start + 2_000, 6, "6"),
        row("FUNDING_FEE", -2.0, day_start + 3_000, 7),
        row("COMMISSION", -1.5, day_start + 4_000, 8),
        # Exact duplicate must not double count.
        row("REALIZED_PNL", -25.0, day_start + 1_000, 5, "5"),
        # Outside the current week and future rows are ignored.
        row("REALIZED_PNL", -999.0, week_start - 1, 9, "9"),
        row("REALIZED_PNL", -999.0, now_ms + 1, 10, "10"),
    ]

    snapshot, state = income.aggregate_income(
        rows,
        now_ms=now_ms,
        source="TEST_FIXTURE",
    )

    assert snapshot["reconciled"] is True
    assert snapshot["utcDayStartUnixMs"] == day_start
    assert snapshot["utcWeekStartUnixMs"] == week_start
    assert abs(snapshot["dailyRealizedTradePnl"] - (-20.0)) < 1e-12
    assert abs(snapshot["weeklyRealizedTradePnl"] - (-50.0)) < 1e-12
    assert abs(snapshot["dailyRealizedTradeLoss"] - 20.0) < 1e-12
    assert abs(snapshot["weeklyRealizedTradeLoss"] - 50.0) < 1e-12
    assert abs(snapshot["dailyFundingFee"] - (-2.0)) < 1e-12
    assert abs(snapshot["weeklyFundingFee"] - 0.0) < 1e-12
    assert abs(snapshot["dailyCommission"] - (-1.5)) < 1e-12
    assert abs(snapshot["weeklyCommission"] - (-2.5)) < 1e-12
    assert abs(snapshot["dailyNetTradingIncome"] - (-23.5)) < 1e-12
    assert abs(snapshot["weeklyNetTradingIncome"] - (-52.5)) < 1e-12
    assert snapshot["ignoredIncomeRecords"] == 1
    assert snapshot["recordsInCurrentWeek"] == 8

    assert state["messageType"] == "RealizedPnlAccumulatorState.v1"
    assert state["dailyRealizedTradePnl"] == snapshot["dailyRealizedTradePnl"]
    assert state["weeklyRealizedTradePnl"] == snapshot["weeklyRealizedTradePnl"]
    assert state["ignoredIncomeRecords"] == 1

    with tempfile.TemporaryDirectory() as tmp:
        status_path = Path(tmp) / "status.json"
        state_path = Path(tmp) / "state.json"
        income.write_atomic(status_path, snapshot)
        income.write_atomic(state_path, state)
        persisted_status = json.loads(status_path.read_text(encoding="utf-8"))
        persisted_state = json.loads(state_path.read_text(encoding="utf-8"))
        assert persisted_status == snapshot
        assert persisted_state == state

    invalid = [row("REALIZED_PNL", -1.0, day_start + 1, 11)]
    invalid[0]["income"] = "nan"
    failed = False
    try:
        income.aggregate_income(
            invalid,
            now_ms=now_ms,
            source="TEST_FIXTURE",
        )
    except income.IncomeReconcilerError:
        failed = True
    assert failed

    fail_closed = income.fail_closed_snapshot(
        source="TEST_FAIL",
        reason="fixture failure",
    )
    assert fail_closed["reconciled"] is False
    assert fail_closed["dailyRealizedTradeLoss"] == 0.0

    print("REALIZED_PNL_INCOME_RECONCILIATION_TEST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
