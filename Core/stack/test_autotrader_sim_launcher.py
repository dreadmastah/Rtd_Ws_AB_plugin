from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("autotrader_sim_launcher.py")
SPEC = importlib.util.spec_from_file_location("autotrader_sim_launcher", MODULE_PATH)
assert SPEC and SPEC.loader
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


def record(pid: int, created: int, executable: str = "python.exe") -> dict[str, object]:
    return {
        "pid": pid,
        "creationTime100ns": created,
        "executable": os.path.abspath(executable),
    }


class LauncherOwnershipTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.pid_patch = mock.patch.object(launcher, "PID_FILE", root / "pids.json")
        self.lock_patch = mock.patch.object(launcher, "LOCK_FILE", root / "lock.json")
        self.claim_patch = mock.patch.object(launcher, "CLAIM_FILE", root / "claim.json")
        self.pid_patch.start()
        self.lock_patch.start()
        self.claim_patch.start()

    def tearDown(self) -> None:
        self.claim_patch.stop()
        self.lock_patch.stop()
        self.pid_patch.stop()
        self.temp.cleanup()

    def write_state(
        self,
        owner: dict[str, object],
        nonce: str = "owner",
        **children: dict[str, object],
    ) -> None:
        launcher.PID_FILE.write_text(
            json.dumps({
                "schemaVersion": launcher.PID_SCHEMA_VERSION,
                "launchNonce": nonce,
                "processes": {"launcher": owner, **children},
            }),
            encoding="utf-8",
        )

    def assert_live_owner_refused(self, owner: dict[str, object]) -> None:
        with (
            mock.patch.object(
                launcher,
                "process_identity",
                side_effect=lambda pid: owner if pid == owner["pid"] else None,
            ),
            mock.patch.object(launcher, "acquire_launch_lock") as acquire,
        ):
            result = launcher.claim_launcher_ownership(
                "contender",
                record(99, 300),
            )
            acquire.assert_not_called()
        self.assertEqual(result, launcher.LAUNCH_OWNERSHIP_LIVE_AMBIGUOUS)
        self.assertTrue(launcher.PID_FILE.exists())

    def test_pid_reuse_does_not_match_recorded_owner(self) -> None:
        with mock.patch.object(
            launcher,
            "process_identity",
            return_value=record(41, 200),
        ):
            self.assertFalse(launcher.process_record_matches(record(41, 100)))

    def test_stale_pid_file_reports_degraded(self) -> None:
        expected = record(41, 100)
        launcher.PID_FILE.write_text(
            json.dumps({
                "schemaVersion": launcher.PID_SCHEMA_VERSION,
                "launchNonce": "stale",
                "processes": {"launcher": expected},
            }),
            encoding="utf-8",
        )
        launcher.LOCK_FILE.write_text(
            json.dumps({
                "schemaVersion": launcher.PID_SCHEMA_VERSION,
                "launchNonce": "stale",
                "launcher": expected,
            }),
            encoding="utf-8",
        )
        with mock.patch.object(launcher, "process_identity", return_value=None):
            self.assertEqual(launcher.status(), 1)

    def test_stale_lock_is_reclaimed(self) -> None:
        launcher.LOCK_FILE.write_text(
            json.dumps({
                "schemaVersion": launcher.PID_SCHEMA_VERSION,
                "launchNonce": "stale",
                "launcher": record(41, 100),
            }),
            encoding="utf-8",
        )
        with mock.patch.object(
            launcher,
            "process_identity",
            return_value=record(41, 200),
        ):
            self.assertTrue(
                launcher.acquire_launch_lock("fresh", record(99, 300))
            )
        lock = json.loads(launcher.LOCK_FILE.read_text(encoding="utf-8"))
        self.assertEqual(lock["launchNonce"], "fresh")

    def test_live_pid_with_missing_lock_is_refused(self) -> None:
        owner = record(41, 100)
        self.write_state(owner)
        self.assert_live_owner_refused(owner)
        self.assertFalse(launcher.LOCK_FILE.exists())

    @unittest.skipUnless(os.name == "nt", "run() integration requires Windows")
    def test_run_starts_no_children_for_ambiguous_live_owner(self) -> None:
        owner = record(41, 100)
        self.write_state(owner)
        root = Path(self.temp.name)
        host = root / "host.exe"
        host.touch()
        status_dir = root / "status"
        status_dir.mkdir()
        with mock.patch.object(
            launcher.sys,
            "argv",
            ["launcher", "--host", str(host), "--status-dir", str(status_dir)],
        ):
            args = launcher.parse_args()
        current = record(os.getpid(), 900)
        with (
            mock.patch.object(
                launcher,
                "process_identity",
                side_effect=lambda pid: {41: owner, os.getpid(): current}.get(pid),
            ),
            mock.patch.object(launcher.signal, "signal"),
            mock.patch.object(launcher.subprocess, "Popen") as popen,
        ):
            self.assertEqual(launcher.run(args), 5)
            popen.assert_not_called()
        self.assertTrue(launcher.PID_FILE.exists())
        self.assertFalse(launcher.LOCK_FILE.exists())

    def test_corrupt_pid_state_is_refused(self) -> None:
        launcher.PID_FILE.write_text("{corrupt", encoding="utf-8")
        with mock.patch.object(launcher, "acquire_launch_lock") as acquire:
            result = launcher.claim_launcher_ownership(
                "contender",
                record(99, 300),
            )
            acquire.assert_not_called()
        self.assertEqual(result, launcher.LAUNCH_OWNERSHIP_LIVE_AMBIGUOUS)
        self.assertEqual(
            launcher.PID_FILE.read_text(encoding="utf-8"),
            "{corrupt",
        )

    def test_live_pid_with_corrupt_lock_is_refused(self) -> None:
        owner = record(41, 100)
        self.write_state(owner)
        launcher.LOCK_FILE.write_text("{corrupt", encoding="utf-8")
        self.assert_live_owner_refused(owner)
        self.assertEqual(
            launcher.LOCK_FILE.read_text(encoding="utf-8"),
            "{corrupt",
        )

    def test_live_pid_with_nonce_mismatched_lock_is_refused(self) -> None:
        owner = record(41, 100)
        self.write_state(owner)
        mismatched = {
            "schemaVersion": launcher.PID_SCHEMA_VERSION,
            "launchNonce": "different",
            "launcher": owner,
        }
        launcher.LOCK_FILE.write_text(json.dumps(mismatched), encoding="utf-8")
        self.assert_live_owner_refused(owner)
        self.assertEqual(
            json.loads(launcher.LOCK_FILE.read_text(encoding="utf-8")),
            mismatched,
        )

    def test_live_pid_with_identity_mismatched_lock_is_refused(self) -> None:
        owner = record(41, 100)
        other = record(77, 700)
        self.write_state(owner)
        mismatched = {
            "schemaVersion": launcher.PID_SCHEMA_VERSION,
            "launchNonce": "owner",
            "launcher": other,
        }
        launcher.LOCK_FILE.write_text(json.dumps(mismatched), encoding="utf-8")
        with (
            mock.patch.object(
                launcher,
                "process_identity",
                side_effect=lambda pid: {41: owner, 77: other}.get(pid),
            ),
            mock.patch.object(launcher, "acquire_launch_lock") as acquire,
        ):
            result = launcher.claim_launcher_ownership(
                "contender",
                record(99, 300),
            )
            acquire.assert_not_called()
        self.assertEqual(result, launcher.LAUNCH_OWNERSHIP_LIVE_AMBIGUOUS)
        self.assertTrue(launcher.PID_FILE.exists())
        self.assertEqual(
            json.loads(launcher.LOCK_FILE.read_text(encoding="utf-8")),
            mismatched,
        )

    def test_dead_launcher_and_all_dead_children_are_reclaimed(self) -> None:
        stale = record(41, 100)
        self.write_state(
            stale,
            nonce="stale",
            relay=record(42, 101),
            server=record(43, 102),
            risk=record(44, 103),
        )
        launcher.LOCK_FILE.write_text(
            json.dumps({
                "schemaVersion": launcher.PID_SCHEMA_VERSION,
                "launchNonce": "stale",
                "launcher": stale,
            }),
            encoding="utf-8",
        )
        with (
            mock.patch.object(launcher, "process_identity", return_value=None),
            mock.patch.object(launcher, "pid_exists", return_value=False),
        ):
            result = launcher.claim_launcher_ownership(
                "fresh",
                record(99, 300),
            )
        self.assertEqual(result, launcher.LAUNCH_OWNERSHIP_ACQUIRED)
        self.assertFalse(launcher.PID_FILE.exists())
        lock = json.loads(launcher.LOCK_FILE.read_text(encoding="utf-8"))
        self.assertEqual(lock["launchNonce"], "fresh")

    def test_dead_launcher_with_live_child_refuses_recovery(self) -> None:
        stale_launcher = record(41, 100)
        live_relay = record(42, 200)
        self.write_state(stale_launcher, relay=live_relay)
        with (
            mock.patch.object(
                launcher,
                "process_identity",
                side_effect=lambda pid: live_relay if pid == 42 else None,
            ),
            mock.patch.object(
                launcher,
                "pid_exists",
                side_effect=lambda pid: pid == 42,
            ),
            mock.patch.object(launcher, "acquire_launch_lock") as acquire,
        ):
            result = launcher.claim_launcher_ownership(
                "fresh",
                record(99, 300),
            )
            acquire.assert_not_called()
        self.assertEqual(result, launcher.LAUNCH_OWNERSHIP_LIVE_AMBIGUOUS)
        self.assertTrue(launcher.PID_FILE.exists())
        self.assertFalse(launcher.LOCK_FILE.exists())

    def test_dead_launcher_with_live_identity_bridge_refuses_recovery(self) -> None:
        stale_launcher = record(41, 100)
        live_identity = record(45, 205)
        self.write_state(stale_launcher, identity=live_identity)
        with (
            mock.patch.object(
                launcher,
                "process_identity",
                side_effect=lambda pid: live_identity if pid == 45 else None,
            ),
            mock.patch.object(
                launcher,
                "pid_exists",
                side_effect=lambda pid: pid == 45,
            ),
        ):
            result = launcher.claim_launcher_ownership(
                "fresh",
                record(99, 300),
            )
        self.assertEqual(result, launcher.LAUNCH_OWNERSHIP_LIVE_AMBIGUOUS)
        self.assertTrue(launcher.PID_FILE.exists())

    def test_dead_launcher_with_live_server_refuses_recovery(self) -> None:
        stale_launcher = record(41, 100)
        live_server = record(43, 203)
        self.write_state(stale_launcher, server=live_server)
        with (
            mock.patch.object(
                launcher,
                "process_identity",
                side_effect=lambda pid: live_server if pid == 43 else None,
            ),
            mock.patch.object(
                launcher,
                "pid_exists",
                side_effect=lambda pid: pid == 43,
            ),
            mock.patch.object(launcher, "acquire_launch_lock") as acquire,
        ):
            result = launcher.claim_launcher_ownership(
                "fresh",
                record(99, 300),
            )
            acquire.assert_not_called()
        self.assertEqual(result, launcher.LAUNCH_OWNERSHIP_LIVE_AMBIGUOUS)
        self.assertTrue(launcher.PID_FILE.exists())

    def test_concurrent_stale_recovery_has_exactly_one_owner(self) -> None:
        stale_launcher = record(41, 100)
        stale_child = record(42, 101)
        first = record(77, 700)
        self.write_state(stale_launcher, relay=stale_child)
        with (
            mock.patch.object(
                launcher,
                "process_identity",
                side_effect=lambda pid: first if pid == 77 else None,
            ),
            mock.patch.object(launcher, "pid_exists", return_value=False),
        ):
            self.assertEqual(
                launcher.claim_launcher_ownership("first", first),
                launcher.LAUNCH_OWNERSHIP_ACQUIRED,
            )
            self.assertEqual(
                launcher.claim_launcher_ownership("second", record(88, 800)),
                launcher.LAUNCH_OWNERSHIP_ALREADY_RUNNING,
            )

    def test_simultaneous_claim_guards_have_exactly_one_winner(self) -> None:
        first = record(77, 700)
        second = record(88, 800)
        identities = {77: first, 88: second}
        barrier = threading.Barrier(2)

        def contend(nonce: str, owner: dict[str, object]) -> bool:
            barrier.wait()
            return launcher.acquire_claim_guard(nonce, owner)

        with (
            mock.patch.object(
                launcher,
                "process_identity",
                side_effect=lambda pid: identities.get(pid),
            ),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            outcomes = list(pool.map(
                lambda item: contend(*item),
                (("first", first), ("second", second)),
            ))
        self.assertEqual(sum(outcomes), 1)

    def test_concurrent_launcher_cannot_replace_owned_lock(self) -> None:
        owned = record(41, 100)
        launcher.LOCK_FILE.write_text(
            json.dumps({
                "schemaVersion": launcher.PID_SCHEMA_VERSION,
                "launchNonce": "owner",
                "launcher": owned,
            }),
            encoding="utf-8",
        )
        with mock.patch.object(launcher, "process_identity", return_value=owned):
            self.assertFalse(
                launcher.acquire_launch_lock("contender", record(99, 300))
            )
        lock = json.loads(launcher.LOCK_FILE.read_text(encoding="utf-8"))
        self.assertEqual(lock["launchNonce"], "owner")

    def test_live_owner_with_matching_lock_reports_already_running(self) -> None:
        owner = record(41, 100)
        self.write_state(owner)
        launcher.LOCK_FILE.write_text(
            json.dumps({
                "schemaVersion": launcher.PID_SCHEMA_VERSION,
                "launchNonce": "owner",
                "launcher": owner,
            }),
            encoding="utf-8",
        )
        with mock.patch.object(launcher, "process_identity", return_value=owner):
            self.assertEqual(
                launcher.claim_launcher_ownership("contender", record(99, 300)),
                launcher.LAUNCH_OWNERSHIP_ALREADY_RUNNING,
            )

    def test_concurrent_claims_have_exactly_one_owner(self) -> None:
        first = record(41, 100)
        with mock.patch.object(
            launcher,
            "process_identity",
            side_effect=lambda pid: first if pid == 41 else None,
        ):
            self.assertEqual(
                launcher.claim_launcher_ownership("first", first),
                launcher.LAUNCH_OWNERSHIP_ACQUIRED,
            )
            self.assertEqual(
                launcher.claim_launcher_ownership("second", record(77, 700)),
                launcher.LAUNCH_OWNERSHIP_ALREADY_RUNNING,
            )

    def test_partial_startup_persists_child_before_later_startup_crash(self) -> None:
        owner = record(41, 100)
        relay = record(42, 200)
        process_records = {"launcher": owner}
        launcher.save_pids(process_records, "owner")
        with mock.patch.object(launcher, "process_identity", return_value=relay):
            launcher.persist_owned_child(process_records, "relay", 42, "owner")

        state = json.loads(launcher.PID_FILE.read_text(encoding="utf-8"))
        self.assertEqual(state["processes"]["relay"], relay)
        self.assertFalse(state["startupComplete"])
        with (
            mock.patch.object(
                launcher,
                "process_identity",
                side_effect=lambda pid: relay if pid == 42 else None,
            ),
            mock.patch.object(
                launcher,
                "pid_exists",
                side_effect=lambda pid: pid == 42,
            ),
            mock.patch.object(launcher, "acquire_launch_lock") as acquire,
        ):
            result = launcher.claim_launcher_ownership(
                "contender",
                record(99, 300),
            )
            acquire.assert_not_called()
        self.assertEqual(result, launcher.LAUNCH_OWNERSHIP_LIVE_AMBIGUOUS)

    def test_persist_failure_stops_child_and_rolls_back_registration(self) -> None:
        owner = record(41, 100)
        child = record(42, 200)
        process_records = {"launcher": owner}
        launcher.save_pids(process_records, "owner")
        proc = mock.Mock(pid=42)
        proc.wait.return_value = 0
        with (
            mock.patch.object(launcher, "process_identity", return_value=child),
            mock.patch.object(
                launcher,
                "save_pids",
                side_effect=OSError("injected persistence failure"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "cannot persist ownership"):
                launcher.register_spawned_child(
                    process_records,
                    "relay",
                    proc,
                    "owner",
                )
        proc.terminate.assert_called_once_with()
        proc.wait.assert_called_once_with(timeout=5.0)
        proc.kill.assert_not_called()
        self.assertNotIn("relay", process_records)
        state = json.loads(launcher.PID_FILE.read_text(encoding="utf-8"))
        self.assertNotIn("relay", state["processes"])

    def test_crash_before_persist_cleanup_kills_unresponsive_child(self) -> None:
        owner = record(41, 100)
        process_records = {"launcher": owner}
        launcher.save_pids(process_records, "owner")
        proc = mock.Mock(pid=42)
        proc.wait.side_effect = [
            launcher.subprocess.TimeoutExpired("child", 5.0),
            0,
        ]
        with mock.patch.object(
            launcher,
            "persist_owned_child",
            side_effect=OSError("crash before persist"),
        ):
            with self.assertRaisesRegex(RuntimeError, "cannot persist ownership"):
                launcher.register_spawned_child(
                    process_records,
                    "relay",
                    proc,
                    "owner",
                )
        proc.terminate.assert_called_once_with()
        proc.kill.assert_called_once_with()
        self.assertEqual(proc.wait.call_count, 2)
        self.assertNotIn("relay", process_records)

    def test_partial_startup_state_is_not_reported_running(self) -> None:
        owner = record(41, 100)
        launcher.save_pids({"launcher": owner}, "owner")
        launcher.LOCK_FILE.write_text(
            json.dumps({
                "schemaVersion": launcher.PID_SCHEMA_VERSION,
                "launchNonce": "owner",
                "launcher": owner,
            }),
            encoding="utf-8",
        )
        with mock.patch.object(launcher, "process_identity", return_value=owner):
            self.assertEqual(launcher.status(), 1)

    def test_stop_refuses_wrong_process_without_taskkill(self) -> None:
        expected = record(41, 100)
        state = {
            "schemaVersion": launcher.PID_SCHEMA_VERSION,
            "launchNonce": "owner",
            "processes": {"launcher": expected},
        }
        lock = {
            "schemaVersion": launcher.PID_SCHEMA_VERSION,
            "launchNonce": "owner",
            "launcher": expected,
        }
        launcher.PID_FILE.write_text(json.dumps(state), encoding="utf-8")
        launcher.LOCK_FILE.write_text(json.dumps(lock), encoding="utf-8")
        with (
            mock.patch.object(
                launcher,
                "process_identity",
                return_value=record(41, 200),
            ),
            mock.patch.object(launcher.subprocess, "run") as run,
        ):
            self.assertEqual(launcher.stop(), 2)
            run.assert_not_called()


class ChildEnvironmentTests(unittest.TestCase):
    def test_secrets_are_removed_from_default_child_environment(self) -> None:
        parent = {
            "PATH": "safe-path",
            "BINANCE_API_KEY": "key",
            "BINANCE_API_SECRET": "secret",
            "ASTU_PRIVATE_TOKEN": "token",
            "ASTU_SURPRISE_ACCESS_TOKEN": "surprise",
            "NPM_TOKEN": "npm",
            "SENTRY_TOKEN": "sentry",
            "CUSTOM_TOKEN": "custom",
            "DATABASE_PASSWORD": "password",
            "TOKENIZERS_PARALLELISM": "true",
        }
        with mock.patch.dict(launcher.os.environ, parent, clear=True):
            child = launcher.sanitized_child_environment()
        self.assertEqual(child["PATH"], "safe-path")
        self.assertEqual(child["PYTHONUNBUFFERED"], "1")
        self.assertNotIn("BINANCE_API_KEY", child)
        self.assertNotIn("BINANCE_API_SECRET", child)
        self.assertNotIn("ASTU_PRIVATE_TOKEN", child)
        self.assertNotIn("ASTU_SURPRISE_ACCESS_TOKEN", child)
        self.assertNotIn("NPM_TOKEN", child)
        self.assertNotIn("SENTRY_TOKEN", child)
        self.assertNotIn("CUSTOM_TOKEN", child)
        self.assertNotIn("DATABASE_PASSWORD", child)
        self.assertEqual(child["TOKENIZERS_PARALLELISM"], "true")

    def test_only_explicit_secret_grants_reach_privileged_child(self) -> None:
        with mock.patch.dict(
            launcher.os.environ,
            {"PATH": "safe-path", "BINANCE_API_KEY": "parent-key"},
            clear=True,
        ):
            child = launcher.sanitized_child_environment(
                {"BINANCE_API_KEY": "granted-key"}
            )
        self.assertEqual(child["BINANCE_API_KEY"], "granted-key")

    def test_actual_popen_environments_follow_child_profiles(self) -> None:
        parent = {
            "PATH": "safe-path",
            "ASTU_BINANCE_PRIVATE_READONLY_ENABLED": "1",
            "BINANCE_API_KEY": "main-key",
            "BINANCE_API_SECRET": "main-secret",
            "ASTU_BINANCE_TESTNET_USER_DATA_ENABLED": "1",
            "ASTU_BINANCE_TESTNET_API_KEY": "demo-key",
            "ASTU_BINANCE_TESTNET_API_SECRET": "demo-secret",
            "ASTU_BINANCE_TESTNET_USER_STREAM_URL_TEMPLATE": "wss://example/{listenKey}",
            "ASTU_SURPRISE_AUTH_TOKEN": "must-not-leak",
            "NPM_TOKEN": "must-not-leak",
            "SENTRY_TOKEN": "must-not-leak",
            "CUSTOM_SERVICE_TOKEN": "must-not-leak",
            "TOKENIZERS_PARALLELISM": "true",
        }
        public_roles = (
            "instrument",
            "risk_fixture",
            "operator_view",
            "execution",
        )
        with (
            mock.patch.dict(launcher.os.environ, parent, clear=True),
            mock.patch.object(launcher.subprocess, "Popen") as popen,
        ):
            for role in public_roles:
                popen.reset_mock()
                launcher.popen_child_process(
                    [role],
                    stdout=launcher.subprocess.DEVNULL,
                    credential_profile=launcher.CREDENTIAL_PROFILE_NONE,
                )
                env = popen.call_args.kwargs["env"]
                self.assertNotIn("ASTU_BINANCE_TESTNET_API_KEY", env, role)
                self.assertNotIn("ASTU_BINANCE_TESTNET_API_SECRET", env, role)
                self.assertNotIn("BINANCE_API_KEY", env, role)
                self.assertNotIn("BINANCE_API_SECRET", env, role)
                self.assertNotIn("ASTU_SURPRISE_AUTH_TOKEN", env, role)
                self.assertNotIn("NPM_TOKEN", env, role)
                self.assertNotIn("SENTRY_TOKEN", env, role)
                self.assertNotIn("CUSTOM_SERVICE_TOKEN", env, role)
                self.assertEqual(env["TOKENIZERS_PARALLELISM"], "true")

            launcher.popen_child_process(
                ["user-data"],
                stdout=launcher.subprocess.DEVNULL,
                credential_profile=launcher.CREDENTIAL_PROFILE_TESTNET_USER_DATA,
            )
            user_data_env = popen.call_args.kwargs["env"]
            self.assertEqual(
                user_data_env["ASTU_BINANCE_TESTNET_API_KEY"],
                "demo-key",
            )
            self.assertNotIn("ASTU_BINANCE_TESTNET_API_SECRET", user_data_env)
            self.assertNotIn("NPM_TOKEN", user_data_env)
            self.assertNotIn("SENTRY_TOKEN", user_data_env)
            self.assertNotIn("CUSTOM_SERVICE_TOKEN", user_data_env)
            self.assertEqual(
                user_data_env["ASTU_BINANCE_TESTNET_USER_STREAM_URL_TEMPLATE"],
                "wss://example/{listenKey}",
            )

            launcher.popen_child_process(
                ["signed-risk"],
                stdout=launcher.subprocess.DEVNULL,
                credential_profile=launcher.CREDENTIAL_PROFILE_BINANCE_DEMO_SIGNED,
            )
            risk_env = popen.call_args.kwargs["env"]
            self.assertEqual(risk_env["BINANCE_API_KEY"], "demo-key")
            self.assertEqual(risk_env["BINANCE_API_SECRET"], "demo-secret")
            self.assertNotIn("ASTU_BINANCE_TESTNET_API_SECRET", risk_env)


if __name__ == "__main__":
    unittest.main()
