#!/usr/bin/env python3
"""Offline D4 structural Live-canary configuration contract (T01-T51)."""
from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, fields, replace
from decimal import Decimal
import inspect
from pathlib import Path
import socket
import subprocess
import sys
import unittest
from unittest import mock
import urllib.request


ACCOUNT_DIR = Path(__file__).resolve().parents[1] / "account"
sys.path.insert(0, str(ACCOUNT_DIR))
import binance_usdm_live_canary_config as canary


class LiveCanaryConfigTests(unittest.TestCase):
    def ready(self, **changes):
        config = canary.LiveCanaryConfigInput(
            config_kind="LIVE_CANARY_CONFIGURATION",
            environment="LIVE",
            symbols=("ETHUSDT", "BTCUSDT"),
            max_concurrent_positions=2,
            max_notional_usdt=Decimal("100.00"),
            strategy_id="offline-fixture",
            strategy_version="v1",
        )
        return replace(config, **changes)

    def result(self, **changes):
        return canary.validate_live_canary_config(self.ready(**changes))

    def reject(self, check_id, **changes):
        result = self.result(**changes)
        self.assertEqual(result.status, "INVALID")
        self.assertIn(check_id, result.failed_check_ids)
        self.assertIsNone(result.normalized_config)
        self.assertFalse(result.can_activate_live)
        return result

    def calls(self):
        tree = ast.parse(inspect.getsource(canary))
        return {
            node.func.id if isinstance(node.func, ast.Name) else node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, (ast.Name, ast.Attribute))
        }

    def test_T01_valid_structural_config(self):
        result = self.result()
        self.assertEqual(result.status, "VALID")
        self.assertEqual(result.failed_check_ids, ())
        self.assertEqual(result.authority_state, "STRUCTURAL_ONLY_NOT_A5_APPROVED")

    def test_T02_demo_rejected(self):
        self.reject("LIVE_ENVIRONMENT", environment="DEMO")

    def test_T03_unknown_environment_rejected(self):
        self.reject("LIVE_ENVIRONMENT", environment="UNKNOWN")

    def test_T04_missing_environment_rejected(self):
        self.reject("LIVE_ENVIRONMENT", environment=None)

    def test_T05_missing_universe_rejected(self):
        self.reject("RESTRICTED_UNIVERSE", symbols=None)

    def test_T06_empty_universe_rejected(self):
        self.reject("RESTRICTED_UNIVERSE", symbols=())

    def test_T07_duplicate_symbol_rejected(self):
        self.reject("RESTRICTED_UNIVERSE", symbols=("BTCUSDT", "BTCUSDT"))

    def test_T08_blank_symbol_rejected(self):
        self.reject("RESTRICTED_UNIVERSE", symbols=("BTCUSDT", ""))

    def test_T09_malformed_symbol_rejected(self):
        self.reject("RESTRICTED_UNIVERSE", symbols=("BTCUSDT", "ETH*USDT"))

    def test_T10_universe_order_deterministic(self):
        a = self.result(symbols=("ETHUSDT", "BTCUSDT"))
        b = self.result(symbols=("BTCUSDT", "ETHUSDT"))
        self.assertEqual(a.normalized_config, b.normalized_config)
        self.assertEqual(a.normalized_config[2], ("BTCUSDT", "ETHUSDT"))

    def test_T11_missing_positions_rejected(self):
        self.reject("MAX_CONCURRENT_POSITIONS", max_concurrent_positions=None)

    def test_T12_zero_positions_rejected(self):
        self.reject("MAX_CONCURRENT_POSITIONS", max_concurrent_positions=0)

    def test_T13_negative_positions_rejected(self):
        self.reject("MAX_CONCURRENT_POSITIONS", max_concurrent_positions=-1)

    def test_T14_noninteger_positions_rejected(self):
        self.reject("MAX_CONCURRENT_POSITIONS", max_concurrent_positions=1.5)

    def test_T15_boolean_positions_rejected(self):
        self.reject("MAX_CONCURRENT_POSITIONS", max_concurrent_positions=True)

    def test_T16_missing_notional_rejected(self):
        self.reject("MAX_NOTIONAL_USDT", max_notional_usdt=None)

    def test_T17_zero_notional_rejected(self):
        self.reject("MAX_NOTIONAL_USDT", max_notional_usdt=Decimal("0"))

    def test_T18_negative_notional_rejected(self):
        self.reject("MAX_NOTIONAL_USDT", max_notional_usdt=Decimal("-1"))

    def test_T19_nan_rejected(self):
        self.reject("MAX_NOTIONAL_USDT", max_notional_usdt=Decimal("NaN"))

    def test_T20_positive_infinity_rejected(self):
        self.reject("MAX_NOTIONAL_USDT", max_notional_usdt=Decimal("Infinity"))

    def test_T21_negative_infinity_rejected(self):
        self.reject("MAX_NOTIONAL_USDT", max_notional_usdt=Decimal("-Infinity"))

    def test_T22_wrong_notional_type_rejected(self):
        self.reject("MAX_NOTIONAL_USDT", max_notional_usdt=100.0)

    def test_T23_missing_or_invalid_identity_rejected(self):
        self.reject("CONFIG_KIND", config_kind=None)
        self.reject("CONFIG_KIND", config_kind="GENERIC_LIVE")

    def test_T24_validation_cannot_activate_live(self):
        self.assertFalse(self.result().can_activate_live)
        self.assertNotIn("canary_enabled", {f.name for f in fields(canary.LiveCanaryConfigInput)})

    def test_T25_missing_strategy_rejected(self):
        self.reject("STRATEGY_ID", strategy_id=None)

    def test_T26_no_separate_workflow_field(self):
        self.assertNotIn("workflow_id", {f.name for f in fields(canary.LiveCanaryConfigInput)})
        self.assertEqual(self.result().status, "VALID")

    def test_T27_unsupported_canary_kind_rejected(self):
        self.reject("CONFIG_KIND", config_kind="TESTNET_CANARY")

    def test_T28_malformed_object_rejected(self):
        result = canary.validate_live_canary_config({"environment": "LIVE"})
        self.assertEqual(result.status, "INVALID")
        self.assertEqual(result.failed_check_ids[0], "CONFIG_KIND")

    def test_T29_unexpected_exception_fails_closed(self):
        with mock.patch.object(canary, "_symbols", side_effect=RuntimeError("private-value")):
            result = self.result()
        self.assertEqual(result.status, "INVALID")
        self.assertEqual(result.reason_codes, ("EVALUATION_EXCEPTION",) * 7)
        self.assertNotIn("private-value", str(result))

    def test_T30_stable_check_ids(self):
        self.assertEqual(tuple(c.check_id for c in self.result().check_results), (
            "CONFIG_KIND", "LIVE_ENVIRONMENT", "RESTRICTED_UNIVERSE",
            "MAX_CONCURRENT_POSITIONS", "MAX_NOTIONAL_USDT",
            "STRATEGY_ID", "STRATEGY_VERSION",
        ))

    def test_T31_stable_reason_order(self):
        result = self.result(environment="DEMO", max_concurrent_positions=0)
        self.assertEqual(result.failed_check_ids, (
            "LIVE_ENVIRONMENT", "MAX_CONCURRENT_POSITIONS",
        ))
        self.assertEqual(result.reason_codes, ("UNSUPPORTED", "OUT_OF_RANGE"))

    def test_T32_normalized_representation(self):
        self.assertEqual(self.result().normalized_config, (
            "LIVE_CANARY_CONFIGURATION", "LIVE", ("BTCUSDT", "ETHUSDT"),
            2, "100", "offline-fixture", "v1",
        ))

    def test_T33_no_api_secret_required(self):
        self.assertFalse(any("secret" in f.name or "api_key" in f.name
                             for f in fields(canary.LiveCanaryConfigInput)))
        self.assertEqual(self.result().status, "VALID")

    def test_T34_no_listen_key_required(self):
        self.assertFalse(any("listen" in f.name.lower()
                             for f in fields(canary.LiveCanaryConfigInput)))
        self.assertEqual(self.result().status, "VALID")

    def test_T35_no_network_access(self):
        with mock.patch.object(socket, "socket", side_effect=AssertionError("socket")), \
             mock.patch.object(socket, "create_connection", side_effect=AssertionError("connect")):
            self.assertEqual(self.result().status, "VALID")

    def test_T36_no_binance_access(self):
        with mock.patch.object(urllib.request, "urlopen", side_effect=AssertionError("http")):
            self.assertEqual(self.result().status, "VALID")

    def test_T37_no_arm_mutation(self):
        self.assertNotIn("arm_live", self.calls())
        self.assertFalse(self.result().can_activate_live)

    def test_T38_no_live_enable_mutation(self):
        self.assertNotIn("enable_live", self.calls())
        self.assertFalse(self.result().can_activate_live)

    def test_T39_no_order_submission(self):
        self.assertTrue(self.calls().isdisjoint({"submit_order", "place_order", "create_order"}))

    def test_T40_no_cancellation(self):
        self.assertTrue(self.calls().isdisjoint({"cancel_order", "cancel_all_orders"}))

    def test_T41_no_position_mutation(self):
        self.assertTrue(self.calls().isdisjoint({"set_position", "update_position"}))

    def test_T42_no_credential_mutation(self):
        self.assertTrue(self.calls().isdisjoint({"set_credential", "write_secret"}))

    def test_T43_no_risk_limit_mutation(self):
        self.assertTrue(self.calls().isdisjoint({"set_risk_limit", "update_risk"}))

    def test_T44_no_runtime_control(self):
        with mock.patch.object(subprocess, "Popen", side_effect=AssertionError("runtime")):
            self.assertEqual(self.result().status, "VALID")

    def test_T45_structural_validity_not_A5_approval(self):
        result = self.result()
        self.assertEqual(result.authority_state, "STRUCTURAL_ONLY_NOT_A5_APPROVED")
        self.assertFalse(result.can_activate_live)

    def test_T46_defaults_not_A5_locked(self):
        result = canary.validate_live_canary_config(canary.LiveCanaryConfigInput())
        self.assertEqual(result.status, "INVALID")
        self.assertEqual(result.authority_state, "STRUCTURAL_ONLY_NOT_A5_APPROVED")

    def test_T47_validation_does_not_allocate_capital(self):
        self.assertTrue(self.calls().isdisjoint({"allocate_capital", "transfer", "withdraw"}))
        self.assertEqual(self.result().normalized_config[4], "100")

    def test_T48_validation_does_not_mutate_universe(self):
        config = self.ready()
        original = config.symbols
        result = canary.validate_live_canary_config(config)
        self.assertEqual(result.normalized_config[2], ("BTCUSDT", "ETHUSDT"))
        self.assertEqual(config.symbols, original)

    def test_T49_input_object_immutable(self):
        config = self.ready()
        with self.assertRaises(FrozenInstanceError):
            config.environment = "DEMO"
        self.assertEqual(config, self.ready())

    def test_T50_repeated_validation_deterministic(self):
        config = self.ready()
        self.assertEqual(canary.validate_live_canary_config(config),
                         canary.validate_live_canary_config(config))

    def test_T51_oversized_exponent_rejected(self):
        self.reject("MAX_NOTIONAL_USDT", max_notional_usdt=Decimal("1E+1000"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
