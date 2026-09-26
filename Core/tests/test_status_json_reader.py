import ctypes
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import status_json_reader as reader


class ReaderTests(unittest.TestCase):
    def test_all_migrated_live_checkpoints_use_shared_reader(self):
        consumers = {
            "available_balance_reservation": ("STATUS", 4),
            "execution_restart": ("EXECSTATUS", 1),
            "exposure_reservation": ("STATUS", 4),
            "loss_drawdown_risk": ("STATUS", 4),
            "net_directional_risk": ("STATUS", 3),
            "realized_pnl_risk": ("EXECSTATUS", 2),
        }
        for name, (variable, expected_count) in consumers.items():
            script = (Path(__file__).resolve().parents[1] / "tools" /
                      f"run_{name}_smoke.cmd").read_text(encoding="utf-8")
            lines = [line for line in script.splitlines()
                     if line.startswith('python -c ') and f"%{variable}%" in line]
            with self.subTest(script=name):
                self.assertEqual(len(lines), expected_count)
                for line in lines:
                    self.assertIn(
                        r"sys.path.insert(0,r'%ROOT%\tools'); "
                        "from status_json_reader import read_json; "
                        f"o=read_json(r'%{variable}%');", line)
                    self.assertNotIn(f"json.load(open(r'%{variable}%'", line)

    def test_unicode_and_multichunk_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "狀態.json"
            expected = {"text": "snapshot" * 30000}
            path.write_text(json.dumps(expected), encoding="utf-8")
            self.assertEqual(reader.read_json(path), expected)
            # Successful read must release the handle.
            path.unlink()

    def test_previously_migrated_live_checkpoints_remain_shared(self):
        for name, count in [("reconciliation_fsm", 1), ("reconciliation_pipe", 2),
                            ("runtime_order_reconciliation", 6),
                            ("startup_order_snapshot", 4)]:
            script = (Path(__file__).resolve().parents[1] / "tools" /
                      f"run_{name}_smoke.cmd").read_text(encoding="utf-8")
            lines = [line for line in script.splitlines()
                     if line.startswith('python -c ') and "%STATUS%" in line]
            with self.subTest(script=name):
                self.assertEqual(len(lines), count)
                for line in lines:
                    self.assertIn("__import__('status_json_reader').read_json(r'%STATUS%')", line)
                    self.assertNotIn("json.load(open(r'%STATUS%'", line)

    @unittest.skipUnless(os.name == "nt", "Windows handle safety")
    def test_native_partial_reads_close_once(self):
        from ctypes import wintypes
        pieces = iter([b'{"ok":', b'true}', b''])

        def read_part(handle, buffer, size, count, overlapped):
            part = next(pieces)
            ctypes.memmove(buffer, part, len(part))
            ctypes.cast(count, ctypes.POINTER(wintypes.DWORD))[0] = len(part)
            return True

        with mock.patch.object(reader, "_kernel") as kernel:
            kernel.CreateFileW.return_value = 123
            kernel.ReadFile.side_effect = read_part
            kernel.CloseHandle.return_value = True
            self.assertEqual(reader.read_json("狀態.json"), {"ok": True})
            kernel.CreateFileW.assert_called_once_with(
                "狀態.json", 0x80000000, 7, None, 3, 0x80, None)
            self.assertEqual(kernel.ReadFile.call_count, 3)
            kernel.CloseHandle.assert_called_once_with(123)

    @unittest.skipUnless(os.name == "nt", "Windows handle safety")
    def test_native_open_failure_does_not_close_invalid_handle(self):
        with mock.patch.object(reader, "_kernel") as kernel, \
                mock.patch.object(reader.ctypes, "get_last_error", return_value=2):
            kernel.CreateFileW.return_value = ctypes.c_void_p(-1).value
            with self.assertRaises(FileNotFoundError) as caught:
                reader._read_bytes("missing")
            self.assertEqual(caught.exception.winerror, 2)
            kernel.ReadFile.assert_not_called()
            kernel.CloseHandle.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows handle safety")
    def test_native_read_error_closes_and_preserves_original_error(self):
        with mock.patch.object(reader, "_kernel") as kernel, \
                mock.patch.object(reader.ctypes, "get_last_error", return_value=1117):
            kernel.CreateFileW.return_value = 123
            kernel.ReadFile.return_value = False
            kernel.CloseHandle.return_value = False
            with self.assertRaises(OSError) as caught:
                reader._read_bytes("fixture")
            self.assertEqual(caught.exception.winerror, 1117)
            kernel.CloseHandle.assert_called_once_with(123)

    def test_empty_truncated_and_invalid_unicode_are_not_retried(self):
        for payload, error in [(b"", json.JSONDecodeError),
                               (b'{"partial":', json.JSONDecodeError),
                               (b"\xff", UnicodeDecodeError)]:
            with self.subTest(payload=payload), mock.patch.object(
                    reader, "_read_bytes", return_value=payload) as read, \
                    mock.patch.object(reader.time, "sleep") as sleep:
                with self.assertRaises(error):
                    reader.read_json("fixture")
                self.assertEqual(read.call_count, 1)
                sleep.assert_not_called()

    def test_order_fsm_restart_status_reads_use_hardened_reader(self):
        script = (Path(__file__).resolve().parents[1] / "tools" /
                  "run_order_fsm_restart_smoke.cmd").read_text(encoding="utf-8")
        status_reads = [line for line in script.splitlines()
                        if line.startswith('python -c ') and "%STATUS%" in line]
        self.assertEqual(len(status_reads), 2)
        for marker in ("ORDER_FSM_RECOVERY_STATUS=PASS",
                       "ORDER_FSM_DUPLICATE_RECOVERY=PASS"):
            with self.subTest(marker=marker):
                matches = [line for line in status_reads if marker in line]
                self.assertEqual(len(matches), 1)
                line = matches[0]
                self.assertIn(
                    r"sys.path.insert(0,r'%ROOT%\tools'); "
                    "from status_json_reader import read_json; "
                    "o=read_json(r'%STATUS%');", line)
                self.assertNotRegex(line, r"json\.load\s*\(\s*open\s*\(")

    def test_normal_read_has_no_delay(self):
        with mock.patch.object(reader, "_read_bytes", return_value=b'{"ok":true}'), mock.patch.object(reader.time, "sleep") as sleep:
            self.assertEqual(reader.read_json("fixture"), {"ok": True})
            sleep.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows sharing retry")
    def test_transient_permission_error(self):
        with mock.patch.object(reader, "_read_bytes", side_effect=[PermissionError(13, "denied"), b'{"ok":true}']) as read, mock.patch.object(reader.time, "sleep") as sleep:
            self.assertEqual(reader.read_json("fixture"), {"ok": True})
            self.assertEqual(read.call_count, 2)
            sleep.assert_called_once_with(0.01)

    @unittest.skipUnless(os.name == "nt", "Windows sharing retry")
    def test_persistent_permission_error(self):
        with mock.patch.object(reader, "_read_bytes", side_effect=PermissionError(13, "denied")) as read, mock.patch.object(reader.time, "sleep") as sleep:
            with self.assertRaisesRegex(PermissionError, "exhausted 5 attempts"):
                reader.read_json("fixture")
            self.assertEqual(read.call_count, 5)
            self.assertEqual(sleep.call_count, 4)

    def test_malformed_json_is_not_retried(self):
        with mock.patch.object(reader, "_read_bytes", return_value=b'{bad') as read, mock.patch.object(reader.time, "sleep") as sleep:
            with self.assertRaises(json.JSONDecodeError):
                reader.read_json("fixture")
            self.assertEqual(read.call_count, 1)
            sleep.assert_not_called()

    def test_missing_file_is_not_retried(self):
        with mock.patch.object(reader, "_read_bytes", side_effect=FileNotFoundError) as read:
            with self.assertRaises(FileNotFoundError):
                reader.read_json("fixture")
            self.assertEqual(read.call_count, 1)

    def test_unrelated_permission_error_is_not_retried(self):
        with mock.patch.object(reader, "_read_bytes", side_effect=PermissionError(1, "not sharing")) as read:
            with self.assertRaises(PermissionError):
                reader.read_json("fixture")
            self.assertEqual(read.call_count, 1)

    def test_wrong_reconciliation_semantics_still_fail(self):
        with mock.patch.object(reader, "_read_bytes", return_value=b'{"runtimeOrderUnresolved":0}') as read:
            with self.assertRaises(AssertionError):
                snapshot = reader.read_json("fixture")
                assert snapshot["runtimeOrderUnresolved"] == 1
            self.assertEqual(read.call_count, 1)

    @unittest.skipUnless(os.name == "nt", "Windows sharing reproduction")
    def test_real_rename_handle_blocks_legacy_reader(self):
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "status.json"
            path.write_text('{"ok":true}')
            # Rename needs DELETE access. A CRT reader which omits SHARE_DELETE
            # cannot coexist with this handle, even though we permit reads.
            handle = kernel.CreateFileW(str(path), 0x10000, 7, None, 3, 0x80, None)
            self.assertNotEqual(handle, wintypes.HANDLE(-1).value)
            try:
                with self.assertRaises(PermissionError):
                    path.read_text()
                with mock.patch.object(reader.time, "sleep") as sleep:
                    self.assertEqual(reader.read_json(path), {"ok": True})
                    sleep.assert_not_called()
            finally:
                kernel.CloseHandle(handle)
            self.assertEqual(reader.read_json(path), {"ok": True})

    @unittest.skipUnless(os.name == "nt", "Windows sharing reproduction")
    def test_legacy_reader_blocks_producer_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "status.json"
            staging = Path(directory) / "status.tmp"
            path.write_text('{"old":true}')
            staging.write_text('{"new":true}')
            with path.open("r"):
                with self.assertRaises(PermissionError):
                    os.replace(staging, path)
            self.assertEqual(reader.read_json(path), {"old": True})

    @unittest.skipUnless(os.name == "nt", "Windows concurrent atomic publisher")
    def test_concurrent_atomic_publish_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "status.json"
            path.write_text('{"seq":-1}')
            binary = Path(__file__).resolve().parents[2] / "build/core/Release/astu_status_sharing_tests.exe"
            self.assertTrue(binary.exists(), "build Core before running Windows sharing tests")
            process = subprocess.Popen([str(binary), "--publish", str(path)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            total_loop_reads = 0
            concurrent_execution_status_reads = 0
            try:
                deadline = time.monotonic() + 45
                while process.poll() is None:
                    snapshot = reader.read_json(path)
                    self.assertTrue(snapshot.get("seq") == -1 or snapshot.get("messageType") == "ExecutionStatus.v1")
                    total_loop_reads += 1
                    # Exclude the seed and reads which finish after the child
                    # exits; only native snapshots observed during its lifetime
                    # provide evidence of concurrent publication/read sharing.
                    if snapshot.get("messageType") == "ExecutionStatus.v1" and process.poll() is None:
                        concurrent_execution_status_reads += 1
                    self.assertLess(time.monotonic(), deadline, "publisher deadline exceeded")
                    time.sleep(0.001)  # 1 kHz sampling; do not busy-spin a reader.
            finally:
                if process.poll() is None:
                    process.kill()
                stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertIn(b"PUBLISH_COUNT=1000", stdout)
            self.assertEqual(reader.read_json(path)["messageType"], "ExecutionStatus.v1")
            print(f"TOTAL_LOOP_READS={total_loop_reads} "
                  f"CONCURRENT_EXECUTION_STATUS_READS={concurrent_execution_status_reads}")
            self.assertGreater(total_loop_reads, 0)
            self.assertGreater(
                concurrent_execution_status_reads,
                0,
                "no ExecutionStatus.v1 snapshot was read while native publisher was running",
            )

    @unittest.skipUnless(os.name == "nt", "Windows concurrent test negative control")
    def test_concurrent_seed_only_is_rejected(self):
        process = mock.Mock()
        process.poll.side_effect = [None, 0, 0]
        process.returncode = 0
        process.communicate.return_value = (b"PUBLISH_COUNT=1000", b"")
        with mock.patch.object(subprocess, "Popen", return_value=process), \
                mock.patch.object(reader, "read_json", side_effect=[
                    {"seq": -1}, {"messageType": "ExecutionStatus.v1"}]) as read, \
                mock.patch.object(time, "sleep"), mock.patch("builtins.print") as output:
            with self.assertRaisesRegex(
                    AssertionError,
                    "no ExecutionStatus.v1 snapshot was read while native publisher was running"):
                self.test_concurrent_atomic_publish_read()
            self.assertEqual(read.call_count, 2)  # Seed loop read and valid final read.
            output.assert_called_once_with(
                "TOTAL_LOOP_READS=1 CONCURRENT_EXECUTION_STATUS_READS=0")
            process.kill.assert_not_called()


if __name__ == "__main__":
    unittest.main()
