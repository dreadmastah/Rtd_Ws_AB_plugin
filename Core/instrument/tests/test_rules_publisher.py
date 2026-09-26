#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parent
MODULE_PATH = ROOT / "instrument" / "binance_usdm_instrument_rules.py"
FIXTURE = (
    ROOT
    / "instrument"
    / "tests"
    / "fixtures"
    / "binance_usdm_exchange_info_bootstrap12.json"
)
SYMBOLS_FILE = REPO / "CleanRoomR2" / "stack" / "bootstrap_symbols.tls"

spec = importlib.util.spec_from_file_location("instrument_rules", MODULE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load instrument rules module")
rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rules)


def assert_all_absent(output: Path, symbols: list[str]) -> None:
    leftovers = [s for s in symbols if (output / f"{s}.json").exists()]
    assert not leftovers, f"stale instrument snapshots survived invalidation: {leftovers}"


def main() -> int:
    symbols = rules.load_symbols(SYMBOLS_FILE)
    assert len(symbols) == 12, symbols
    assert symbols[0] == "BTCUSDT"
    assert symbols[-1] == "ETHUSDT"

    baseline = json.loads(FIXTURE.read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory(prefix="astu-instrument-rules-") as td:
        root = Path(td)
        output = root / "out"

        rules.publish_once(output, symbols, "unused", FIXTURE)
        files = sorted(p.stem for p in output.glob("*.json"))
        assert len(files) == 12, files
        assert set(files) == set(symbols)

        btc = json.loads((output / "BTCUSDT.json").read_text(encoding="utf-8"))
        assert btc["ready"] is True
        assert btc["source"] == "BINANCE_USDM_EXCHANGE_INFO"
        assert abs(btc["quantityStep"] - 0.001) < 1e-12
        assert abs(btc["minNotional"] - 5.0) < 1e-12

        changed = copy.deepcopy(baseline)
        btc_obj = next(x for x in changed["symbols"] if x["symbol"] == "BTCUSDT")
        for item in btc_obj["filters"]:
            if item["filterType"] == "LOT_SIZE":
                item["stepSize"] = "0.010"
            elif item["filterType"] == "MIN_NOTIONAL":
                item["notional"] = "20"
        changed_path = root / "changed.json"
        changed_path.write_text(json.dumps(changed), encoding="utf-8")

        rules.publish_once(output, symbols, "unused", changed_path)
        btc_changed = json.loads(
            (output / "BTCUSDT.json").read_text(encoding="utf-8")
        )
        assert abs(btc_changed["quantityStep"] - 0.01) < 1e-12
        assert abs(btc_changed["minNotional"] - 20.0) < 1e-12
        assert len(list(output.glob("*.json"))) == 12

        market_specific = copy.deepcopy(baseline)
        market_btc = next(
            x for x in market_specific["symbols"]
            if x["symbol"] == "BTCUSDT"
        )
        market_btc["filters"].append({
            "filterType": "MARKET_LOT_SIZE",
            "minQty": "0.0001",
            "maxQty": "1000",
            "stepSize": "0.0001",
        })
        market_path = root / "market-specific.json"
        market_path.write_text(
            json.dumps(market_specific),
            encoding="utf-8",
        )
        rules.publish_once(output, symbols, "unused", market_path)
        btc_market = json.loads(
            (output / "BTCUSDT.json").read_text(encoding="utf-8")
        )
        assert abs(btc_market["quantityStep"] - 0.0001) < 1e-12
        assert abs(btc_market["minQuantity"] - 0.0001) < 1e-12
        assert "MARKET_LOT_SIZE" in btc_market["detail"]

        missing = copy.deepcopy(baseline)
        missing["symbols"] = [
            x for x in missing["symbols"] if x["symbol"] != "ETHUSDT"
        ]
        missing_path = root / "missing.json"
        missing_path.write_text(json.dumps(missing), encoding="utf-8")
        try:
            rules.publish_once(output, symbols, "unused", missing_path)
            raise AssertionError("missing bootstrap symbol was not rejected")
        except RuntimeError as exc:
            assert "ETHUSDT" in str(exc)
        assert_all_absent(output, symbols)

        rules.publish_once(output, symbols, "unused", FIXTURE)
        malformed = copy.deepcopy(baseline)
        sol_obj = next(x for x in malformed["symbols"] if x["symbol"] == "SOLUSDT")
        sol_obj["filters"] = [
            x for x in sol_obj["filters"] if x["filterType"] != "LOT_SIZE"
        ]
        malformed_path = root / "malformed.json"
        malformed_path.write_text(json.dumps(malformed), encoding="utf-8")
        try:
            rules.publish_once(output, symbols, "unused", malformed_path)
            raise AssertionError("malformed filter set was not rejected")
        except ValueError as exc:
            assert "SOLUSDT" in str(exc)
        assert_all_absent(output, symbols)

    print("INSTRUMENT_RULES_RECOVERY_TEST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
