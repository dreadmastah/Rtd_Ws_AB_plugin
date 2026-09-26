#!/usr/bin/env python3
"""Offline contract tests for the LIVE readiness evaluator (T01-T35)."""
from __future__ import annotations

import ast
from dataclasses import replace
import inspect
from pathlib import Path
import sys
import unittest
from unittest import mock


ACCOUNT_DIR = Path(__file__).resolve().parents[1] / "account"
sys.path.insert(0, str(ACCOUNT_DIR))

import binance_usdm_credential_binding as binding
import binance_usdm_live_preflight as preflight


class LivePreflightTests(unittest.TestCase):
    def ready(self, **changes):
        complete = preflight.LivePreflightInput(
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
        return replace(complete, **changes)

    def check(self, result, check_id):
        return next(c for c in result.check_results if c.check_id == check_id)

    def assert_rejected(self, check_id, **changes):
        result = preflight.evaluate_live_preflight(self.ready(**changes))
        self.assertEqual(result.overall_status, "FAIL")
        self.assertIn(check_id, result.failed_check_ids)
        self.assertFalse(result.armed)
        return result

    def called_names(self):
        tree = ast.parse(inspect.getsource(preflight))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    names.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    names.add(node.func.attr)
        return names

    def test_T01_valid_live_all_pass(self):
        result = preflight.evaluate_live_preflight(self.ready())
        self.assertEqual(result.overall_status, "PASS")
        self.assertEqual(len(result.check_results), 13)
        self.assertEqual(result.failed_check_ids, ())

    def test_T02_demo_rejected(self):
        self.assert_rejected("LIVE_ENVIRONMENT", environment="DEMO")

    def test_T03_unknown_environment_rejected(self):
        result = self.assert_rejected("LIVE_ENVIRONMENT", environment="UNKNOWN")
        self.assertEqual(result.environment, "UNBOUND")
        self.assert_rejected("LIVE_ENVIRONMENT", environment=None)

    def test_T04_configuration_fail(self):
        self.assert_rejected("CONFIGURATION_VALID", configuration_valid="FAIL")

    def test_T05_configuration_unknown(self):
        self.assert_rejected("CONFIGURATION_VALID", configuration_valid="UNKNOWN")
        self.assert_rejected("CONFIGURATION_VALID", configuration_valid=None)
        invalid = self.assert_rejected("CONFIGURATION_VALID", configuration_valid=True)
        self.assertEqual(self.check(invalid, "CONFIGURATION_VALID").reason_code, "INVALID_STATE")

    def test_T06_workflow_fail(self):
        self.assert_rejected("WORKFLOW_VALID", workflow_valid="FAIL")

    def test_T07_workflow_unknown(self):
        self.assert_rejected("WORKFLOW_VALID", workflow_valid="UNKNOWN")

    def test_T08_registry_fail(self):
        self.assert_rejected("REGISTRY_VALID", registry_valid="FAIL")

    def test_T09_registry_unknown(self):
        self.assert_rejected("REGISTRY_VALID", registry_valid="UNKNOWN")

    def test_T10_d1_binding_invalid(self):
        self.assert_rejected(
            "LIVE_CREDENTIAL_BINDING", credential_profile="TESTNET_SIGNED_READONLY"
        )

    def test_T11_credential_presence_missing(self):
        self.assert_rejected("LIVE_CREDENTIAL_PRESENT", credential_presence_valid=None)

    def test_T12_endpoint_profile_mismatch(self):
        self.assert_rejected("ENDPOINT_PROFILE_BINDING", rest_base_url=binding.DEMO_REST_BASE)
        self.assert_rejected(
            "ENDPOINT_PROFILE_BINDING",
            private_ws_template=binding.DEMO_USER_STREAM_TEMPLATE,
        )
        self.assert_rejected("ENDPOINT_PROFILE_BINDING", private_ws_template=None)

    def test_T13_live_enabled_fail(self):
        self.assert_rejected("LIVE_ENABLED", live_enabled="FAIL")

    def test_T14_live_enabled_unknown(self):
        self.assert_rejected("LIVE_ENABLED", live_enabled="UNKNOWN")

    def test_T15_reconciliation_fail(self):
        self.assert_rejected("RECONCILIATION_READY", reconciliation_ready="FAIL")

    def test_T16_reconciliation_unknown(self):
        self.assert_rejected("RECONCILIATION_READY", reconciliation_ready="UNKNOWN")

    def test_T17_risk_fail(self):
        self.assert_rejected("RISK_LIMITS_READY", risk_limits_ready="FAIL")

    def test_T18_risk_unknown(self):
        self.assert_rejected("RISK_LIMITS_READY", risk_limits_ready="UNKNOWN")

    def test_T19_process_fail(self):
        self.assert_rejected("PROCESS_INSTANCE_READY", process_instance_ready="FAIL")

    def test_T20_data_stale_fail(self):
        self.assert_rejected("DATA_CONNECTIVITY_READY", data_connectivity_ready="FAIL")

    def test_T21_persistence_fail(self):
        self.assert_rejected("PERSISTENCE_READY", persistence_ready="FAIL")

    def test_T22_multiple_failures_ordered(self):
        result = preflight.evaluate_live_preflight(
            self.ready(workflow_valid="FAIL", persistence_ready="UNKNOWN")
        )
        self.assertEqual(
            result.failed_check_ids, ("WORKFLOW_VALID", "PERSISTENCE_READY")
        )

    def test_T23_stable_reason_metadata(self):
        result = self.assert_rejected("WORKFLOW_VALID", workflow_valid="FAIL")
        check = self.check(result, "WORKFLOW_VALID")
        self.assertEqual(check.reason_code, "REPORTED_FAIL")
        self.assertEqual(check.source_class, "REQUIRED_NEW_INPUT_CONTRACT")
        self.assertTrue(check.required)

    def test_T24_unexpected_exception_is_sanitized(self):
        with mock.patch.object(
            preflight.binding,
            "resolve_credential_binding",
            side_effect=RuntimeError("SECRET_SENTINEL"),
        ):
            result = preflight.evaluate_live_preflight(self.ready())
        self.assertEqual(result.overall_status, "FAIL")
        self.assertEqual(result.failed_check_ids, ("EVALUATION_EXCEPTION",))
        self.assertNotIn("SECRET_SENTINEL", repr(result))

    def test_T25_no_order_submission_call(self):
        self.assertTrue(
            self.called_names().isdisjoint({"submit_order", "place_order", "submit"})
        )

    def test_T26_no_order_cancellation_call(self):
        self.assertTrue(
            self.called_names().isdisjoint({"cancel_order", "cancel_all_orders"})
        )

    def test_T27_no_arm_live_call(self):
        self.assertTrue(self.called_names().isdisjoint({"arm_live", "ARM_LIVE"}))

    def test_T28_no_credential_value_read_or_mutation(self):
        with mock.patch.object(preflight.binding, "read_bound_credentials") as reader:
            result = preflight.evaluate_live_preflight(self.ready())
        self.assertEqual(result.overall_status, "PASS")
        reader.assert_not_called()

    def test_T29_no_risk_limit_mutation_call(self):
        self.assertTrue(
            self.called_names().isdisjoint({"set_risk_limits", "change_risk_limit"})
        )

    def test_T30_pass_remains_readiness_only(self):
        result = preflight.evaluate_live_preflight(self.ready())
        self.assertEqual(result.readiness_state, "READY_FOR_OPERATOR_ARMING")
        self.assertFalse(result.armed)

    def test_T31_workflow_missing(self):
        self.assert_rejected("WORKFLOW_VALID", workflow_valid=None)

    def test_T32_registry_missing(self):
        self.assert_rejected("REGISTRY_VALID", registry_valid=None)

    def test_T33_credential_presence_unknown(self):
        self.assert_rejected("LIVE_CREDENTIAL_PRESENT", credential_presence_valid="UNKNOWN")

    def test_T34_unsupported_profile(self):
        self.assert_rejected("LIVE_CREDENTIAL_BINDING", credential_profile="UNSUPPORTED")

    def test_T35_identical_input_is_deterministic(self):
        snapshot = self.ready()
        self.assertEqual(
            preflight.evaluate_live_preflight(snapshot),
            preflight.evaluate_live_preflight(snapshot),
        )


if __name__ == "__main__":
    unittest.main()
