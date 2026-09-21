from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
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
        self.pid_patch.start()
        self.lock_patch.start()

    def tearDown(self) -> None:
        self.lock_patch.stop()
        self.pid_patch.stop()
        self.temp.cleanup()

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
            "DATABASE_PASSWORD": "password",
        }
        with mock.patch.dict(launcher.os.environ, parent, clear=True):
            child = launcher.sanitized_child_environment()
        self.assertEqual(child["PATH"], "safe-path")
        self.assertEqual(child["PYTHONUNBUFFERED"], "1")
        self.assertNotIn("BINANCE_API_KEY", child)
        self.assertNotIn("BINANCE_API_SECRET", child)
        self.assertNotIn("ASTU_PRIVATE_TOKEN", child)
        self.assertNotIn("DATABASE_PASSWORD", child)

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


if __name__ == "__main__":
    unittest.main()
