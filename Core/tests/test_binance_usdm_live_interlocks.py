#!/usr/bin/env python3
"""Offline D3 logical LIVE privilege interlock contract (T1-T40)."""
from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
import inspect
from pathlib import Path
import sys
import unittest
from unittest import mock


ACCOUNT_DIR = Path(__file__).resolve().parents[1] / "account"
sys.path.insert(0, str(ACCOUNT_DIR))

import binance_usdm_credential_binding as binding
import binance_usdm_live_interlocks as interlock
import binance_usdm_live_preflight as preflight


class LiveInterlockTests(unittest.TestCase):
    def ready(self, **changes):
        snapshot = preflight.LivePreflightInput(
            environment="LIVE",
            credential_profile="LIVE_SIGNED_READONLY",
            rest_base_url=binding.LIVE_REST_BASE,
            private_ws_template=binding.LIVE_USER_STREAM_TEMPLATE,
            configuration_valid="PASS",
            workflow_valid="PASS",
            registry_valid="PASS",
            credential_presence_valid="PASS",
            live_enabled="PASS",
            reconciliation_ready="PASS",
            risk_limits_ready="PASS",
            process_instance_ready="PASS",
            data_connectivity_ready="PASS",
            persistence_ready="PASS",
        )
        return replace(snapshot, **changes)

    def evaluate(self, arm_state="ARM_LIVE", **changes):
        return interlock.evaluate_live_interlock(
            interlock.LiveInterlockInput(self.ready(**changes), arm_state)
        )

    def deny(self, check_id, arm_state="ARM_LIVE", **changes):
        result = self.evaluate(arm_state=arm_state, **changes)
        self.assertEqual(result.decision, "DENY")
        self.assertEqual(result.authorization_state, "NOT_AUTHORIZED")
        self.assertIn(check_id, result.failed_interlock_ids)
        return result

    def called_names(self):
        tree = ast.parse(inspect.getsource(interlock))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    names.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    names.add(node.func.attr)
        return names

    def test_T01_valid_live_arm_authorizes(self):
        with mock.patch.object(
            interlock.preflight, "evaluate_live_preflight",
            wraps=preflight.evaluate_live_preflight,
        ) as evaluate:
            result = self.evaluate()
        self.assertEqual(evaluate.call_count, 1)
        self.assertEqual(result.decision, "ALLOW")
        self.assertEqual(result.authorization_state, "LIVE_PRIVILEGE_AUTHORIZED")
        self.assertEqual(result.failed_interlock_ids, ())

    def test_T02_disarmed_denies(self):
        self.deny("IL_EXPLICIT_ARM_LIVE", arm_state="DISARMED")

    def test_T03_unsupported_arm_denies(self):
        result = self.deny("IL_EXPLICIT_ARM_LIVE", arm_state="ARM_PAPER")
        self.assertIn("INVALID_INTERLOCK_INPUT", result.reason_codes)

    def test_T04_demo_denies(self):
        self.deny("IL_LIVE_ENVIRONMENT", environment="DEMO")

    def test_T05_unknown_environment_denies(self):
        self.deny("IL_LIVE_ENVIRONMENT", environment="UNKNOWN")

    def test_T06_D2_failure_denies(self):
        result = self.deny("IL_D2_PREFLIGHT_PASS", configuration_valid="FAIL")
        self.assertEqual(result.preflight_overall_status, "FAIL")

    def test_T07_D2_unknown_denies(self):
        self.deny("IL_D2_PREFLIGHT_PASS", configuration_valid="UNKNOWN")

    def test_T08_configuration_denies(self):
        self.deny("IL_WORKFLOW_REGISTRY_READY", configuration_valid="FAIL")

    def test_T09_workflow_denies(self):
        self.deny("IL_WORKFLOW_REGISTRY_READY", workflow_valid="FAIL")

    def test_T10_registry_denies(self):
        self.deny("IL_WORKFLOW_REGISTRY_READY", registry_valid="FAIL")

    def test_T11_D1_binding_denies(self):
        self.deny("IL_D1_LIVE_PROFILE", credential_profile="TESTNET_USER_DATA")

    def test_T12_credential_presence_denies(self):
        self.deny("IL_D1_LIVE_PROFILE", credential_presence_valid="FAIL")

    def test_T13_endpoint_profile_mismatch_denies(self):
        self.deny("IL_D1_LIVE_PROFILE", rest_base_url=binding.DEMO_REST_BASE)

    def test_T14_live_disabled_denies(self):
        result = self.deny("IL_LIVE_ENABLED", live_enabled="FAIL")
        self.assertIn("LIVE_DISABLED", result.reason_codes)

    def test_T15_live_enable_unknown_denies(self):
        self.deny("IL_LIVE_ENABLED", live_enabled="UNKNOWN")

    def test_T16_reconciliation_denies(self):
        self.deny("IL_RECONCILIATION_READY", reconciliation_ready="FAIL")

    def test_T17_risk_denies(self):
        self.deny("IL_RISK_READY", risk_limits_ready="FAIL")

    def test_T18_process_denies(self):
        self.deny("IL_PROCESS_DATA_PERSISTENCE_READY", process_instance_ready="FAIL")

    def test_T19_data_denies(self):
        self.deny("IL_PROCESS_DATA_PERSISTENCE_READY", data_connectivity_ready="FAIL")

    def test_T20_persistence_denies(self):
        self.deny("IL_PROCESS_DATA_PERSISTENCE_READY", persistence_ready="FAIL")

    def test_T21_missing_arm_denies(self):
        self.deny("IL_EXPLICIT_ARM_LIVE", arm_state=None)

    def test_T22_malformed_arm_denies(self):
        result = self.deny("IL_FAIL_CLOSED_CONTEXT", arm_state=object())
        self.assertEqual(result.preflight_overall_status, "PASS")

    def test_T23_missing_preflight_input_denies(self):
        result = interlock.evaluate_live_interlock(
            interlock.LiveInterlockInput(None, "ARM_LIVE")
        )
        self.assertEqual(result.decision, "DENY")
        self.assertIn("IL_FAIL_CLOSED_CONTEXT", result.failed_interlock_ids)

    def test_T24_D2_exception_denies_without_text(self):
        with mock.patch.object(
            interlock.preflight, "evaluate_live_preflight",
            side_effect=RuntimeError("SENSITIVE_SENTINEL"),
        ):
            result = self.evaluate()
        self.assertEqual(result.decision, "DENY")
        self.assertIn("INTERLOCK_EVALUATION_EXCEPTION", result.reason_codes)
        self.assertNotIn("SENSITIVE_SENTINEL", repr(result))
        with mock.patch.object(
            preflight.binding, "resolve_credential_binding",
            side_effect=RuntimeError("SENSITIVE_SENTINEL"),
        ):
            sanitized = self.evaluate()
        self.assertEqual(sanitized.decision, "DENY")
        self.assertIn(
            "INTERLOCK_EVALUATION_EXCEPTION", sanitized.reason_codes
        )
        self.assertNotIn("SENSITIVE_SENTINEL", repr(sanitized))

    def test_T25_not_armed_reason_is_stable(self):
        a = self.evaluate(arm_state="DISARMED")
        b = self.evaluate(arm_state="DISARMED")
        self.assertEqual(a.reason_codes, b.reason_codes)
        self.assertEqual(a.reason_codes, ("NOT_ARMED_LIVE",))

    def test_T26_failed_preflight_reason_is_stable(self):
        a = self.evaluate(configuration_valid="FAIL")
        b = self.evaluate(configuration_valid="FAIL")
        self.assertEqual(a.reason_codes, b.reason_codes)
        self.assertIn("PREFLIGHT_NOT_READY", a.reason_codes)

    def test_T27_allow_is_authorization_only(self):
        result = self.evaluate()
        self.assertEqual(result.authorization_state, "LIVE_PRIVILEGE_AUTHORIZED")
        self.assertFalse(hasattr(result, "order_id"))
        self.assertFalse(hasattr(result, "execution_started"))

    def test_T28_arm_input_is_not_mutated(self):
        request = interlock.LiveInterlockInput(self.ready(), "DISARMED")
        interlock.evaluate_live_interlock(request)
        self.assertEqual(request.arm_state, "DISARMED")
        with self.assertRaises(FrozenInstanceError):
            request.arm_state = "ARM_LIVE"

    def test_T29_D2_input_is_not_mutated(self):
        snapshot = self.ready()
        before = replace(snapshot)
        interlock.evaluate_live_interlock(
            interlock.LiveInterlockInput(snapshot, "ARM_LIVE")
        )
        self.assertEqual(snapshot, before)
        with self.assertRaises(FrozenInstanceError):
            snapshot.live_enabled = "FAIL"

    def test_T30_no_network_IO_calls(self):
        self.assertFalse(
            self.called_names() & {"urlopen", "connect", "socket", "request"}
        )

    def test_T31_no_Binance_access_calls(self):
        self.assertFalse(
            self.called_names() & {"signed_request", "binance_request", "futures"}
        )

    def test_T32_no_order_submission_calls(self):
        self.assertFalse(
            self.called_names() & {"submit_order", "create_order", "place_order"}
        )

    def test_T33_no_cancel_calls(self):
        self.assertFalse(
            self.called_names() & {"cancel_order", "cancel_all", "cancel"}
        )

    def test_T34_no_position_mutation_calls(self):
        self.assertFalse(
            self.called_names() & {"flatten", "close_position", "set_position"}
        )

    def test_T35_no_credential_mutation_calls(self):
        self.assertFalse(
            self.called_names() & {"setenv", "write_credential", "store_secret"}
        )

    def test_T36_no_risk_limit_mutation_calls(self):
        self.assertFalse(
            self.called_names() & {"set_risk_limit", "update_risk_limit"}
        )

    def test_T37_D2_PASS_without_live_arm_denies(self):
        self.deny("IL_EXPLICIT_ARM_LIVE", arm_state="DISARMED")

    def test_T38_live_arm_without_D2_PASS_denies(self):
        self.deny("IL_D2_PREFLIGHT_PASS", risk_limits_ready="FAIL")

    def test_T39_multiple_failures_are_ordered(self):
        result = self.evaluate(
            arm_state="DISARMED", environment="DEMO",
            workflow_valid="FAIL", live_enabled="FAIL",
        )
        expected_order = tuple(
            check.check_id for check in result.check_results
            if check.status == "FAIL"
        )
        self.assertEqual(result.failed_interlock_ids, expected_order)
        self.assertEqual(
            result.reason_codes,
            tuple(
                check.reason_code for check in result.check_results
                if check.status == "FAIL"
            ),
        )

    def test_T40_bounded_stable_result_model(self):
        result = self.deny("IL_D2_PREFLIGHT_PASS", live_enabled="UNKNOWN")
        self.assertEqual(len(result.check_results), 10)
        self.assertEqual(len({x.check_id for x in result.check_results}), 10)
        self.assertTrue(all(len(code) < 64 for code in result.reason_codes))
        with self.assertRaises(FrozenInstanceError):
            result.decision = "ALLOW"


if __name__ == "__main__":
    unittest.main()
