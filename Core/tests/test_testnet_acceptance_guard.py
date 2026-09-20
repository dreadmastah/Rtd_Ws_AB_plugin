#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "tools" / "testnet_acceptance.py"
spec = importlib.util.spec_from_file_location("testnet_acceptance", MOD)
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)

def expect_fail(fn) -> None:
    try:
        fn()
    except m.AcceptanceError:
        return
    raise AssertionError("expected AcceptanceError")

def main() -> int:
    assert m.require_testnet_rest_url(
        "https://testnet.binancefuture.com"
    ) == "https://testnet.binancefuture.com"
    assert m.require_testnet_rest_url(
        "https://demo-fapi.binance.com/"
    ) == "https://demo-fapi.binance.com"

    expect_fail(lambda: m.require_testnet_rest_url(
        "https://fapi.binance.com"
    ))
    expect_fail(lambda: m.require_testnet_rest_url(
        "http://testnet.binancefuture.com"
    ))
    expect_fail(lambda: m.require_testnet_rest_url(
        "https://testnet.binancefuture.com/fapi"
    ))

    prior = os.environ.pop("ASTU_TESTNET_ACCEPTANCE_ARM", None)
    try:
        expect_fail(lambda: m.validate_execution(
            execute=True,
            quantity=0.01,
            price=100.0,
            max_notional=25.0,
        ))
        os.environ["ASTU_TESTNET_ACCEPTANCE_ARM"] = (
            "I_UNDERSTAND_TESTNET_ORDER"
        )
        notional = m.validate_execution(
            execute=True,
            quantity=0.01,
            price=100.0,
            max_notional=25.0,
        )
        assert abs(notional - 1.0) < 1e-12
        expect_fail(lambda: m.validate_execution(
            execute=True,
            quantity=1.01,
            price=100.0,
            max_notional=100.0,
        ))
        assert m.HARD_MAX_NOTIONAL == 100.0
        expect_fail(lambda: m.validate_execution(
            execute=True,
            quantity=0.01,
            price=100.0,
            max_notional=m.HARD_MAX_NOTIONAL + 1.0,
        ))
    finally:
        if prior is None:
            os.environ.pop("ASTU_TESTNET_ACCEPTANCE_ARM", None)
        else:
            os.environ["ASTU_TESTNET_ACCEPTANCE_ARM"] = prior

    assert "--reduce-only" in Path(MOD).read_text(encoding="utf-8")
    assert '("reduceOnly", "true")' in Path(MOD).read_text(encoding="utf-8")

    client_id = m.deterministic_acceptance_client_id()
    assert client_id.startswith("ASTU-ACC-")
    assert len(client_id) <= 36
    print("TESTNET_ACCEPTANCE_GUARD=PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
