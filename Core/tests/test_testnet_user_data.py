#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "account" / "binance_usdm_testnet_user_data.py"
spec = importlib.util.spec_from_file_location("testnet_user_data", MOD)
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)

def write(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj)+"\n", encoding="utf-8")

def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        journal = root / "journal.jsonl"
        order_id = "SIMORD-0123456789abcdef0123456789abcdef"
        client_id = "ASTU-123456789abcdef0123456789abcdef"
        journal.write_text(json.dumps({
            "schemaVersion":1,
            "eventType":"TESTNET_ORDER_SUBMISSION_ATTEMPT",
            "utcMs":1789909999000,
            "simulationOrderId":order_id,
            "requestId":"REQ",
            "signalId":"SIG",
            "symbol":"BTCUSDT",
            "exchangeSide":"BUY",
            "quantity":0.102,
            "reduceOnly":False,
            "clientOrderId":client_id,
            "executionEnvironment":"BINANCE_USDM_TESTNET",
            "exchangeSubmissionAttempted":True
        })+"\n", encoding="utf-8")
        write(root/"account.json", {
            "schemaVersion":1,"messageType":"AccountRiskSnapshot.v1",
            "generatedUnixMs":1789910000000,"source":"TEST",
            "reconciled":True,"riskState":"NORMAL","riskCapital":10250,
            "availableBalance":9150,"marginBalance":10250,"initialMargin":100,
            "grossNotional":1000,"netDirectionalNotional":1000,
            "maxGrossNotional":100000,"openPositions":1,"maxOpenPositions":10,
            "detail":"fixture"
        })
        write(root/"positions"/"BTCUSDT.json", {
            "schemaVersion":1,"messageType":"PositionSnapshot.v1",
            "generatedUnixMs":1789910000000,"source":"TEST",
            "reconciled":True,"symbol":"BTCUSDT","mode":"LONG",
            "quantity":10,"notional":1000,"detail":"fixture"
        })
        auth = m.Authority(
            status_path=root/"status.json",
            order_dir=root/"orders",
            journal=journal,
            account_snapshot=root/"account.json",
            position_dir=root/"positions",
            max_liveness_ms=15000,
        )
        auth.mark_connected(1789910000050)
        account_event = {
            "e":"ACCOUNT_UPDATE","E":1789910000000,
            "a":{"m":"ORDER","B":[],"P":[{"s":"BTCUSDT","pa":"10.0"}]}
        }
        auth.process(account_event,1789910000100)
        assert auth.snapshot(1789910000100)["accountConverged"] is True
        order_event = {
            "e":"ORDER_TRADE_UPDATE","E":1789910000100,
            "o":{"s":"BTCUSDT","c":client_id,"q":"0.102","z":"0.102",
                 "X":"FILLED","i":123456789}
        }
        auth.process(order_event,1789910000200)
        out = json.loads((root/"orders"/f"{order_id}.json").read_text())
        assert out["ready"] is True
        assert out["state"] == "FILLED"
        assert abs(out["cumulativeFilledQuantity"]-0.102) < 1e-12
        status = auth.snapshot(1789910000200)
        assert status["ready"] is True
        assert status["ordersConverged"] is True
        assert status["accountConverged"] is True
        assert status["positionsConverged"] is True
        assert status["restFallbackRequired"] is False

        stale = auth.snapshot(1789910020001)
        assert stale["streamAlive"] is False
        assert stale["ready"] is False

        try:
            auth.process({"e":"ORDER_TRADE_UPDATE","E":1789900000000,"o":{
                "s":"BTCUSDT","c":client_id,"q":"0.102","z":"0.102",
                "X":"FILLED","i":123456789}},1789910000300)
        except m.UserDataError:
            pass
        else:
            raise AssertionError("event-time regression must fail closed")

    print("TESTNET_USER_DATA_AUTHORITY=PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
