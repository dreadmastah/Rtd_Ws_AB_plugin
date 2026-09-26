"""Exercise CLI defaults and real cmd argument forwarding without live actions."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import autostart_manager
import stack_launcher as launcher


class DatabaseDefaultsTests(unittest.TestCase):
    def test_launcher_default_and_override(self):
        for args, expected in (([], "Data"), (["--dbname", "SomeOtherDb"], "SomeOtherDb")):
            with self.subTest(args=args), mock.patch.object(sys, "argv", ["launcher", *args]):
                with mock.patch.object(launcher, "run_supervisor", return_value=0) as run:
                    with mock.patch.dict(os.environ, {"WSRTD_RELAY_PORT": "10101"}):
                        self.assertEqual(launcher.main(), 0)
                    run.assert_called_once_with(expected, 10101)

    def test_blank_lock_default_and_explicit_identity(self):
        for name in ("", "   "):
            lock = launcher.InstanceLock(name, 10101)
            self.assertEqual(lock.dbname, "Data")
            self.assertEqual(lock.identity, launcher.instance_lock_identity("Data", 10101))
        self.assertEqual(launcher.InstanceLock("SomeOtherDb", 10102).dbname, "SomeOtherDb")

    def test_autostart_cli_default_and_override(self):
        for args, expected in (([], "Data"), (["--dbname", "SomeOtherDb"], "SomeOtherDb")):
            with self.subTest(args=args), mock.patch.object(sys, "argv", ["manager", "--install", *args]):
                with mock.patch.object(autostart_manager, "install", return_value=0) as install:
                    self.assertEqual(autostart_manager.main(), 0)
                    install.assert_called_once_with(expected)

    def wrapper_args(self, root, filename, target, args):
        # Run a copy of the actual wrapper with only the interpreter path
        # redirected. The target is a harmless argv printer in a temporary cwd;
        # no production launcher/installer code is executed by cmd.exe.
        content = (launcher.BASE / filename).read_text()
        content = content.replace(r".venv\Scripts\python.exe", sys.executable)
        (root / filename).write_text(content, encoding="utf-8")
        (root / target).write_text(
            "import json, sys\nprint(json.dumps(sys.argv))\n", encoding="utf-8")
        command = subprocess.list2cmdline([filename, *args])
        result = subprocess.run(
            'cmd.exe /d /c ' + command, cwd=root, capture_output=True,
            text=True, check=True, timeout=10,
            creationflags=launcher.windows_hidden_flags(),
        )
        return json.loads(result.stdout.strip())

    @unittest.skipUnless(os.name == "nt", "real Windows batch wrapper")
    def test_install_wrapper_default_and_override(self):
        with tempfile.TemporaryDirectory() as directory:
            for args, expected in (([], "Data"), (["SomeOtherDb"], "SomeOtherDb"),
                                   (["Some Other Db"], "Some Other Db")):
                with self.subTest(args=args):
                    argv = self.wrapper_args(Path(directory), "install_recovery_autostart.cmd",
                                             "autostart_manager.py", args)
                    with mock.patch.object(sys, "argv", argv):
                        with mock.patch.object(autostart_manager, "install", return_value=0) as install:
                            self.assertEqual(autostart_manager.main(), 0)
                            install.assert_called_once_with(expected)

    @unittest.skipUnless(os.name == "nt", "real Windows batch wrapper")
    def test_stop_wrapper_default_override_and_provenance(self):
        cases = (([], "Data", 10101),
                 (["--dbname", "SomeOtherDb", "--relay-port", "10102"], "SomeOtherDb", 10102),
                 (["--dbname", "Some Other Db", "--relay-port", "19107"], "Some Other Db", 19107))
        for args, dbname, port in cases:
            with self.subTest(args=args), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                argv = self.wrapper_args(root, "stop_wsrtd_stack.cmd", "stack_launcher.py", args)
                with (mock.patch.object(sys, "argv", argv),
                      mock.patch.object(launcher, "RUNTIME", root),
                      mock.patch.object(launcher, "PIDFILE", root / "pids.json"),
                      mock.patch.object(launcher, "PAUSEFILE", root / "maintenance_pause"),
                      mock.patch.dict(os.environ, {"WSRTD_RELAY_PORT": "19999"})):
                    self.assertEqual(launcher.main(), 0)
                record = json.loads((root / "stop_provenance.jsonl").read_text())
                self.assertEqual(record["dbname"], dbname)
                self.assertEqual(record["relay_port"], port)
                self.assertEqual(record["sourceDeclared"], "cmd-wrapper")
                self.assertEqual(record["instanceId"], launcher.instance_token(dbname, port))
                self.assertEqual(json.loads((root / "maintenance_pause").read_text()), record)


if __name__ == "__main__":
    unittest.main()
