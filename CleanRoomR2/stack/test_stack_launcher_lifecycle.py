from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import autostart_manager
import stack_launcher


def process_record(
    pid: int,
    created: int,
    executable: str = "python.exe",
) -> dict[str, object]:
    return {
        "pid": pid,
        "creationTime100ns": created,
        "executable": os.path.abspath(executable),
    }


class InstanceLockTests(unittest.TestCase):
    def test_identity_is_database_case_insensitive_and_port_scoped(self) -> None:
        self.assertEqual(
            stack_launcher.instance_lock_identity("WSRTD", 10101),
            stack_launcher.instance_lock_identity("wsrtd", 10101),
        )
        self.assertNotEqual(
            stack_launcher.instance_lock_identity("WSRTD", 10101),
            stack_launcher.instance_lock_identity("WSRTD", 10102),
        )

    def test_second_owner_is_rejected_and_release_allows_restart(self) -> None:
        first = stack_launcher.InstanceLock("WSRTD_LIFECYCLE_TEST", 19101)
        second = stack_launcher.InstanceLock("WSRTD_LIFECYCLE_TEST", 19101)
        third = stack_launcher.InstanceLock("WSRTD_LIFECYCLE_TEST", 19101)
        self.assertTrue(first.acquire())
        try:
            self.assertFalse(second.acquire())
        finally:
            first.release()
        self.assertTrue(third.acquire())
        third.release()

    def test_stop_request_is_pair_scoped(self) -> None:
        self.assertEqual(
            stack_launcher.stop_request_path("WSRTD", 10101),
            stack_launcher.stop_request_path("wsrtd", 10101),
        )
        self.assertNotEqual(
            stack_launcher.stop_request_path("WSRTD", 10101),
            stack_launcher.stop_request_path("WSRTD", 10102),
        )

    def test_autostart_command_binds_database_and_port(self) -> None:
        command = autostart_manager.ensure_command("WSRTD", 10101)
        self.assertIn(".venv", command)
        self.assertIn("stack_launcher.py", command)
        self.assertIn("--dbname WSRTD", command)
        self.assertIn("--relay-port 10101", command)


class HiddenTasklistTests(unittest.TestCase):
    @mock.patch.object(stack_launcher.subprocess, "run")
    def test_process_name_running_uses_hidden_tasklist_and_preserves_semantics(
        self, run: mock.Mock
    ) -> None:
        run.side_effect = [
            SimpleNamespace(stdout='"Broker.exe","1234"\n'),
            SimpleNamespace(stdout="INFO: No tasks are running"),
        ]

        self.assertTrue(stack_launcher.process_name_running("Broker.exe"))
        self.assertFalse(stack_launcher.process_name_running("Broker.exe"))

        for call in run.call_args_list:
            self.assertEqual(
                call.args[0],
                ["tasklist", "/FI", "IMAGENAME eq Broker.exe", "/FO", "CSV", "/NH"],
            )
            self.assertEqual(
                call.kwargs["creationflags"], subprocess_create_no_window(),
            )

    @mock.patch.object(stack_launcher.subprocess, "run")
    def test_pid_alive_uses_hidden_tasklist_and_preserves_semantics(
        self, run: mock.Mock
    ) -> None:
        run.side_effect = [
            SimpleNamespace(stdout='"pythonw.exe","4321"\n'),
            SimpleNamespace(stdout="INFO: No tasks are running"),
        ]

        self.assertTrue(stack_launcher.pid_alive(4321))
        self.assertFalse(stack_launcher.pid_alive(4321))

        for call in run.call_args_list:
            self.assertEqual(
                call.args[0],
                ["tasklist", "/FI", "PID eq 4321", "/FO", "CSV", "/NH"],
            )
            self.assertEqual(
                call.kwargs["creationflags"], subprocess_create_no_window(),
            )

    def test_non_windows_paths_do_not_use_windows_subprocess_flags(self) -> None:
        with mock.patch.object(stack_launcher.os, "name", "posix"), mock.patch.object(
            stack_launcher.subprocess, "run"
        ) as run, mock.patch.object(stack_launcher.os, "kill") as kill:
            self.assertEqual(stack_launcher.windows_hidden_flags(), 0)
            self.assertFalse(stack_launcher.process_name_running("Broker.exe"))
            self.assertTrue(stack_launcher.pid_alive(4321))
            run.assert_not_called()
            kill.assert_called_once_with(4321, 0)


