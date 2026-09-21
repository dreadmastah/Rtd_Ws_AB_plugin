from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest import mock

import autostart_manager
import stack_launcher


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


def subprocess_create_no_window() -> int:
    return stack_launcher.subprocess.CREATE_NO_WINDOW


if __name__ == "__main__":
    unittest.main()
