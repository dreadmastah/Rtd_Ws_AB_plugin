"""All stop operations use temporary runtime paths and fake process ownership."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import stack_launcher as launcher


class StopProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name, value in (("RUNTIME", self.root), ("PIDFILE", self.root / "pids.json"),
                            ("PAUSEFILE", self.root / "maintenance_pause")):
            patch = mock.patch.object(launcher, name, value)
            patch.start()
            self.addCleanup(patch.stop)

    def records(self):
        return [json.loads(line) for line in
                (self.root / "stop_provenance.jsonl").read_text().splitlines()]

    def test_no_stack_stop_is_audited_and_pause_blocks_recovery(self):
        self.assertEqual(launcher.stop_from_pidfile("Data", 10101, source="test-harness"), 0)
        record = self.records()[0]
        self.assertEqual(json.loads(launcher.PAUSEFILE.read_text()), record)
        self.assertEqual(record["requested_by_pid"], os.getpid())
        self.assertEqual(record["parentPid"], os.getppid())
        self.assertEqual(record["dbname"], "Data")
        self.assertEqual(record["sourceDeclared"], "test-harness")
        for field in ("timestampUtc", "reason", "executable", "commandLine", "username",
                      "instanceId", "instance_lock", "launcherPid", "childPids"):
            self.assertIn(field, record)
        with mock.patch.object(launcher, "popen_with_sanitized_environment") as spawn:
            self.assertEqual(launcher.ensure_running("Data", 10101), 0)
            spawn.assert_not_called()

    def test_request_and_pause_link_to_durable_record_before_stop(self):
        data = {"dbname": "Data", "relay_port": 10101, "launcher": 42,
                "relay": 43, "server": 44, "identity": 45, "amibroker": 46}
        launcher.PIDFILE.write_text(json.dumps(data))

        def dead(pid):
            self.assertEqual(pid, 42)
            record = self.records()[0]
            request = launcher.stop_request_path("Data", 10101)
            self.assertEqual(json.loads(request.read_text()), record)
            self.assertEqual(json.loads(launcher.PAUSEFILE.read_text()), record)
            self.assertEqual(record["childPids"]["server"], 44)
            return False

        with mock.patch.object(launcher, "pid_alive", side_effect=dead):
            self.assertEqual(launcher.stop_from_pidfile("Data", 10101, source="cmd-wrapper"), 0)
        self.assertTrue(launcher.PAUSEFILE.exists())
        self.assertFalse(launcher.stop_request_path("Data", 10101).exists())
        self.assertEqual(len(self.records()), 1)

    def test_audit_failure_does_not_pause_or_stop(self):
        with mock.patch.object(launcher, "append_stop_provenance", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                launcher.stop_from_pidfile("Data", 10101)
        self.assertFalse(launcher.PAUSEFILE.exists())
        self.assertFalse(launcher.stop_request_path("Data", 10101).exists())

    def test_mismatched_instance_does_not_pause(self):
        launcher.PIDFILE.write_text(json.dumps({"dbname": "Data", "relay_port": 10101}))
        self.assertEqual(launcher.stop_from_pidfile("WSRTD", 10101), 2)
        self.assertFalse(launcher.PAUSEFILE.exists())
        self.assertFalse((self.root / "stop_provenance.jsonl").exists())

    def test_normal_ensure_running_creates_no_pause_or_provenance(self):
        with mock.patch.object(launcher, "adjudicate_pid_state",
                               return_value=launcher.LAUNCH_OWNERSHIP_ALREADY_RUNNING):
            self.assertEqual(launcher.ensure_running("Data", 10101), 0)
        self.assertFalse(launcher.PAUSEFILE.exists())
        self.assertFalse((self.root / "stop_provenance.jsonl").exists())

    def test_raw_credentials_and_environment_are_not_recorded(self):
        with mock.patch.object(launcher.sys, "argv", ["launcher", "--token", "TOP_SECRET"]):
            with mock.patch.dict(os.environ, {"API_KEY": "TOP_SECRET"}):
                launcher.stop_from_pidfile("Data", 10101)
        self.assertNotIn("TOP_SECRET", (self.root / "stop_provenance.jsonl").read_text())
        self.assertIn("--dbname Data", self.records()[0]["commandLine"])

    def test_concurrent_appends_are_complete_and_preserve_predecessors(self):
        launcher.record_stop_intent("Data", 10101, {}, "test-harness")
        prefix = (self.root / "stop_provenance.jsonl").read_bytes()
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: launcher.record_stop_intent("Data", 10101, {}, "test-harness"),
                          range(8)))
        self.assertTrue((self.root / "stop_provenance.jsonl").read_bytes().startswith(prefix))
        records = self.records()
        self.assertEqual(len(records), 9)
        self.assertEqual(len({record["eventId"] for record in records}), 9)

    def test_cli_and_wrapper_source_are_explicit(self):
        with mock.patch.object(launcher.sys, "argv", ["launcher", "--stop", "--dbname", "Data"]):
            with mock.patch.object(launcher, "stop_from_pidfile", return_value=0) as stop:
                self.assertEqual(launcher.main(), 0)
                stop.assert_called_once_with("Data", 10101, source="direct-cli")
        wrapper = (launcher.BASE / "stop_wsrtd_stack.cmd").read_text()
        self.assertIn("--stop --dbname Data --relay-port 10101 %* --stop-source cmd-wrapper", wrapper)


if __name__ == "__main__":
    unittest.main()
