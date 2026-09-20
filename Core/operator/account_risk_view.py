#!/usr/bin/env python3
"""Read-only Account Risk operator view derived from ExecutionStatus.v1.

The view never opens a trading endpoint and contains no mutation controls.
It projects already-published execution/risk evidence into deterministic JSON
and a local auto-refreshing HTML page.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
DEFAULT_STATUS = RUNTIME / "execution_status.v1.json"
DEFAULT_JSON = RUNTIME / "account_risk_view.v1.json"
DEFAULT_HTML = RUNTIME / "account_risk_view.html"

BUDGET_SPECS = (
    (
        "DAILY_RISK_CAPITAL_LOSS",
        "Daily Risk Capital loss",
        "RISK_CAPITAL",
        "dailyStartRiskCapital",
        "dailyRiskCapitalLoss",
        "maxDailyRiskCapitalLoss",
        "accountLossMetricsReady",
    ),
    (
        "WEEKLY_RISK_CAPITAL_LOSS",
        "Weekly Risk Capital loss",
        "RISK_CAPITAL",
        "weeklyStartRiskCapital",
        "weeklyRiskCapitalLoss",
        "maxWeeklyRiskCapitalLoss",
        "accountLossMetricsReady",
    ),
    (
        "DAILY_TOTAL_PNL_LOSS",
        "Daily total-PnL compatibility loss",
        "MARGIN_BALANCE",
        "dailyStartMarginBalance",
        "dailyTotalPnlLoss",
        "maxDailyTotalPnlLoss",
        "accountLossMetricsReady",
    ),
    (
        "WEEKLY_TOTAL_PNL_LOSS",
        "Weekly total-PnL compatibility loss",
        "MARGIN_BALANCE",
        "weeklyStartMarginBalance",
        "weeklyTotalPnlLoss",
        "maxWeeklyTotalPnlLoss",
        "accountLossMetricsReady",
    ),
    (
        "ACCOUNT_DRAWDOWN",
        "Account drawdown from high-water Margin Balance",
        "HIGH_WATER_MARGIN_BALANCE",
        "highWaterMarginBalance",
        "accountDrawdown",
        "maxAccountDrawdown",
        "accountLossMetricsReady",
    ),
    (
        "DAILY_REALIZED_TRADE_LOSS",
        "Daily realized-trade loss",
        "REALIZED_PNL_LEDGER",
        None,
        "dailyRealizedTradeLoss",
        "maxDailyRealizedTradeLoss",
        "realizedPnlReady",
    ),
    (
        "WEEKLY_REALIZED_TRADE_LOSS",
        "Weekly realized-trade loss",
        "REALIZED_PNL_LEDGER",
        None,
        "weeklyRealizedTradeLoss",
        "maxWeeklyRealizedTradeLoss",
        "realizedPnlReady",
    ),
)


def _number(obj: dict[str, Any], key: str) -> float:
    value = obj.get(key, 0.0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{key} must be finite")
    return value


def _integer(obj: dict[str, Any], key: str) -> int:
    value = obj.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _boolean(obj: dict[str, Any], key: str) -> bool:
    value = obj.get(key, False)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be boolean")
    return value


def _string(obj: dict[str, Any], key: str, default: str = "") -> str:
    value = obj.get(key, default)
    if value is None and default == "":
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _utc_day_label(day_index: int) -> str:
    if day_index <= 0:
        return ""
    try:
        return (date(1970, 1, 1) + timedelta(days=day_index)).isoformat()
    except (OverflowError, ValueError):
        return ""


def _budget_row(
    status: dict[str, Any],
    *,
    budget_id: str,
    label: str,
    baseline_kind: str,
    baseline_key: str | None,
    consumption_key: str,
    limit_key: str,
    readiness_key: str,
    source_fresh: bool,
) -> dict[str, Any]:
    limit = _number(status, limit_key)
    consumption = _number(status, consumption_key)
    if limit < 0 or consumption < 0:
        raise ValueError(f"{budget_id} values must be non-negative")
    enabled = limit > 0
    evidence_ready = source_fresh and _boolean(status, readiness_key)
    blocked = enabled and evidence_ready and consumption >= limit
    headroom = max(0.0, limit - consumption) if enabled else None
    ratio = consumption / limit if enabled else None

    if not enabled:
        row_status = "DISABLED"
    elif not evidence_ready:
        row_status = "UNAVAILABLE"
    elif blocked:
        row_status = "BLOCKED"
    else:
        row_status = "HEADROOM"

    return {
        "id": budget_id,
        "label": label,
        "baselineKind": baseline_kind,
        "baselineValue": (
            _number(status, baseline_key) if baseline_key is not None else None
        ),
        "consumption": consumption,
        "limit": limit,
        "headroom": headroom,
        "consumedRatio": ratio,
        "enabled": enabled,
        "evidenceReady": evidence_ready,
        "blocked": blocked,
        "status": row_status,
    }


def validate_status(status: dict[str, Any]) -> None:
    if status.get("schemaVersion") != 1:
        raise ValueError("unsupported ExecutionStatus schemaVersion")
    if status.get("messageType") != "ExecutionStatus.v1":
        raise ValueError("expected ExecutionStatus.v1")
    if status.get("orderRoutingEnabled") is not False:
        raise ValueError("operator view refuses status with orderRoutingEnabled != false")
    generated = _integer(status, "generatedUnixMs")
    if generated <= 0:
        raise ValueError("generatedUnixMs must be positive")
    _string(status, "lifecycleState")
    _string(status, "riskProvider")
    _string(status, "realizedPnlProvider")
    _boolean(status, "accountRiskObservationReady")
    _integer(status, "accountRiskObservedUnixMs")
    _string(status, "accountRiskState")
    for key in (
        "currentRiskCapital",
        "currentAvailableBalance",
        "projectedAvailableBalance",
        "currentGrossNotional",
        "projectedGrossNotional",
        "currentMaxGrossNotional",
        "currentMarginBalance",
        "currentInitialMargin",
        "projectedInitialMargin",
        "projectedEffectiveLeverage",
        "projectedMarginUtilization",
        "currentNetDirectionalNotional",
        "projectedNetDirectionalNotional",
    ):
        _number(status, key)
    for key in (
        "currentOpenPositions",
        "projectedOpenPositions",
        "currentMaxOpenPositions",
    ):
        _integer(status, key)
    _boolean(status, "accountMarginMetricsReady")
    _boolean(status, "accountNetDirectionalReady")
    for spec in BUDGET_SPECS:
        _number(status, spec[4])
        _number(status, spec[5])
        _boolean(status, spec[6])


def build_view(
    status: dict[str, Any],
    *,
    now_ms: int,
    source_path: str,
    max_source_age_ms: int,
) -> dict[str, Any]:
    validate_status(status)
    if max_source_age_ms <= 0:
        raise ValueError("max_source_age_ms must be positive")

    source_generated = _integer(status, "generatedUnixMs")
    source_age = now_ms - source_generated
    source_fresh = 0 <= source_age <= max_source_age_ms

    budgets = [
        _budget_row(
            status,
            budget_id=spec[0],
            label=spec[1],
            baseline_kind=spec[2],
            baseline_key=spec[3],
            consumption_key=spec[4],
            limit_key=spec[5],
            readiness_key=spec[6],
            source_fresh=source_fresh,
        )
        for spec in BUDGET_SPECS
    ]

    reasons: list[str] = []
    account_limits_enabled = any(
        row["enabled"]
        for row in budgets
        if row["id"]
        not in ("DAILY_REALIZED_TRADE_LOSS", "WEEKLY_REALIZED_TRADE_LOSS")
    )
    realized_limits_enabled = any(
        row["enabled"]
        for row in budgets
        if row["id"]
        in ("DAILY_REALIZED_TRADE_LOSS", "WEEKLY_REALIZED_TRADE_LOSS")
    )

    if source_age < 0:
        reasons.append("ACCOUNT_NOT_RECONCILED:EXECUTION_STATUS_CLOCK_ROLLBACK")
    elif not source_fresh:
        reasons.append("ACCOUNT_NOT_RECONCILED:EXECUTION_STATUS_STALE")

    if source_fresh and account_limits_enabled and not _boolean(
        status, "accountLossMetricsReady"
    ):
        reasons.append("ACCOUNT_NOT_RECONCILED:ACCOUNT_LOSS_METRICS_UNAVAILABLE")

    if source_fresh and realized_limits_enabled and not _boolean(
        status, "realizedPnlReady"
    ):
        reasons.append("ACCOUNT_NOT_RECONCILED:REALIZED_PNL_UNAVAILABLE")

    account_observation_ready = (
        source_fresh and _boolean(status, "accountRiskObservationReady")
    )
    if source_fresh and not account_observation_ready:
        reasons.append("ACCOUNT_NOT_RECONCILED:ACCOUNT_RISK_OBSERVATION_UNAVAILABLE")

    if account_observation_ready:
        risk_state = _string(status, "accountRiskState")
        if risk_state in ("BLOCK_NEW_ENTRIES", "EMERGENCY"):
            reasons.append(f"RISK_BLOCKED:ACCOUNT_RISK_STATE_{risk_state}")

        max_open_positions = _integer(status, "currentMaxOpenPositions")
        projected_open_positions = _integer(status, "projectedOpenPositions")
        if (
            max_open_positions > 0
            and projected_open_positions >= max_open_positions
        ):
            reasons.append("RISK_BLOCKED:MAX_OPEN_POSITIONS")

        max_pending = _integer(status, "maxPendingEntryScaleInReservations")
        active_pending = _integer(status, "activeExposureReservations")
        if max_pending > 0 and active_pending >= max_pending:
            reasons.append("RISK_BLOCKED:MAX_PENDING_ENTRY_SCALE_IN_RESERVATIONS")

        max_gross = _number(status, "currentMaxGrossNotional")
        projected_gross = _number(status, "projectedGrossNotional")
        if max_gross > 0 and projected_gross >= max_gross:
            reasons.append("RISK_BLOCKED:MAX_GROSS_NOTIONAL")

        min_available = _number(status, "minimumAvailableBalanceReserve")
        projected_available = _number(status, "projectedAvailableBalance")
        if min_available > 0 and projected_available <= min_available:
            reasons.append("RISK_BLOCKED:MINIMUM_AVAILABLE_BALANCE_RESERVE")

        leverage_limit = _number(status, "maxEffectiveLeverage")
        margin_limit = _number(status, "maxMarginUtilization")
        margin_ready = _boolean(status, "accountMarginMetricsReady")
        if (leverage_limit > 0 or margin_limit > 0) and not margin_ready:
            reasons.append("ACCOUNT_NOT_RECONCILED:MARGIN_METRICS_UNAVAILABLE")
        elif margin_ready:
            if (
                leverage_limit > 0
                and _number(status, "projectedEffectiveLeverage")
                >= leverage_limit
            ):
                reasons.append("RISK_BLOCKED:MAX_EFFECTIVE_LEVERAGE")
            if (
                margin_limit > 0
                and _number(status, "projectedMarginUtilization")
                >= margin_limit
            ):
                reasons.append("RISK_BLOCKED:MAX_MARGIN_UTILIZATION")

        directional_limit = _number(status, "maxNetDirectionalNotional")
        directional_ready = _boolean(status, "accountNetDirectionalReady")
        if directional_limit > 0 and not directional_ready:
            reasons.append("ACCOUNT_NOT_RECONCILED:NET_DIRECTIONAL_EXPOSURE_UNAVAILABLE")
        elif directional_limit > 0:
            projected_net = _number(status, "projectedNetDirectionalNotional")
            if projected_net >= directional_limit:
                reasons.append("RISK_BLOCKED:LONG_NET_DIRECTIONAL_LIMIT")
            if projected_net <= -directional_limit:
                reasons.append("RISK_BLOCKED:SHORT_NET_DIRECTIONAL_LIMIT")

    if not any(reason.startswith("ACCOUNT_NOT_RECONCILED:") for reason in reasons):
        for row in budgets:
            if row["blocked"]:
                reasons.append(f"RISK_BLOCKED:{row['id']}")

    if any(reason.startswith("ACCOUNT_NOT_RECONCILED:") for reason in reasons):
        gate_state = "ACCOUNT_NOT_RECONCILED"
    elif any(reason.startswith("RISK_BLOCKED:") for reason in reasons):
        gate_state = "RISK_BLOCKED"
    else:
        gate_state = "CLEAR"

    day_index = _integer(status, "accountLossUtcDayIndex")
    week_index = _integer(status, "accountLossUtcWeekStartDayIndex")

    return {
        "schemaVersion": 1,
        "messageType": "AccountRiskView.v1",
        "generatedUnixMs": int(now_ms),
        "sourceExecutionStatusPath": source_path,
        "sourceGeneratedUnixMs": source_generated,
        "sourceAgeMs": source_age,
        "sourceFresh": source_fresh,
        "maxSourceAgeMs": int(max_source_age_ms),
        "lifecycleState": _string(status, "lifecycleState"),
        "riskProvider": _string(status, "riskProvider"),
        "realizedPnlProvider": _string(status, "realizedPnlProvider"),
        "orderRoutingEnabled": False,
        "gateState": gate_state,
        "blockReasons": reasons,
        "periods": {
            "utcDayIndex": day_index,
            "utcDay": _utc_day_label(day_index),
            "utcWeekStartDayIndex": week_index,
            "utcWeekStart": _utc_day_label(week_index),
        },
        "budgets": budgets,
        "realizedPnlEvidence": {
            "ready": source_fresh and _boolean(status, "realizedPnlReady"),
            "settlementAsset": _string(status, "realizedPnlSettlementAsset"),
            "dailyRealizedTradePnl": _number(status, "dailyRealizedTradePnl"),
            "weeklyRealizedTradePnl": _number(status, "weeklyRealizedTradePnl"),
            "dailyFundingFee": _number(status, "dailyFundingFee"),
            "weeklyFundingFee": _number(status, "weeklyFundingFee"),
            "dailyCommission": _number(status, "dailyCommission"),
            "weeklyCommission": _number(status, "weeklyCommission"),
            "dailyNetTradingIncome": _number(status, "dailyNetTradingIncome"),
            "weeklyNetTradingIncome": _number(status, "weeklyNetTradingIncome"),
            "recordsInCurrentWeek": _integer(
                status, "realizedPnlRecordsInCurrentWeek"
            ),
            "ignoredIncomeRecords": _integer(
                status, "realizedPnlIgnoredIncomeRecords"
            ),
        },
        "accountRiskObservation": {
            "ready": account_observation_ready,
            "observedUnixMs": _integer(status, "accountRiskObservedUnixMs"),
            "riskState": _string(status, "accountRiskState"),
            "riskCapital": _number(status, "currentRiskCapital"),
            "availableBalance": _number(status, "currentAvailableBalance"),
            "projectedAvailableBalance": _number(
                status, "projectedAvailableBalance"
            ),
            "availableBalanceHeadroom": max(
                0.0,
                _number(status, "projectedAvailableBalance")
                - _number(status, "minimumAvailableBalanceReserve"),
            ),
            "grossNotional": _number(status, "currentGrossNotional"),
            "projectedGrossNotional": _number(
                status, "projectedGrossNotional"
            ),
            "maxGrossNotional": _number(status, "currentMaxGrossNotional"),
            "grossNotionalHeadroom": max(
                0.0,
                _number(status, "currentMaxGrossNotional")
                - _number(status, "projectedGrossNotional"),
            ),
            "openPositions": _integer(status, "currentOpenPositions"),
            "projectedOpenPositions": _integer(
                status, "projectedOpenPositions"
            ),
            "maxOpenPositions": _integer(status, "currentMaxOpenPositions"),
            "openPositionHeadroom": max(
                0,
                _integer(status, "currentMaxOpenPositions")
                - _integer(status, "projectedOpenPositions"),
            ),
            "marginMetricsReady": (
                source_fresh and _boolean(status, "accountMarginMetricsReady")
            ),
            "marginBalance": _number(status, "currentMarginBalance"),
            "initialMargin": _number(status, "currentInitialMargin"),
            "projectedInitialMargin": _number(
                status, "projectedInitialMargin"
            ),
            "projectedEffectiveLeverage": _number(
                status, "projectedEffectiveLeverage"
            ),
            "effectiveLeverageHeadroom": (
                max(
                    0.0,
                    _number(status, "maxEffectiveLeverage")
                    - _number(status, "projectedEffectiveLeverage"),
                )
                if _number(status, "maxEffectiveLeverage") > 0
                else None
            ),
            "projectedMarginUtilization": _number(
                status, "projectedMarginUtilization"
            ),
            "marginUtilizationHeadroom": (
                max(
                    0.0,
                    _number(status, "maxMarginUtilization")
                    - _number(status, "projectedMarginUtilization"),
                )
                if _number(status, "maxMarginUtilization") > 0
                else None
            ),
            "netDirectionalReady": (
                source_fresh and _boolean(status, "accountNetDirectionalReady")
            ),
            "netDirectionalNotional": _number(
                status, "currentNetDirectionalNotional"
            ),
            "projectedNetDirectionalNotional": _number(
                status, "projectedNetDirectionalNotional"
            ),
            "longDirectionalHeadroom": (
                max(
                    0.0,
                    _number(status, "maxNetDirectionalNotional")
                    - _number(status, "projectedNetDirectionalNotional"),
                )
                if _number(status, "maxNetDirectionalNotional") > 0
                else None
            ),
            "shortDirectionalHeadroom": (
                max(
                    0.0,
                    _number(status, "maxNetDirectionalNotional")
                    + _number(status, "projectedNetDirectionalNotional"),
                )
                if _number(status, "maxNetDirectionalNotional") > 0
                else None
            ),
        },
        "projectedRisk": {
            "activeExposureReservations": _integer(
                status, "activeExposureReservations"
            ),
            "reservedGrossNotional": _number(status, "reservedGrossNotional"),
            "reservedAvailableBalance": _number(
                status, "reservedAvailableBalance"
            ),
            "reservedNetDirectionalNotional": _number(
                status, "reservedNetDirectionalNotional"
            ),
            "reservedPositionSlots": _integer(status, "reservedPositionSlots"),
            "maxPendingEntryScaleInReservations": _integer(
                status, "maxPendingEntryScaleInReservations"
            ),
            "maxSymbolNotional": _number(status, "maxSymbolNotional"),
            "minimumAvailableBalanceReserve": _number(
                status, "minimumAvailableBalanceReserve"
            ),
            "simulationMarginReservationRate": _number(
                status, "simulationMarginReservationRate"
            ),
            "maxEffectiveLeverage": _number(status, "maxEffectiveLeverage"),
            "maxMarginUtilization": _number(status, "maxMarginUtilization"),
            "maxNetDirectionalNotional": _number(
                status, "maxNetDirectionalNotional"
            ),
        },
        "lastDecisionCode": status.get("lastDecisionCode"),
        "detail": _string(status, "detail"),
    }


def build_error_view(
    *,
    now_ms: int,
    source_path: str,
    max_source_age_ms: int,
    reason: str,
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "messageType": "AccountRiskView.v1",
        "generatedUnixMs": int(now_ms),
        "sourceExecutionStatusPath": source_path,
        "sourceGeneratedUnixMs": 0,
        "sourceAgeMs": 0,
        "sourceFresh": False,
        "maxSourceAgeMs": int(max_source_age_ms),
        "lifecycleState": "UNKNOWN",
        "riskProvider": "UNKNOWN",
        "realizedPnlProvider": "UNKNOWN",
        "orderRoutingEnabled": False,
        "gateState": "ACCOUNT_NOT_RECONCILED",
        "blockReasons": [f"ACCOUNT_NOT_RECONCILED:EXECUTION_STATUS_ERROR:{reason}"],
        "periods": {
            "utcDayIndex": 0,
            "utcDay": "",
            "utcWeekStartDayIndex": 0,
            "utcWeekStart": "",
        },
        "budgets": [],
        "realizedPnlEvidence": {
            "ready": False,
            "settlementAsset": "",
            "dailyRealizedTradePnl": 0.0,
            "weeklyRealizedTradePnl": 0.0,
            "dailyFundingFee": 0.0,
            "weeklyFundingFee": 0.0,
            "dailyCommission": 0.0,
            "weeklyCommission": 0.0,
            "dailyNetTradingIncome": 0.0,
            "weeklyNetTradingIncome": 0.0,
            "recordsInCurrentWeek": 0,
            "ignoredIncomeRecords": 0,
        },
        "accountRiskObservation": {
            "ready": False,
            "observedUnixMs": 0,
            "riskState": "UNKNOWN",
            "riskCapital": 0.0,
            "availableBalance": 0.0,
            "projectedAvailableBalance": 0.0,
            "availableBalanceHeadroom": 0.0,
            "grossNotional": 0.0,
            "projectedGrossNotional": 0.0,
            "maxGrossNotional": 0.0,
            "grossNotionalHeadroom": 0.0,
            "openPositions": 0,
            "projectedOpenPositions": 0,
            "maxOpenPositions": 0,
            "openPositionHeadroom": 0,
            "marginMetricsReady": False,
            "marginBalance": 0.0,
            "initialMargin": 0.0,
            "projectedInitialMargin": 0.0,
            "projectedEffectiveLeverage": 0.0,
            "effectiveLeverageHeadroom": None,
            "projectedMarginUtilization": 0.0,
            "marginUtilizationHeadroom": None,
            "netDirectionalReady": False,
            "netDirectionalNotional": 0.0,
            "projectedNetDirectionalNotional": 0.0,
            "longDirectionalHeadroom": None,
            "shortDirectionalHeadroom": None,
        },
        "projectedRisk": {
            "activeExposureReservations": 0,
            "reservedGrossNotional": 0.0,
            "reservedAvailableBalance": 0.0,
            "reservedNetDirectionalNotional": 0.0,
            "reservedPositionSlots": 0,
            "maxPendingEntryScaleInReservations": 0,
            "maxSymbolNotional": 0.0,
            "minimumAvailableBalanceReserve": 0.0,
            "simulationMarginReservationRate": 0.0,
            "maxEffectiveLeverage": 0.0,
            "maxMarginUtilization": 0.0,
            "maxNetDirectionalNotional": 0.0,
        },
        "lastDecisionCode": None,
        "detail": "ExecutionStatus evidence unavailable",
    }


def _fmt(value: Any, decimals: int = 2) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "YES" if value else "NO"
    if isinstance(value, (int, float)):
        return f"{value:,.{decimals}f}"
    return str(value)


def render_html(view: dict[str, Any], refresh_seconds: float) -> str:
    esc = html.escape
    refresh = max(1, int(round(refresh_seconds)))
    gate_state = esc(str(view["gateState"]))
    reasons = view.get("blockReasons") or []
    reason_html = (
        "".join(f"<li><code>{esc(str(reason))}</code></li>" for reason in reasons)
        if reasons
        else "<li>None</li>"
    )

    budget_rows = []
    for row in view.get("budgets", []):
        ratio = row.get("consumedRatio")
        ratio_text = "—" if ratio is None else f"{ratio * 100:.1f}%"
        budget_rows.append(
            "<tr>"
            f"<td>{esc(str(row['label']))}</td>"
            f"<td>{esc(str(row['baselineKind']))}</td>"
            f"<td>{esc(_fmt(row['baselineValue']))}</td>"
            f"<td>{esc(_fmt(row['consumption']))}</td>"
            f"<td>{esc(_fmt(row['limit']))}</td>"
            f"<td>{esc(_fmt(row['headroom']))}</td>"
            f"<td>{esc(ratio_text)}</td>"
            f"<td>{esc(str(row['status']))}</td>"
            "</tr>"
        )
    if not budget_rows:
        budget_rows.append(
            '<tr><td colspan="8">No trustworthy ExecutionStatus evidence available.</td></tr>'
        )

    evidence = view["realizedPnlEvidence"]
    account = view["accountRiskObservation"]
    projected = view["projectedRisk"]
    periods = view["periods"]

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="{refresh}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Astu Account Risk — Read Only</title>
<style>
:root {{ font-family: system-ui, sans-serif; color-scheme: light dark; }}
body {{ margin: 2rem; max-width: 1200px; }}
header {{ display: flex; gap: 1rem; align-items: baseline; flex-wrap: wrap; }}
.badge {{ border: 1px solid currentColor; border-radius: 999px; padding: .2rem .6rem; font-weight: 700; }}
.notice {{ padding: .75rem 1rem; border: 1px solid currentColor; margin: 1rem 0; }}
table {{ width: 100%; border-collapse: collapse; margin: 1rem 0 2rem; }}
th, td {{ border-bottom: 1px solid #8886; padding: .55rem; text-align: right; }}
th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) {{ text-align: left; }}
code {{ overflow-wrap: anywhere; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: .75rem; }}
.card {{ border: 1px solid #8886; padding: .75rem 1rem; }}
dt {{ font-weight: 650; }}
dd {{ margin: 0 0 .5rem; }}
small {{ opacity: .8; }}
</style>
</head>
<body>
<header>
<h1>Account Risk</h1>
<span class="badge">{gate_state}</span>
<span class="badge">READ ONLY</span>
</header>
<div class="notice">
<strong>No order controls exist in this view.</strong>
orderRoutingEnabled=false. This page only renders local ExecutionStatus.v1 evidence.
</div>
<div class="grid">
<div class="card"><dl>
<dt>Lifecycle</dt><dd>{esc(str(view['lifecycleState']))}</dd>
<dt>Risk provider</dt><dd>{esc(str(view['riskProvider']))}</dd>
<dt>Realized-PnL provider</dt><dd>{esc(str(view['realizedPnlProvider']))}</dd>
</dl></div>
<div class="card"><dl>
<dt>ExecutionStatus fresh</dt><dd>{esc(_fmt(view['sourceFresh']))}</dd>
<dt>Source age</dt><dd>{esc(_fmt(view['sourceAgeMs'], 0))} ms</dd>
<dt>Freshness limit</dt><dd>{esc(_fmt(view['maxSourceAgeMs'], 0))} ms</dd>
</dl></div>
<div class="card"><dl>
<dt>UTC day</dt><dd>{esc(str(periods['utcDay'] or periods['utcDayIndex']))}</dd>
<dt>UTC week start</dt><dd>{esc(str(periods['utcWeekStart'] or periods['utcWeekStartDayIndex']))}</dd>
<dt>Settlement asset</dt><dd>{esc(str(evidence['settlementAsset'] or '—'))}</dd>
</dl></div>
</div>

<h2>Current block reasons</h2>
<ul>{reason_html}</ul>

<h2>Loss budgets and headroom</h2>
<table>
<thead><tr>
<th>Control</th><th>Baseline</th><th>Start / high-water</th>
<th>Consumption</th><th>Limit</th><th>Headroom</th><th>Consumed</th><th>Status</th>
</tr></thead>
<tbody>{''.join(budget_rows)}</tbody>
</table>

<h2>Realized-PnL evidence</h2>
<div class="grid">
<div class="card"><dl>
<dt>Daily realized trade PnL</dt><dd>{esc(_fmt(evidence['dailyRealizedTradePnl']))}</dd>
<dt>Daily funding</dt><dd>{esc(_fmt(evidence['dailyFundingFee']))}</dd>
<dt>Daily commission</dt><dd>{esc(_fmt(evidence['dailyCommission']))}</dd>
<dt>Daily net classified income</dt><dd>{esc(_fmt(evidence['dailyNetTradingIncome']))}</dd>
</dl></div>
<div class="card"><dl>
<dt>Weekly realized trade PnL</dt><dd>{esc(_fmt(evidence['weeklyRealizedTradePnl']))}</dd>
<dt>Weekly funding</dt><dd>{esc(_fmt(evidence['weeklyFundingFee']))}</dd>
<dt>Weekly commission</dt><dd>{esc(_fmt(evidence['weeklyCommission']))}</dd>
<dt>Weekly net classified income</dt><dd>{esc(_fmt(evidence['weeklyNetTradingIncome']))}</dd>
</dl></div>
<div class="card"><dl>
<dt>Records this week</dt><dd>{esc(_fmt(evidence['recordsInCurrentWeek'], 0))}</dd>
<dt>Ignored income records</dt><dd>{esc(_fmt(evidence['ignoredIncomeRecords'], 0))}</dd>
<dt>Evidence ready</dt><dd>{esc(_fmt(evidence['ready']))}</dd>
</dl></div>
</div>

<h2>Live account and projected headroom</h2>
<div class="grid">
<div class="card"><dl>
<dt>Risk state</dt><dd>{esc(str(account['riskState']))}</dd>
<dt>Risk Capital</dt><dd>{esc(_fmt(account['riskCapital']))}</dd>
<dt>Available balance</dt><dd>{esc(_fmt(account['availableBalance']))}</dd>
<dt>Projected available balance</dt><dd>{esc(_fmt(account['projectedAvailableBalance']))}</dd>
<dt>Available-balance headroom</dt><dd>{esc(_fmt(account['availableBalanceHeadroom']))}</dd>
</dl></div>
<div class="card"><dl>
<dt>Gross notional</dt><dd>{esc(_fmt(account['grossNotional']))}</dd>
<dt>Projected gross notional</dt><dd>{esc(_fmt(account['projectedGrossNotional']))}</dd>
<dt>Gross-notional headroom</dt><dd>{esc(_fmt(account['grossNotionalHeadroom']))}</dd>
<dt>Projected open positions</dt><dd>{esc(_fmt(account['projectedOpenPositions'], 0))}</dd>
<dt>Open-position headroom</dt><dd>{esc(_fmt(account['openPositionHeadroom'], 0))}</dd>
</dl></div>
<div class="card"><dl>
<dt>Projected effective leverage</dt><dd>{esc(_fmt(account['projectedEffectiveLeverage']))}</dd>
<dt>Leverage headroom</dt><dd>{esc(_fmt(account['effectiveLeverageHeadroom']))}</dd>
<dt>Projected margin utilization</dt><dd>{esc(_fmt(account['projectedMarginUtilization'] * 100))}%</dd>
<dt>Margin-utilization headroom</dt><dd>{esc(_fmt(None if account['marginUtilizationHeadroom'] is None else account['marginUtilizationHeadroom'] * 100))}%</dd>
</dl></div>
<div class="card"><dl>
<dt>Projected signed net notional</dt><dd>{esc(_fmt(account['projectedNetDirectionalNotional']))}</dd>
<dt>LONG directional headroom</dt><dd>{esc(_fmt(account['longDirectionalHeadroom']))}</dd>
<dt>SHORT directional headroom</dt><dd>{esc(_fmt(account['shortDirectionalHeadroom']))}</dd>
<dt>Account observation ready</dt><dd>{esc(_fmt(account['ready']))}</dd>
</dl></div>
</div>

<h2>Projected exposure context</h2>
<div class="grid">
<div class="card"><dl>
<dt>Active reservations</dt><dd>{esc(_fmt(projected['activeExposureReservations'], 0))}</dd>
<dt>Reserved gross notional</dt><dd>{esc(_fmt(projected['reservedGrossNotional']))}</dd>
<dt>Reserved balance</dt><dd>{esc(_fmt(projected['reservedAvailableBalance']))}</dd>
<dt>Reserved signed net notional</dt><dd>{esc(_fmt(projected['reservedNetDirectionalNotional']))}</dd>
</dl></div>
<div class="card"><dl>
<dt>Max pending reservations</dt><dd>{esc(_fmt(projected['maxPendingEntryScaleInReservations'], 0))}</dd>
<dt>Max symbol notional</dt><dd>{esc(_fmt(projected['maxSymbolNotional']))}</dd>
<dt>Minimum free-balance reserve</dt><dd>{esc(_fmt(projected['minimumAvailableBalanceReserve']))}</dd>
</dl></div>
<div class="card"><dl>
<dt>Max effective leverage</dt><dd>{esc(_fmt(projected['maxEffectiveLeverage']))}</dd>
<dt>Max margin utilization</dt><dd>{esc(_fmt(projected['maxMarginUtilization'] * 100))}%</dd>
<dt>Max directional notional</dt><dd>{esc(_fmt(projected['maxNetDirectionalNotional']))}</dd>
</dl></div>
</div>

<p><small>Last decision: {esc(str(view.get('lastDecisionCode') or '—'))}. Detail: {esc(str(view.get('detail') or ''))}</small></p>
<p><small>Source: <code>{esc(str(view['sourceExecutionStatusPath']))}</code></small></p>
</body>
</html>
"""


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def publish_once(
    status_path: Path,
    output_json: Path,
    output_html: Path,
    *,
    max_source_age_ms: int,
    refresh_seconds: float,
) -> dict[str, Any]:
    now_ms = int(time.time() * 1000)
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if not isinstance(status, dict):
            raise ValueError("ExecutionStatus root must be an object")
        view = build_view(
            status,
            now_ms=now_ms,
            source_path=str(status_path),
            max_source_age_ms=max_source_age_ms,
        )
    except Exception as exc:
        view = build_error_view(
            now_ms=now_ms,
            source_path=str(status_path),
            max_source_age_ms=max_source_age_ms,
            reason=str(exc)[:240],
        )

    write_atomic(
        output_json,
        json.dumps(view, indent=2, sort_keys=True) + "\n",
    )
    write_atomic(output_html, render_html(view, refresh_seconds))
    return view


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execution-status-file", default=str(DEFAULT_STATUS))
    ap.add_argument("--output-json", default=str(DEFAULT_JSON))
    ap.add_argument("--output-html", default=str(DEFAULT_HTML))
    ap.add_argument("--max-source-age-ms", type=int, default=5000)
    ap.add_argument("--poll-seconds", type=float, default=1.0)
    ap.add_argument("--watch", action="store_true")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_source_age_ms <= 0 or args.poll_seconds <= 0:
        print("ACCOUNT_RISK_VIEW_FATAL=invalid freshness/poll settings")
        return 2

    status_path = Path(args.execution_status_file).resolve()
    output_json = Path(args.output_json).resolve()
    output_html = Path(args.output_html).resolve()

    while True:
        view = publish_once(
            status_path,
            output_json,
            output_html,
            max_source_age_ms=args.max_source_age_ms,
            refresh_seconds=args.poll_seconds,
        )
        print(
            "ACCOUNT_RISK_VIEW_STATE="
            f"{view['gateState']} SOURCE_FRESH={str(view['sourceFresh']).lower()}"
        )
        print("ORDER_ROUTING_ENABLED=false")
        if not args.watch:
            return 0
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
