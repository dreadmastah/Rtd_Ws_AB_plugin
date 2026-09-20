#!/usr/bin/env python3
"""Binance USD-M read-only income history -> realized PnL evidence.

This process is deliberately USER_DATA/read-only. It exposes no order, cancel,
leverage, transfer, or margin-mutation operation.

Live mode is disabled unless ASTU_BINANCE_PRIVATE_READONLY_ENABLED=1.
Credentials are read only from environment variables.

Verified Binance USD-M endpoint:
  GET /fapi/v1/income

The reconciler requests all income types for the current Monday-aligned UTC
week, paginates to completion, and classifies REALIZED_PNL, FUNDING_FEE and
COMMISSION independently. TRANSFER and every other income type are excluded
from realized-trade-loss accounting.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://fapi.binance.com"
DEFAULT_OUTPUT = Path("Core/runtime/realized_pnl_status.v1.json")
DEFAULT_STATE = Path("Core/runtime/realized_pnl_accumulator.v1.json")
DEFAULT_LIMIT = 1000

REALIZED_PNL = "REALIZED_PNL"
FUNDING_FEE = "FUNDING_FEE"
COMMISSION = "COMMISSION"


class IncomeReconcilerError(RuntimeError):
    pass


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def utc_day_start_ms(now_ms: int) -> int:
    day_ms = 86_400_000
    return (now_ms // day_ms) * day_ms


def utc_week_start_ms(now_ms: int) -> int:
    day_ms = 86_400_000
    day_index = now_ms // day_ms
    # Unix epoch day 0 was Thursday. Monday is offset 3 days behind Thursday.
    days_since_monday = (day_index + 3) % 7
    week_start_day = max(0, day_index - days_since_monday)
    return week_start_day * day_ms


def _numeric_income(row: dict[str, Any]) -> float:
    try:
        value = float(row["income"])
    except (KeyError, TypeError, ValueError) as exc:
        raise IncomeReconcilerError("income row has invalid income") from exc
    if not math.isfinite(value):
        raise IncomeReconcilerError("income row has non-finite income")
    return value


def _integer_time(row: dict[str, Any]) -> int:
    try:
        value = int(row["time"])
    except (KeyError, TypeError, ValueError) as exc:
        raise IncomeReconcilerError("income row has invalid time") from exc
    if value < 0:
        raise IncomeReconcilerError("income row has negative time")
    return value


def normalize_rows(
    rows: list[dict[str, Any]],
    *,
    week_start_ms: int,
    now_ms: int,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            raise IncomeReconcilerError("income response contains non-object row")
        income_type = str(raw.get("incomeType", "")).upper()
        if not income_type:
            raise IncomeReconcilerError("income row missing incomeType")
        event_time = _integer_time(raw)
        if event_time < week_start_ms or event_time > now_ms:
            continue
        income = _numeric_income(raw)
        asset = str(raw.get("asset", ""))
        tran_id = str(raw.get("tranId", ""))
        trade_id = str(raw.get("tradeId", ""))
        # Binance documents tranId as unique within incomeType. Prefer that
        # stable identity; fall back to immutable row fields if it is absent.
        key = (
            (income_type, "TRAN_ID", tran_id)
            if tran_id
            else (income_type, str(event_time), trade_id, asset)
        )
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "incomeType": income_type,
                "income": income,
                "asset": asset,
                "symbol": str(raw.get("symbol", "")),
                "time": event_time,
                "tranId": tran_id,
                "tradeId": trade_id,
            }
        )
    normalized.sort(
        key=lambda row: (
            int(row["time"]),
            str(row["incomeType"]),
            str(row["tranId"]),
            str(row["tradeId"]),
        )
    )
    return normalized


def aggregate_income(
    rows: list[dict[str, Any]],
    *,
    now_ms: int,
    source: str,
    settlement_asset: str = "USDT",
    prior_state: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    day_start = utc_day_start_ms(now_ms)
    week_start = utc_week_start_ms(now_ms)
    normalized = normalize_rows(
        rows,
        week_start_ms=week_start,
        now_ms=now_ms,
    )

    def sums(start_ms: int) -> dict[str, float]:
        realized = 0.0
        funding = 0.0
        commission = 0.0
        for row in normalized:
            if int(row["time"]) < start_ms:
                continue
            income_type = str(row["incomeType"])
            value = float(row["income"])
            if income_type == REALIZED_PNL:
                realized += value
            elif income_type == FUNDING_FEE:
                funding += value
            elif income_type == COMMISSION:
                commission += value
        return {
            "realized": realized,
            "funding": funding,
            "commission": commission,
        }

    settlement_asset = settlement_asset.strip().upper()
    if not settlement_asset:
        raise IncomeReconcilerError("settlement asset is empty")
    included_types = {REALIZED_PNL, FUNDING_FEE, COMMISSION}
    unsupported = [
        row
        for row in normalized
        if row["incomeType"] in included_types
        and str(row["asset"]).upper() != settlement_asset
    ]
    if unsupported:
        assets = sorted({str(row["asset"]).upper() for row in unsupported})
        raise IncomeReconcilerError(
            "tracked income contains unsupported settlement assets: "
            + ",".join(assets)
        )

    daily = sums(day_start)
    weekly = sums(week_start)
    ignored_count = sum(
        1 for row in normalized if row["incomeType"] not in included_types
    )

    daily_loss_consumed = max(0.0, -daily["realized"])
    weekly_loss_consumed = max(0.0, -weekly["realized"])
    if prior_state is not None:
        prior_day = int(prior_state["utcDayStartUnixMs"])
        prior_week = int(prior_state["utcWeekStartUnixMs"])
        prior_updated = int(prior_state["updatedUnixMs"])
        if prior_day > day_start or prior_week > week_start or prior_updated > now_ms:
            raise IncomeReconcilerError(
                "persisted realized PnL state is ahead of current UTC time"
            )
        if (
            prior_week == week_start
            and int(prior_state["recordsInCurrentWeek"]) > len(normalized)
        ):
            raise IncomeReconcilerError(
                "current income history regressed below persisted weekly record count"
            )
        if prior_day == day_start:
            daily_loss_consumed = max(
                daily_loss_consumed,
                float(prior_state["dailyRealizedTradeLossConsumed"]),
            )
        if prior_week == week_start:
            weekly_loss_consumed = max(
                weekly_loss_consumed,
                float(prior_state["weeklyRealizedTradeLossConsumed"]),
            )

    snapshot = {
        "schemaVersion": 1,
        "messageType": "RealizedPnlSnapshot.v1",
        "generatedUnixMs": int(now_ms),
        "source": source,
        "reconciled": True,
        "settlementAsset": settlement_asset,
        "utcDayStartUnixMs": int(day_start),
        "utcWeekStartUnixMs": int(week_start),
        "dailyRealizedTradePnl": daily["realized"],
        "weeklyRealizedTradePnl": weekly["realized"],
        "dailyRealizedTradeLoss": daily_loss_consumed,
        "weeklyRealizedTradeLoss": weekly_loss_consumed,
        "dailyFundingFee": daily["funding"],
        "weeklyFundingFee": weekly["funding"],
        "dailyCommission": daily["commission"],
        "weeklyCommission": weekly["commission"],
        "dailyNetTradingIncome": (
            daily["realized"] + daily["funding"] + daily["commission"]
        ),
        "weeklyNetTradingIncome": (
            weekly["realized"] + weekly["funding"] + weekly["commission"]
        ),
        "recordsInCurrentWeek": len(normalized),
        "ignoredIncomeRecords": ignored_count,
        "detail": (
            "income history reconciled; realized trade PnL, funding and "
            "commission classified separately; transfers/other income excluded"
        ),
    }
    state = {
        "schemaVersion": 1,
        "messageType": "RealizedPnlAccumulatorState.v1",
        "updatedUnixMs": int(now_ms),
        "settlementAsset": settlement_asset,
        "utcDayStartUnixMs": int(day_start),
        "utcWeekStartUnixMs": int(week_start),
        "dailyRealizedTradePnl": daily["realized"],
        "weeklyRealizedTradePnl": weekly["realized"],
        "dailyRealizedTradeLossConsumed": daily_loss_consumed,
        "weeklyRealizedTradeLossConsumed": weekly_loss_consumed,
        "dailyFundingFee": daily["funding"],
        "weeklyFundingFee": weekly["funding"],
        "dailyCommission": daily["commission"],
        "weeklyCommission": weekly["commission"],
        "recordsInCurrentWeek": len(normalized),
        "ignoredIncomeRecords": ignored_count,
    }
    return snapshot, state


def fail_closed_snapshot(*, source: str, reason: str) -> dict[str, Any]:
    now_ms = int(time.time() * 1000)
    return {
        "schemaVersion": 1,
        "messageType": "RealizedPnlSnapshot.v1",
        "generatedUnixMs": now_ms,
        "source": source,
        "reconciled": False,
        "settlementAsset": "UNKNOWN",
        "utcDayStartUnixMs": utc_day_start_ms(now_ms),
        "utcWeekStartUnixMs": utc_week_start_ms(now_ms),
        "dailyRealizedTradePnl": 0.0,
        "weeklyRealizedTradePnl": 0.0,
        "dailyRealizedTradeLoss": 0.0,
        "weeklyRealizedTradeLoss": 0.0,
        "dailyFundingFee": 0.0,
        "weeklyFundingFee": 0.0,
        "dailyCommission": 0.0,
        "weeklyCommission": 0.0,
        "dailyNetTradingIncome": 0.0,
        "weeklyNetTradingIncome": 0.0,
        "recordsInCurrentWeek": 0,
        "ignoredIncomeRecords": 0,
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


def load_accumulator_state(
    path: Path,
    *,
    settlement_asset: str,
) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IncomeReconcilerError(
            "cannot parse persisted realized PnL accumulator state"
        ) from exc
    if not isinstance(obj, dict):
        raise IncomeReconcilerError(
            "persisted realized PnL accumulator is not an object"
        )
    if obj.get("schemaVersion") != 1 or obj.get("messageType") != (
        "RealizedPnlAccumulatorState.v1"
    ):
        raise IncomeReconcilerError(
            "persisted realized PnL accumulator schema mismatch"
        )
    expected_asset = settlement_asset.strip().upper()
    if str(obj.get("settlementAsset", "")).upper() != expected_asset:
        raise IncomeReconcilerError(
            "persisted realized PnL accumulator settlement asset mismatch"
        )
    numeric_nonnegative = [
        "dailyRealizedTradeLossConsumed",
        "weeklyRealizedTradeLossConsumed",
    ]
    integer_nonnegative = [
        "updatedUnixMs",
        "utcDayStartUnixMs",
        "utcWeekStartUnixMs",
        "recordsInCurrentWeek",
        "ignoredIncomeRecords",
    ]
    for key in numeric_nonnegative:
        try:
            value = float(obj[key])
        except (KeyError, TypeError, ValueError) as exc:
            raise IncomeReconcilerError(
                f"persisted realized PnL accumulator invalid {key}"
            ) from exc
        if not math.isfinite(value) or value < 0.0:
            raise IncomeReconcilerError(
                f"persisted realized PnL accumulator invalid {key}"
            )
    for key in integer_nonnegative:
        try:
            value = int(obj[key])
        except (KeyError, TypeError, ValueError) as exc:
            raise IncomeReconcilerError(
                f"persisted realized PnL accumulator invalid {key}"
            ) from exc
        if value < 0:
            raise IncomeReconcilerError(
                f"persisted realized PnL accumulator invalid {key}"
            )
    return obj


def load_fixture(path: Path, *, now_ms: int) -> list[dict[str, Any]]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, list):
        raise IncomeReconcilerError("income fixture must contain a JSON array")
    rows: list[dict[str, Any]] = []
    for raw in obj:
        if not isinstance(raw, dict):
            raise IncomeReconcilerError("income fixture contains non-object row")
        row = dict(raw)
        if "dayOffsetMs" in row:
            try:
                offset = int(row.pop("dayOffsetMs"))
            except (TypeError, ValueError) as exc:
                raise IncomeReconcilerError(
                    "income fixture has invalid dayOffsetMs"
                ) from exc
            row["time"] = utc_day_start_ms(now_ms) + offset
        elif "timeOffsetMs" in row:
            try:
                offset = int(row.pop("timeOffsetMs"))
            except (TypeError, ValueError) as exc:
                raise IncomeReconcilerError(
                    "income fixture has invalid timeOffsetMs"
                ) from exc
            row["time"] = now_ms + offset
        rows.append(row)
    return rows


def signed_get_income_page(
    *,
    base_url: str,
    api_key: str,
    api_secret: str,
    recv_window_ms: int,
    timeout_seconds: float,
    start_time_ms: int,
    end_time_ms: int,
    page: int,
    limit: int,
) -> list[dict[str, Any]]:
    timestamp = int(time.time() * 1000)
    params = [
        ("startTime", str(start_time_ms)),
        ("endTime", str(end_time_ms)),
        ("page", str(page)),
        ("limit", str(limit)),
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
        + "/fapi/v1/income?"
        + query
        + "&signature="
        + urllib.parse.quote(signature)
    )
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "X-MBX-APIKEY": api_key,
            "User-Agent": "ASTU-ReadOnly-Income-Reconciler/1.0",
        },
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout_seconds,
        ) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        # Do not echo private USER_DATA response bodies into logs.
        raise IncomeReconcilerError(
            f"Binance income USER_DATA HTTP {exc.code}"
        ) from exc
    except urllib.error.URLError as exc:
        raise IncomeReconcilerError(
            f"Binance income USER_DATA request failed: {exc.reason}"
        ) from exc

    try:
        obj = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise IncomeReconcilerError(
            "Binance income USER_DATA returned invalid JSON"
        ) from exc
    if not isinstance(obj, list):
        raise IncomeReconcilerError(
            "Binance income response is not an array"
        )
    return obj


def signed_get_week_income(
    *,
    base_url: str,
    api_key: str,
    api_secret: str,
    recv_window_ms: int,
    timeout_seconds: float,
    now_ms: int,
    limit: int,
) -> list[dict[str, Any]]:
    week_start = utc_week_start_ms(now_ms)
    all_rows: list[dict[str, Any]] = []
    page = 1
    while True:
        rows = signed_get_income_page(
            base_url=base_url,
            api_key=api_key,
            api_secret=api_secret,
            recv_window_ms=recv_window_ms,
            timeout_seconds=timeout_seconds,
            start_time_ms=week_start,
            end_time_ms=now_ms,
            page=page,
            limit=limit,
        )
        all_rows.extend(rows)
        if len(rows) < limit:
            break
        page += 1
        if page > 10_000:
            raise IncomeReconcilerError(
                "income pagination exceeded safety bound"
            )
    return all_rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--fixture", type=Path)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--state", type=Path, default=DEFAULT_STATE)
    ap.add_argument("--poll-seconds", type=float, default=30.0)
    ap.add_argument("--recv-window-ms", type=int, default=5_000)
    ap.add_argument("--timeout-seconds", type=float, default=10.0)
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--settlement-asset", default="USDT")
    ap.add_argument(
        "--base-url",
        default=os.getenv("BINANCE_USDM_BASE_URL", DEFAULT_BASE_URL),
    )
    args = ap.parse_args()

    if args.recv_window_ms <= 0 or args.recv_window_ms > 60_000:
        raise SystemExit("recvWindow must be in 1..60000 ms")
    if args.poll_seconds < 5.0:
        raise SystemExit("poll-seconds must be >= 5")
    if args.limit <= 0 or args.limit > 1000:
        raise SystemExit("limit must be in 1..1000")

    fixture_mode = args.fixture is not None
    if not fixture_mode and not env_bool(
        "ASTU_BINANCE_PRIVATE_READONLY_ENABLED",
        False,
    ):
        snapshot = fail_closed_snapshot(
            source="BINANCE_USDM_INCOME_DISABLED",
            reason="read-only private income reconciler disabled",
        )
        write_atomic(args.output, snapshot)
        print("BINANCE_INCOME_READONLY=DISABLED")
        print(f"OUTPUT={args.output}")
        return 3

    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")
    if not fixture_mode and (not api_key or not api_secret):
        snapshot = fail_closed_snapshot(
            source="BINANCE_USDM_INCOME_MISSING_CREDENTIALS",
            reason="read-only private income credentials unavailable",
        )
        write_atomic(args.output, snapshot)
        print("BINANCE_INCOME_READONLY=MISSING_CREDENTIALS")
        print(f"OUTPUT={args.output}")
        return 4

    try:
        prior_state = load_accumulator_state(
            args.state,
            settlement_asset=args.settlement_asset,
        )
    except Exception as exc:
        snapshot = fail_closed_snapshot(
            source="BINANCE_USDM_INCOME_STATE_INVALID",
            reason=(
                "persisted income state invalid: "
                f"{type(exc).__name__}: {exc}"
            ),
        )
        write_atomic(args.output, snapshot)
        print(
            "BINANCE_INCOME_READONLY=FAIL_CLOSED "
            f"error={type(exc).__name__}: {exc}"
        )
        return 5

    while True:
        source = (
            "BINANCE_USDM_INCOME_V1_FIXTURE"
            if fixture_mode
            else "BINANCE_USDM_INCOME_V1"
        )
        now_ms = int(time.time() * 1000)
        try:
            rows = (
                load_fixture(args.fixture, now_ms=now_ms)
                if fixture_mode
                else signed_get_week_income(
                    base_url=args.base_url,
                    api_key=api_key,
                    api_secret=api_secret,
                    recv_window_ms=args.recv_window_ms,
                    timeout_seconds=args.timeout_seconds,
                    now_ms=now_ms,
                    limit=args.limit,
                )
            )
            snapshot, state = aggregate_income(
                rows,
                now_ms=now_ms,
                source=source,
                settlement_asset=args.settlement_asset,
                prior_state=prior_state,
            )
            write_atomic(args.state, state)
            prior_state = state
            write_atomic(args.output, snapshot)
            print(
                "BINANCE_INCOME_READONLY=RECONCILED "
                f"weeklyRealizedTradePnl={snapshot['weeklyRealizedTradePnl']} "
                f"weeklyFundingFee={snapshot['weeklyFundingFee']} "
                f"weeklyCommission={snapshot['weeklyCommission']} "
                f"records={snapshot['recordsInCurrentWeek']}"
            )
        except Exception as exc:
            snapshot = fail_closed_snapshot(
                source=source,
                reason=(
                    "income reconciliation failed: "
                    f"{type(exc).__name__}: {exc}"
                ),
            )
            write_atomic(args.output, snapshot)
            print(
                "BINANCE_INCOME_READONLY=FAIL_CLOSED "
                f"error={type(exc).__name__}: {exc}"
            )

        if args.once:
            return 0 if snapshot["reconciled"] else 5
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