class SecretIsolationTests(unittest.TestCase):
    def test_wsrtd_children_do_not_inherit_private_credentials(self) -> None:
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
        with mock.patch.dict(os.environ, parent, clear=True):
            child = stack_launcher.sanitized_child_environment({
                "WSRTD_RELAY_PORT": "10101",
            })
        self.assertEqual(child["PATH"], "safe-path")
        self.assertEqual(child["WSRTD_RELAY_PORT"], "10101")
        self.assertNotIn("BINANCE_API_KEY", child)
        self.assertNotIn("BINANCE_API_SECRET", child)
        self.assertNotIn("ASTU_PRIVATE_TOKEN", child)
        self.assertNotIn("ASTU_SURPRISE_ACCESS_TOKEN", child)
        self.assertNotIn("NPM_TOKEN", child)
        self.assertNotIn("SENTRY_TOKEN", child)
        self.assertNotIn("CUSTOM_TOKEN", child)
        self.assertNotIn("DATABASE_PASSWORD", child)
        self.assertEqual(child["TOKENIZERS_PARALLELISM"], "true")

    def test_actual_wsrtd_child_environments_are_secret_free(self) -> None:
        parent = {
            "PATH": "safe-path",
            "ASTU_BINANCE_TESTNET_API_KEY": "key",
            "ASTU_BINANCE_TESTNET_API_SECRET": "secret",
            "ASTU_SURPRISE_AUTH_TOKEN": "token",
            "NPM_TOKEN": "npm",
            "SENTRY_TOKEN": "sentry",
            "CUSTOM_SERVICE_TOKEN": "custom",
            "TOKENIZERS_PARALLELISM": "true",
        }
        with (
            mock.patch.dict(os.environ, parent, clear=True),
            mock.patch.object(stack_launcher.subprocess, "Popen") as popen,
        ):
            for role in ("relay", "server", "identity"):
                popen.reset_mock()
                stack_launcher.popen_with_sanitized_environment(
                    [role],
                    env_overrides={"WSRTD_RELAY_PORT": "10101"},
                )
                env = popen.call_args.kwargs["env"]
                self.assertEqual(env["PATH"], "safe-path")
                self.assertEqual(env["WSRTD_RELAY_PORT"], "10101")
                self.assertEqual(env["TOKENIZERS_PARALLELISM"], "true")
                self.assertNotIn("ASTU_BINANCE_TESTNET_API_KEY", env, role)
                self.assertNotIn("ASTU_BINANCE_TESTNET_API_SECRET", env, role)
                self.assertNotIn("ASTU_SURPRISE_AUTH_TOKEN", env, role)
                self.assertNotIn("NPM_TOKEN", env, role)
                self.assertNotIn("SENTRY_TOKEN", env, role)
                self.assertNotIn("CUSTOM_SERVICE_TOKEN", env, role)


class LauncherOwnershipTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.pid_patch = mock.patch.object(
            stack_launcher,
            "PIDFILE",
            Path(self.temp.name) / "stack_pids.json",
        )
        self.pid_patch.start()
        self.pause_patch = mock.patch.object(
            stack_launcher, "PAUSEFILE", Path(self.temp.name) / "pause"
        )
        self.pause_patch.start()

    def tearDown(self) -> None:
        self.pause_patch.stop()
        self.pid_patch.stop()
        self.temp.cleanup()

    def write_state(
        self,
        launcher_record: dict[str, object],
        **children: dict[str, object],
    ) -> None:
        stack_launcher.PIDFILE.write_text(
            json.dumps({
                "schemaVersion": stack_launcher.PID_SCHEMA_VERSION,
                "launchNonce": "owner",
                "processes": {"launcher": launcher_record, **children},
                "launcher": launcher_record["pid"],
                **{name: child["pid"] for name, child in children.items()},
            }),
            encoding="utf-8",
        )

    def assert_live_child_refuses_recovery(self, child_name: str) -> None:
        stale_launcher = process_record(41, 100)
        live_child = process_record(42, 200)
        self.write_state(stale_launcher, **{child_name: live_child})
        with (
            mock.patch.object(
                stack_launcher,
                "process_identity",
                side_effect=lambda pid: live_child if pid == 42 else None,
            ),
            mock.patch.object(
                stack_launcher,
                "pid_alive",
                side_effect=lambda pid: pid == 42,
            ),
            mock.patch.object(stack_launcher, "InstanceLock") as lock,
        ):
            ownership, acquired = stack_launcher.claim_launcher_ownership(
                "WSRTD_TEST",
                19102,
            )
            lock.assert_not_called()
        self.assertEqual(
            ownership,
            stack_launcher.LAUNCH_OWNERSHIP_LIVE_AMBIGUOUS,
        )
        self.assertIsNone(acquired)
        self.assertTrue(stack_launcher.PIDFILE.exists())

    def assert_live_child_refuses_ensure_running(self, child_name: str) -> None:
        stale_launcher = process_record(41, 100)
        live_child = process_record(42, 200)
        self.write_state(stale_launcher, **{child_name: live_child})
        with (
            mock.patch.object(
                stack_launcher,
                "process_identity",
                side_effect=lambda pid: live_child if pid == 42 else None,
            ),
            mock.patch.object(
                stack_launcher,
                "pid_alive",
                side_effect=lambda pid: pid == 42,
            ),
            mock.patch.object(stack_launcher, "instance_running") as running,
            mock.patch.object(stack_launcher, "configure_registry") as configure,
            mock.patch.object(stack_launcher, "popen_with_sanitized_environment") as popen,
        ):
            result = stack_launcher.ensure_running("WSRTD_TEST", 19102)
            running.assert_not_called()
            configure.assert_not_called()
            popen.assert_not_called()
        self.assertEqual(result, 4)
        self.assertTrue(stack_launcher.PIDFILE.exists())

    def test_dead_launcher_with_live_relay_refuses_recovery(self) -> None:
        self.assert_live_child_refuses_recovery("relay")

    def test_dead_launcher_with_live_server_refuses_recovery(self) -> None:
        self.assert_live_child_refuses_recovery("server")

    def test_dead_launcher_with_live_identity_refuses_recovery(self) -> None:
        self.assert_live_child_refuses_recovery("identity")

    def test_live_relay_refuses_ensure_running(self) -> None:
        self.assert_live_child_refuses_ensure_running("relay")

    def test_live_server_refuses_ensure_running(self) -> None:
        self.assert_live_child_refuses_ensure_running("server")

    def test_live_identity_refuses_ensure_running(self) -> None:
        self.assert_live_child_refuses_ensure_running("identity")

    def test_all_children_dead_allow_ensure_running_recovery(self) -> None:
        self.write_state(
            process_record(41, 100),
            relay=process_record(42, 101),
            server=process_record(43, 102),
            identity=process_record(44, 103),
        )
        spawned = SimpleNamespace(pid=99)
        with (
            mock.patch.object(stack_launcher, "process_identity", return_value=None),
            mock.patch.object(stack_launcher, "pid_alive", return_value=False),
            mock.patch.object(stack_launcher, "instance_running", return_value=False),
            mock.patch.object(stack_launcher, "configure_registry", return_value=True),
            mock.patch.object(
                stack_launcher,
                "popen_with_sanitized_environment",
                return_value=spawned,
            ) as popen,
        ):
            result = stack_launcher.ensure_running("WSRTD_TEST", 19102)
        self.assertEqual(result, 0)
        # Only the supervisor may replace stale state under exclusive ownership.
        self.assertTrue(stack_launcher.PIDFILE.exists())
        popen.assert_called_once()

    def test_interleaved_ensure_preserves_winning_supervisor_state(self) -> None:
        self.write_state(process_record(41, 100), relay=process_record(42, 101))
        old_bytes = stack_launcher.PIDFILE.read_bytes()
        real_adjudicate = stack_launcher.adjudicate_pid_state
        barrier = threading.Barrier(2)
        winner_published = threading.Event()
        owner = process_record(99, 300)
        relay = process_record(100, 301)
        server = process_record(101, 302)
        identities = {}
        winning_bytes = []
        acquired_locks = []

        def adjudicate():
            result = real_adjudicate()
            barrier.wait(timeout=5)
            return result

        def spawn(*args, **kwargs):
            # Both real ensure callers saw stale state. Their supervisor
            # candidates still use the production ownership adjudication.
            with mock.patch.object(stack_launcher, "adjudicate_pid_state", real_adjudicate):
                result, lock = stack_launcher.claim_launcher_ownership(
                    "WSRTD_RACE_TEST", 19107
                )
            if result == stack_launcher.LAUNCH_OWNERSHIP_ACQUIRED:
                acquired_locks.append(lock)
                identities.update({99: owner, 100: relay, 101: server})
                self.write_state(owner, relay=relay, server=server)
                winning_bytes.append(stack_launcher.PIDFILE.read_bytes())
                winner_published.set()
            return SimpleNamespace(pid=99)

        probe_lock = threading.Lock()
        probes = []
        def probe(*args):
            with probe_lock:
                probes.append(True)
                first = len(probes) == 1
            if not first:
                self.assertTrue(winner_published.wait(5))
            # Reproduce a stale probe result for the resumed caller.
            return False

        with (
            mock.patch.object(stack_launcher, "adjudicate_pid_state", adjudicate),
            mock.patch.object(stack_launcher, "process_identity",
                              side_effect=lambda pid: identities.get(pid)),
            mock.patch.object(stack_launcher, "pid_alive",
                              side_effect=lambda pid: pid in identities),
            mock.patch.object(stack_launcher, "instance_running", side_effect=probe),
            mock.patch.object(stack_launcher, "configure_registry", return_value=True),
            mock.patch.object(stack_launcher, "popen_with_sanitized_environment",
                              side_effect=spawn),
            mock.patch.dict(stack_launcher.CFG, {"identity_bridge": {"enabled": False}}),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            try:
                results = list(pool.map(
                    lambda _: stack_launcher.ensure_running("WSRTD_RACE_TEST", 19107),
                    range(2),
                ))
                self.assertEqual(results, [0, 0])
                self.assertEqual(len(acquired_locks), 1)
                self.assertNotEqual(old_bytes, winning_bytes[0])
                self.assertEqual(stack_launcher.PIDFILE.read_bytes(), winning_bytes[0])
                self.assertEqual(stack_launcher.status_from_pidfile(), 0)
            finally:
                for lock in acquired_locks:
                    lock.release()

    def test_dead_launcher_and_all_dead_children_allow_recovery(self) -> None:
        self.write_state(
            process_record(41, 100),
            relay=process_record(42, 101),
            server=process_record(43, 102),
            identity=process_record(44, 103),
            additional=process_record(45, 104),
        )
        with (
            mock.patch.object(stack_launcher, "process_identity", return_value=None),
            mock.patch.object(stack_launcher, "pid_alive", return_value=False),
            mock.patch.object(stack_launcher, "InstanceLock") as lock,
        ):
            lock.return_value.acquire.return_value = True
            ownership, acquired = stack_launcher.claim_launcher_ownership(
                "WSRTD_TEST",
                19102,
            )
        self.assertEqual(ownership, stack_launcher.LAUNCH_OWNERSHIP_ACQUIRED)
        self.assertIs(acquired, lock.return_value)

    def test_invalid_identity_state_refuses_recovery(self) -> None:
        stack_launcher.PIDFILE.write_text(
            json.dumps({
                "schemaVersion": stack_launcher.PID_SCHEMA_VERSION,
                "launchNonce": "owner",
                "processes": {"relay": process_record(42, 101)},
            }),
            encoding="utf-8",
        )
        with mock.patch.object(stack_launcher, "InstanceLock") as lock:
            ownership, acquired = stack_launcher.claim_launcher_ownership(
                "WSRTD_TEST",
                19102,
            )
            lock.assert_not_called()
        self.assertEqual(
            ownership,
            stack_launcher.LAUNCH_OWNERSHIP_LIVE_AMBIGUOUS,
        )
        self.assertIsNone(acquired)

    def test_concurrent_stale_recovery_has_exactly_one_owner(self) -> None:
        self.write_state(
            process_record(41, 100),
            relay=process_record(42, 101),
        )
        acquire_barrier = threading.Barrier(2)

        class ContendedLock:
            guard = threading.Lock()
            held = False

            def __init__(self, dbname: str, relay_port: int) -> None:
                self.identity = f"{dbname}:{relay_port}"

            def acquire(self) -> bool:
                acquire_barrier.wait()
                with self.guard:
                    if self.held:
                        return False
                    type(self).held = True
                    return True

            def release(self) -> None:
                with self.guard:
                    type(self).held = False

        with (
            mock.patch.object(stack_launcher, "process_identity", return_value=None),
            mock.patch.object(stack_launcher, "pid_alive", return_value=False),
            mock.patch.object(stack_launcher, "InstanceLock", ContendedLock),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            results = list(pool.map(
                lambda _: stack_launcher.claim_launcher_ownership(
                    "WSRTD_CONCURRENT_TEST",
                    19103,
                ),
                range(2),
            ))
        winners = [
            lock
            for ownership, lock in results
            if ownership == stack_launcher.LAUNCH_OWNERSHIP_ACQUIRED
        ]
        self.assertEqual(len(winners), 1)
        self.assertEqual(
            sum(
                ownership == stack_launcher.LAUNCH_OWNERSHIP_ALREADY_RUNNING
                for ownership, _lock in results
            ),
            1,
        )
        winners[0].release()


def subprocess_create_no_window() -> int:
    return stack_launcher.subprocess.CREATE_NO_WINDOW


if __name__ == "__main__":
    unittest.main()
