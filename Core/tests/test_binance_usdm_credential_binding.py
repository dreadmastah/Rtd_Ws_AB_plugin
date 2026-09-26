#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ACCOUNT_DIR = Path(__file__).resolve().parents[1] / "account"
sys.path.insert(0, str(ACCOUNT_DIR))

import binance_usdm_credential_binding as binding
import binance_usdm_testnet_user_data as user_data


class CredentialBindingTests(unittest.TestCase):
    def resolve(self, environment, profile, rest, ws=None):
        return binding.resolve_credential_binding(
            environment=environment,
            profile=profile,
            rest_base_url=rest,
            private_ws_template=ws,
        )

    def test_T01_demo_testnet_profile_accepts_demo_family(self):
        result = self.resolve("DEMO", "TESTNET_SIGNED_READONLY", binding.DEMO_REST_BASE)
        self.assertEqual(result.credential_names, (binding.DEMO_KEY, binding.DEMO_SECRET))

    def test_T02_live_profile_accepts_live_family(self):
        result = self.resolve("LIVE", "LIVE_SIGNED_READONLY", binding.LIVE_REST_BASE)
        self.assertEqual(result.credential_names, (binding.LIVE_KEY, binding.LIVE_SECRET))

    def test_T03_demo_rejects_live_profile(self):
        with self.assertRaises(binding.CredentialBindingError):
            self.resolve("DEMO", "LIVE_SIGNED_READONLY", binding.DEMO_REST_BASE)

    def test_T04_live_rejects_testnet_profile(self):
        with self.assertRaises(binding.CredentialBindingError):
            self.resolve("LIVE", "TESTNET_SIGNED_READONLY", binding.LIVE_REST_BASE)

    def test_T05_demo_family_rejects_live_profile(self):
        with self.assertRaises(binding.CredentialBindingError):
            self.resolve("DEMO", "LIVE_SIGNED_READONLY", binding.DEMO_REST_BASE)

    def test_T06_live_family_rejects_testnet_profile(self):
        with self.assertRaises(binding.CredentialBindingError):
            self.resolve("LIVE", "TESTNET_SIGNED_READONLY", binding.LIVE_REST_BASE)

    def test_T07_mixed_demo_rest_live_private_ws_rejected(self):
        with self.assertRaisesRegex(binding.CredentialBindingError, "PRIVATE_WS_ENDPOINT_MISMATCH"):
            self.resolve("DEMO", "TESTNET_USER_DATA", binding.DEMO_REST_BASE, binding.LIVE_USER_STREAM_TEMPLATE)

    def test_T08_mixed_live_rest_demo_private_ws_rejected(self):
        with self.assertRaisesRegex(binding.CredentialBindingError, "REST_ENDPOINT_MISMATCH"):
            self.resolve("LIVE", "LIVE_SIGNED_READONLY", binding.DEMO_REST_BASE, binding.DEMO_USER_STREAM_TEMPLATE)

    def test_T09_missing_testnet_credentials_fail_closed(self):
        result = self.resolve("DEMO", "TESTNET_SIGNED_READONLY", binding.DEMO_REST_BASE)
        with self.assertRaisesRegex(binding.CredentialBindingError, "CREDENTIAL_REFERENCE_MISSING"):
            binding.read_bound_credentials(result, {binding.DEMO_KEY: "TESTNET_KEY_SENTINEL"})

    def test_T10_missing_live_credentials_fail_closed(self):
        result = self.resolve("LIVE", "LIVE_SIGNED_READONLY", binding.LIVE_REST_BASE)
        with self.assertRaisesRegex(binding.CredentialBindingError, "CREDENTIAL_REFERENCE_MISSING"):
            binding.read_bound_credentials(result, {binding.LIVE_KEY: "LIVE_KEY_SENTINEL"})

    def test_T11_generic_names_cannot_satisfy_testnet(self):
        result = self.resolve("DEMO", "TESTNET_SIGNED_READONLY", binding.DEMO_REST_BASE)
        with self.assertRaisesRegex(binding.CredentialBindingError, "GENERIC_CREDENTIAL_FORBIDDEN"):
            binding.read_bound_credentials(result, {"BINANCE_API_KEY": "generic-key", "BINANCE_API_SECRET": "generic-secret"})

    def test_T12_generic_names_cannot_satisfy_live(self):
        result = self.resolve("LIVE", "LIVE_SIGNED_READONLY", binding.LIVE_REST_BASE)
        with self.assertRaisesRegex(binding.CredentialBindingError, "GENERIC_CREDENTIAL_FORBIDDEN"):
            binding.read_bound_credentials(result, {"BINANCE_API_KEY": "generic-key", "BINANCE_API_SECRET": "generic-secret"})

    def test_T13_sidecar_rejects_live_rest_override(self):
        with self.assertRaisesRegex(binding.CredentialBindingError, "REST_ENDPOINT_MISMATCH"):
            self.resolve("DEMO", "TESTNET_USER_DATA", binding.LIVE_REST_BASE, binding.DEMO_USER_STREAM_TEMPLATE)

    def test_T14_sidecar_rejects_live_private_ws_override(self):
        with self.assertRaisesRegex(binding.CredentialBindingError, "PRIVATE_WS_ENDPOINT_MISMATCH"):
            self.resolve("DEMO", "TESTNET_USER_DATA", binding.DEMO_REST_BASE, binding.LIVE_USER_STREAM_TEMPLATE)

    def test_T15_gateway_rejects_environment_endpoint_profile_mismatch(self):
        with self.assertRaisesRegex(binding.CredentialBindingError, "REST_ENDPOINT_MISMATCH"):
            self.resolve("DEMO", "TESTNET_SIGNED_READONLY", binding.LIVE_REST_BASE)

    def test_T16_unknown_endpoint_rejected(self):
        with self.assertRaisesRegex(binding.CredentialBindingError, "REST_ENDPOINT_MISMATCH"):
            self.resolve("LIVE", "LIVE_SIGNED_READONLY", "https://unknown.invalid")

    def test_T17_missing_environment_rejected(self):
        with self.assertRaisesRegex(binding.CredentialBindingError, "ENVIRONMENT_REQUIRED"):
            self.resolve(None, "LIVE_SIGNED_READONLY", binding.LIVE_REST_BASE)

    def test_T18_testnet_secret_sentinel_never_in_diagnostic(self):
        diagnostic = binding.safe_diagnostic(
            environment="DEMO", profile="TESTNET_SIGNED_READONLY",
            reason_code="REQUEST_FAILED", exception=RuntimeError("TESTNET_SECRET_SENTINEL"),
        )
        self.assertNotIn("TESTNET_SECRET_SENTINEL", diagnostic)
        self.assertIn("RuntimeError", diagnostic)

    def test_T19_live_secret_sentinel_never_in_diagnostic(self):
        diagnostic = binding.safe_diagnostic(
            environment="LIVE", profile="LIVE_SIGNED_READONLY",
            reason_code="REQUEST_FAILED", exception=RuntimeError("LIVE_SECRET_SENTINEL"),
        )
        self.assertNotIn("LIVE_SECRET_SENTINEL", diagnostic)
        self.assertIn("RuntimeError", diagnostic)

    def test_T20_binding_preserves_distinct_backing_names(self):
        demo = self.resolve("DEMO", "TESTNET_SIGNED_READONLY", binding.DEMO_REST_BASE)
        live = self.resolve("LIVE", "LIVE_SIGNED_READONLY", binding.LIVE_REST_BASE)
        self.assertTrue(set(demo.credential_names).isdisjoint(live.credential_names))

    def test_T21_demo_template_is_exact(self):
        self.assertEqual(binding.DEMO_USER_STREAM_TEMPLATE, "wss://fstream.binancefuture.com/private/ws?listenKey={listenKey}&events=ORDER_TRADE_UPDATE/ACCOUNT_UPDATE")

    def test_T22_live_template_is_exact(self):
        self.assertEqual(binding.LIVE_USER_STREAM_TEMPLATE, "wss://fstream.binance.com/private/ws?listenKey={listenKey}&events=ORDER_TRADE_UPDATE/ACCOUNT_UPDATE")

    def test_T23_event_order_is_exact(self):
        self.assertTrue(binding.DEMO_USER_STREAM_TEMPLATE.endswith("events=ORDER_TRADE_UPDATE/ACCOUNT_UPDATE"))
        self.assertTrue(binding.LIVE_USER_STREAM_TEMPLATE.endswith("events=ORDER_TRADE_UPDATE/ACCOUNT_UPDATE"))

    def test_T24_listen_key_expired_remains_stream_control(self):
        authority = user_data.Authority(
            status_path=Path("unused-status.json"),
            order_dir=Path("unused-orders"),
            journal=Path("unused-journal.jsonl"),
            account_snapshot=Path("unused-account.json"),
            position_dir=Path("unused-positions"),
            max_liveness_ms=15000,
        )
        authority.publish = lambda at_ms=None: None
        authority.process({"e": "listenKeyExpired", "E": 1000}, 1001)
        self.assertTrue(authority.expired)
        self.assertEqual(authority.expired_count, 1)
        self.assertNotIn("listenKeyExpired", binding.DEMO_USER_STREAM_TEMPLATE)


if __name__ == "__main__":
    unittest.main()
