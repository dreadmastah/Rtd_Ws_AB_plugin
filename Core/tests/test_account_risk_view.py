#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
MODULE = HERE.parents[1] / "operator" / "account_risk_view.py"
spec = importlib.util.spec_from_file_location("account_risk_view", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def base_status() -> dict:
    return {
        "schemaVersion": 1,
        "messageType": "ExecutionStatus.v1",
        "generatedUnixMs": 1_000_000,
        "lifecycleState": "READY",
        "riskProvider": "FIXTURE",
        "realizedPnlProvider": "FIXTURE",
        "orderRoutingEnabled": False,
        "accountLossMetricsReady": True,
        "accountLossUtcDayIndex": 20000,
        "accountLossUtcWeekStartDayIndex": 19996,
        "dailyStartRiskCapital": 1000.0,
        "weeklyStartRiskCapital": 1200.0,
        "dailyStartMarginBalance": 1100.0,
        "weeklyStartMarginBalance": 1300.0,
        "highWaterMarginBalance": 1500.0,
        "dailyRiskCapitalLoss": 25.0,
        "weeklyRiskCapitalLoss": 75.0,
        "dailyTotalPnlLoss": 40.0,
        "weeklyTotalPnlLoss": 90.0,
        "accountDrawdown": 100.0,
        "maxDailyRiskCapitalLoss": 100.0,
        "maxWeeklyRiskCapitalLoss": 300.0,
        "maxDailyTotalPnlLoss": 150.0,
        "maxWeeklyTotalPnlLoss": 400.0,
        "maxAccountDrawdown": 500.0,
        "realizedPnlReady": True,
        "realizedPnlSettlementAsset": "USDT",
        "dailyRealizedTradePnl": -20.0,
        "weeklyRealizedTradePnl": -60.0,
        "dailyRealizedTradeLoss": 20.0,
        "weeklyRealizedTradeLoss": 60.0,
        "dailyFundingFee": 1.0,
        "weeklyFundingFee": 2.0,
        "dailyCommission": -0.5,
        "weeklyCommission": -1.5,
        "dailyNetTradingIncome": -19.5,
        "weeklyNetTradingIncome": -59.5,
        "realizedPnlRecordsInCurrentWeek": 5,
        "realizedPnlIgnoredIncomeRecords": 1,
        "maxDailyRealizedTradeLoss": 50.0,
        "maxWeeklyRealizedTradeLoss": 120.0,
        "activeExposureReservations": 2,
        "reservedGrossNotional": 300.0,
        "reservedAvailableBalance": 30.0,
        "reservedNetDirectionalNotional": 100.0,
        "reservedPositionSlots": 1,
        "maxPendingEntryScaleInReservations": 4,
        "maxSymbolNotional": 2500.0,
        "minimumAvailableBalanceReserve": 100.0,
        "simulationMarginReservationRate": 0.1,
        "maxEffectiveLeverage": 3.0,
        "maxMarginUtilization": 0.6,
        "maxNetDirectionalNotional": 5000.0,
        "accountRiskObservationReady": True,
        "accountRiskObservedUnixMs": 999_900,
        "accountRiskState": "NORMAL",
        "currentRiskCapital": 1000.0,
        "currentAvailableBalance": 700.0,
        "projectedAvailableBalance": 670.0,
        "currentGrossNotional": 1000.0,
        "projectedGrossNotional": 1300.0,
        "currentMaxGrossNotional": 5000.0,
        "currentOpenPositions": 2,
        "projectedOpenPositions": 3,
        "currentMaxOpenPositions": 10,
        "accountMarginMetricsReady": True,
        "currentMarginBalance": 2000.0,
        "currentInitialMargin": 200.0,
        "projectedInitialMargin": 230.0,
        "projectedEffectiveLeverage": 0.65,
        "projectedMarginUtilization": 0.115,
        "accountNetDirectionalReady": True,
        "currentNetDirectionalNotional": 400.0,
        "projectedNetDirectionalNotional": 500.0,
        "lastDecisionCode": "ORDER_ROUTING_DISABLED",
        "detail": "simulation execution host ready",
    }


def budget(view: dict, budget_id: str) -> dict:
    return next(row for row in view["budgets"] if row["id"] == budget_id)


def main() -> int:
    status = base_status()

    view = mod.build_view(
        status,
        now_ms=1_001_000,
        source_path="execution_status.v1.json",
        max_source_age_ms=5_000,
    )
    assert view["gateState"] == "CLEAR"
    assert view["blockReasons"] == []
    assert view["orderRoutingEnabled"] is False
    daily = budget(view, "DAILY_RISK_CAPITAL_LOSS")
    assert daily["status"] == "HEADROOM"
    assert abs(daily["headroom"] - 75.0) < 1e-12
    assert abs(daily["consumedRatio"] - 0.25) < 1e-12
    account = view["accountRiskObservation"]
    assert account["ready"] is True
    assert abs(account["availableBalanceHeadroom"] - 570.0) < 1e-12
    assert abs(account["grossNotionalHeadroom"] - 3700.0) < 1e-12
    assert account["openPositionHeadroom"] == 7
    assert abs(account["effectiveLeverageHeadroom"] - 2.35) < 1e-12
    assert abs(account["marginUtilizationHeadroom"] - 0.485) < 1e-12
    assert abs(account["longDirectionalHeadroom"] - 4500.0) < 1e-12
    assert abs(account["shortDirectionalHeadroom"] - 5500.0) < 1e-12

    observation_missing = base_status()
    observation_missing["accountRiskObservationReady"] = False
    view = mod.build_view(
        observation_missing,
        now_ms=1_001_000,
        source_path="execution_status.v1.json",
        max_source_age_ms=5_000,
    )
    assert view["gateState"] == "ACCOUNT_NOT_RECONCILED"
    assert (
        "ACCOUNT_NOT_RECONCILED:ACCOUNT_RISK_OBSERVATION_UNAVAILABLE"
        in view["blockReasons"]
    )

    blocked = base_status()
    blocked["dailyRealizedTradeLoss"] = 50.0
    view = mod.build_view(
        blocked,
        now_ms=1_001_000,
        source_path="execution_status.v1.json",
        max_source_age_ms=5_000,
    )
    assert view["gateState"] == "RISK_BLOCKED"
    assert "RISK_BLOCKED:DAILY_REALIZED_TRADE_LOSS" in view["blockReasons"]
    assert budget(view, "DAILY_REALIZED_TRADE_LOSS")["headroom"] == 0.0

    unavailable = base_status()
    unavailable["realizedPnlReady"] = False
    view = mod.build_view(
        unavailable,
        now_ms=1_001_000,
        source_path="execution_status.v1.json",
        max_source_age_ms=5_000,
    )
    assert view["gateState"] == "ACCOUNT_NOT_RECONCILED"
    assert (
        "ACCOUNT_NOT_RECONCILED:REALIZED_PNL_UNAVAILABLE"
        in view["blockReasons"]
    )

    stale = mod.build_view(
        base_status(),
        now_ms=1_010_001,
        source_path="execution_status.v1.json",
        max_source_age_ms=5_000,
    )
    assert stale["gateState"] == "ACCOUNT_NOT_RECONCILED"
    assert stale["sourceFresh"] is False
    assert (
        "ACCOUNT_NOT_RECONCILED:EXECUTION_STATUS_STALE"
        in stale["blockReasons"]
    )

    rollback = mod.build_view(
        base_status(),
        now_ms=999_999,
        source_path="execution_status.v1.json",
        max_source_age_ms=5_000,
    )
    assert rollback["gateState"] == "ACCOUNT_NOT_RECONCILED"
    assert (
        "ACCOUNT_NOT_RECONCILED:EXECUTION_STATUS_CLOCK_ROLLBACK"
        in rollback["blockReasons"]
    )

    disabled = base_status()
    disabled["maxDailyRiskCapitalLoss"] = 0.0
    view = mod.build_view(
        disabled,
        now_ms=1_001_000,
        source_path="execution_status.v1.json",
        max_source_age_ms=5_000,
    )
    assert budget(view, "DAILY_RISK_CAPITAL_LOSS")["status"] == "DISABLED"
    assert budget(view, "DAILY_RISK_CAPITAL_LOSS")["headroom"] is None

    unsafe = base_status()
    unsafe["orderRoutingEnabled"] = True
    try:
        mod.build_view(
            unsafe,
            now_ms=1_001_000,
            source_path="execution_status.v1.json",
            max_source_age_ms=5_000,
        )
    except ValueError as exc:
        assert "orderRoutingEnabled" in str(exc)
    else:
        raise AssertionError("unsafe routing status must be rejected")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        source = root / "status.json"
        output_json = root / "view.json"
        output_html = root / "view.html"
        source.write_text(json.dumps(base_status()), encoding="utf-8")
        mod.publish_once(
            source,
            output_json,
            output_html,
            max_source_age_ms=10**15,
            refresh_seconds=1.0,
        )
        obj = json.loads(output_json.read_text(encoding="utf-8"))
        html = output_html.read_text(encoding="utf-8")
        assert obj["messageType"] == "AccountRiskView.v1"
        assert obj["orderRoutingEnabled"] is False
        assert "READ ONLY" in html
        assert "No order controls exist in this view." in html
        assert "orderRoutingEnabled=false" in html

    print("ACCOUNT_RISK_VIEW_TESTS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
