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
                with self.assertRaisesRegex(PermissionError, "exhausted 5 attempts"):
                    reader.read_json(path)
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
            count = 0
            try:
                deadline = time.monotonic() + 45
                while process.poll() is None:
                    snapshot = reader.read_json(path)
                    self.assertTrue(snapshot.get("seq") == -1 or snapshot.get("messageType") == "ExecutionStatus.v1")
                    count += 1
                    self.assertLess(time.monotonic(), deadline, "publisher deadline exceeded")
                    time.sleep(0.001)  # 1 kHz sampling; do not busy-spin a reader.
            finally:
                if process.poll() is None:
                    process.kill()
                stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertIn(b"PUBLISH_COUNT=1000", stdout)
            self.assertGreater(count, 0)
            self.assertEqual(reader.read_json(path)["messageType"], "ExecutionStatus.v1")


if __name__ == "__main__":
    unittest.main()
