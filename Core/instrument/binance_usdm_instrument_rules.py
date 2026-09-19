#!/usr/bin/env python3
"""Publish Binance USD-M public instrument filters as InstrumentConstraints.v1.

This module uses only public exchange metadata. It contains no credentials,
private API access, signing, or order submission.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
DEFAULT_OUTPUT = ROOT / "runtime" / "instrument_constraints"
DEFAULT_SYMBOLS_FILE = REPO / "CleanRoomR2" / "stack" / "bootstrap_symbols.tls"
DEFAULT_REST_BASE = "https://fapi.binance.com"


def load_symbols(path: Path) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        symbol = line.strip().upper()
        if not symbol or symbol.startswith("#") or symbol in seen:
            continue
        seen.add(symbol)
        out.append(symbol)
    return out


def fetch_exchange_info(rest_base: str, fixture: Path | None) -> dict[str, Any]:
    if fixture is not None:
        return json.loads(fixture.read_text(encoding="utf-8"))
    url = rest_base.rstrip("/") + "/fapi/v1/exchangeInfo"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "AstuInstrumentRules/1.0"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def decimal_value(value: Any) -> float:
    x = float(str(value))
    if x < 0:
        raise ValueError("negative filter value")
    return x


def build_constraint(symbol_obj: dict[str, Any], now_ms: int) -> dict[str, Any]:
    symbol = str(symbol_obj.get("symbol", "")).upper()
    filters = {
        str(item.get("filterType", "")): item
        for item in symbol_obj.get("filters", [])
        if isinstance(item, dict)
    }

    price = filters.get("PRICE_FILTER")
    lot = filters.get("LOT_SIZE")
    min_notional_filter = filters.get("MIN_NOTIONAL")
    if not isinstance(price, dict) or not isinstance(lot, dict):
        raise ValueError(f"{symbol}: PRICE_FILTER/LOT_SIZE missing")

    tick = decimal_value(price.get("tickSize"))
    step = decimal_value(lot.get("stepSize"))
    min_qty = decimal_value(lot.get("minQty"))
    max_qty = decimal_value(lot.get("maxQty"))
    min_notional = 0.0
    if isinstance(min_notional_filter, dict):
        raw = min_notional_filter.get("notional", min_notional_filter.get("minNotional", 0))
        min_notional = decimal_value(raw)

    if tick <= 0 or step <= 0 or max_qty <= 0:
        raise ValueError(f"{symbol}: non-positive tick/step/maxQty")

    return {
        "schemaVersion": 1,
        "messageType": "InstrumentConstraints.v1",
        "generatedUnixMs": now_ms,
        "ready": True,
        "source": "BINANCE_USDM_EXCHANGE_INFO",
        "symbol": symbol,
        "priceTick": tick,
        "quantityStep": step,
        "minQuantity": min_qty,
        "maxQuantity": max_qty,
        "minNotional": min_notional,
        "maxNotional": 0.0,
        "detail": "public exchangeInfo PRICE_FILTER + LOT_SIZE + MIN_NOTIONAL",
    }


def write_atomic(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def publish_once(
    output_dir: Path,
    symbols: list[str],
    rest_base: str,
    fixture: Path | None,
) -> int:
    info = fetch_exchange_info(rest_base, fixture)
    by_symbol = {
        str(item.get("symbol", "")).upper(): item
        for item in info.get("symbols", [])
        if isinstance(item, dict)
    }
    missing = [symbol for symbol in symbols if symbol not in by_symbol]
    if missing:
        raise RuntimeError("exchangeInfo missing symbols: " + ",".join(missing))

    now_ms = int(time.time() * 1000)
    for symbol in symbols:
        constraint = build_constraint(by_symbol[symbol], now_ms)
        write_atomic(output_dir / f"{symbol}.json", constraint)
    print(
        f"INSTRUMENT_RULES_PUBLISHED={len(symbols)} "
        f"OUTPUT_DIR={output_dir} SOURCE=BINANCE_USDM_EXCHANGE_INFO"
    )
    return 0


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--fixture", type=Path)
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--symbols-file", type=Path, default=DEFAULT_SYMBOLS_FILE)
    ap.add_argument("--symbols", default="")
    ap.add_argument("--rest-base", default=DEFAULT_REST_BASE)
    ap.add_argument("--poll-seconds", type=float, default=3600.0)
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    if args.symbols:
        symbols = [
            item.strip().upper()
            for item in args.symbols.split(",")
            if item.strip()
        ]
    else:
        symbols = load_symbols(args.symbols_file)
    if not symbols:
        raise RuntimeError("no instrument symbols selected")

    while True:
        publish_once(args.output_dir, symbols, args.rest_base, args.fixture)
        if args.once:
            return 0
        time.sleep(max(60.0, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
