"""Identity publication regressions; all outputs and contention use temp files."""
import ctypes
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock

import identity_bridge as bridge


class ConcurrentReadEvidence:
    """Count only published snapshots whose entire read brackets an active writer."""
    def __init__(self, writer_started, writer_finished):
        self.writer_started = writer_started
        self.writer_finished = writer_finished
        self.total_reads = 0
        self.concurrent_published_reads = 0

    def read(self, path):
        active_before = self.writer_started.is_set() and not self.writer_finished.is_set()
        with path.open("r", encoding="utf-8") as stream:
            snapshot = json.load(stream)
        active_after = self.writer_started.is_set() and not self.writer_finished.is_set()
        self.total_reads += 1
        if (active_before and active_after and snapshot.get("seq", -1) >= 0
                and snapshot.get("identityReady") is True):
            self.concurrent_published_reads += 1
        return snapshot

    def require_concurrent_publication(self):
        if self.concurrent_published_reads <= 0:
            raise AssertionError("no published identity snapshot was read while writer was active")


class IdentityPublicationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / "data_identity.v1.json"
        self.old = b'{"old":true}'
        self.path.write_bytes(self.old)

    def assert_no_staging(self):
        self.assertEqual(list(self.root.rglob("*.tmp")), [])

    def test_normal_and_serialization_failure(self):
        bridge.write_atomic(self.path, {"new": True})
        self.assertEqual(json.loads(self.path.read_text()), {"new": True})
        with mock.patch.object(bridge.os, "replace") as replace:
            with self.assertRaises(TypeError):
                bridge.write_atomic(self.path, {"invalid": object()})
            replace.assert_not_called()
        self.assertEqual(json.loads(self.path.read_text()), {"new": True})
        self.assert_no_staging()

    @unittest.skipUnless(os.name == "nt", "Real Windows sharing")
    def test_real_transient_reader_denial(self):
        original = os.replace
        denied = threading.Event()
        release_errors = []
        held = self.path.open("r")

        def release():
            try:
                if not denied.wait(2):
                    raise AssertionError("no sharing denial observed")
                time.sleep(0.05)
                self.assertEqual(self.path.read_bytes(), self.old)
            except BaseException as exc:
                release_errors.append(exc)
            finally:
                held.close()

        def replacing(src, dst):
            try:
                return original(src, dst)
            except PermissionError:
                denied.set()
                raise

        worker = threading.Thread(target=release)
        worker.start()
        try:
            with mock.patch.object(bridge.os, "replace", side_effect=replacing) as replace:
                bridge.write_atomic(self.path, {"new": True})
                self.assertGreater(replace.call_count, 1)
                self.assertLessEqual(replace.call_count, 5)
        finally:
            worker.join(3)
            held.close()
        self.assertFalse(worker.is_alive())
        self.assertEqual(release_errors, [])
        self.assertEqual(json.loads(self.path.read_text()), {"new": True})
        self.assert_no_staging()

    @unittest.skipUnless(os.name == "nt", "Real Windows sharing")
    def test_real_persistent_denial(self):
        started = time.monotonic()
        with self.path.open("r"), mock.patch.object(bridge.os, "replace", wraps=os.replace) as replace:
            with self.assertRaises(PermissionError) as caught:
                bridge.write_atomic(self.path, {"new": True})
            self.assertEqual(replace.call_count, 5)
            self.assertIn(caught.exception.winerror, (5, 32, 33))
            self.assertEqual(Path(caught.exception.filename2), self.path)
        self.assertLess(time.monotonic() - started, 3)
        self.assertEqual(self.path.read_bytes(), self.old)
        self.assert_no_staging()

    @unittest.skipUnless(os.name == "nt", "Windows error codes")
    def test_classified_errors_exact_budget(self):
        for code in (5, 32, 33):
            error = ctypes.WinError(code)
            with self.subTest(code=code), mock.patch.object(
                    bridge.os, "replace", side_effect=error) as replace, \
                    mock.patch.object(bridge.time, "sleep") as sleep:
                with self.assertRaises(OSError) as caught:
                    bridge.write_atomic(self.path, {"new": True})
                self.assertIs(caught.exception, error)
                self.assertEqual(replace.call_count, 5)
                self.assertEqual(sleep.call_args_list,
                                 [mock.call(x) for x in (0.025, 0.05, 0.1, 0.2)])
            self.assertEqual(self.path.read_bytes(), self.old)
            self.assert_no_staging()

    def test_unrelated_io_error_not_retried(self):
        for error in (OSError(28, "disk full"), PermissionError(1, "unrelated")):
            with mock.patch.object(bridge.os, "replace", side_effect=error) as replace, \
                    mock.patch.object(bridge.time, "sleep") as sleep:
                with self.assertRaises(OSError) as caught:
                    bridge.write_atomic(self.path, {"new": True})
                self.assertIs(caught.exception, error)
                replace.assert_called_once()
                sleep.assert_not_called()
            self.assertEqual(self.path.read_bytes(), self.old)
            self.assert_no_staging()

    def test_non_windows_no_retry(self):
        error = OSError("denial")
        error.winerror = 5
        fake_os = mock.Mock(wraps=os)
        fake_os.name = "posix"
        fake_os.replace.side_effect = error
        with mock.patch.object(bridge, "os", fake_os), \
                mock.patch.object(bridge.time, "sleep") as sleep:
            with self.assertRaises(OSError):
                bridge.write_atomic(self.path, {"new": True})
            fake_os.replace.assert_called_once()
            sleep.assert_not_called()
        self.assert_no_staging()

    def test_overlapping_calls_have_distinct_staging(self):
        original = os.replace
        paths = []

        def replacing(src, dst):
            paths.append(src)
            if len(paths) == 1:
                first_bytes = src.read_bytes()
                bridge.write_atomic(self.path, {"writer": 2})
                self.assertEqual(src.read_bytes(), first_bytes)
            original(src, dst)

        with mock.patch.object(bridge.os, "replace", side_effect=replacing):
            bridge.write_atomic(self.path, {"writer": 1})
        self.assertEqual(len(set(paths)), 2)
        self.assertTrue(all(p.parent == self.path.parent for p in paths))
        self.assertEqual(json.loads(self.path.read_text()), {"writer": 1})
        self.assert_no_staging()

    def test_one_shot_both_output_classes_and_semantics(self):
        manifest = bridge.load_and_verify_manifest()
        recovery = {"saved_utc": "2026-09-23T00:00:00+00:00", "symbols": {
            s: {"last_completed_1m_open_ms": 1790121600000,
                "last_completed_eod_date": 20260922, "updated_utc": "fixture"}
            for s in manifest["symbols"]}}
        market = {"symbols": {s: {"live": True, "fresh": True,
                  "historyHydrated": True, "quoteAgeMs": 12} for s in manifest["symbols"]}}
        recovery_path = self.root / "recovery.json"
        market_path = self.root / "market.json"
        recovery_path.write_text(json.dumps(recovery))
        market_path.write_text(json.dumps(market))
        status_dir = self.root / "autotrader_status"
        with mock.patch.object(bridge, "RECOVERY_PATH", recovery_path), \
                mock.patch.object(bridge, "MARKET_STATUS_PATH", market_path), \
                mock.patch.object(bridge, "OUTPUT_PATH", self.path), \
                mock.patch.object(bridge, "STATUS_DIR", status_dir), \
                mock.patch.object(bridge, "write_atomic", wraps=bridge.write_atomic) as write:
            snapshot = bridge.write_once(manifest)
        self.assertEqual(write.call_count, 13)
        self.assertEqual(json.loads(self.path.read_text()), snapshot)
        for key in ("universeId", "universeVersion", "universeHash"):
            self.assertEqual(snapshot[key], manifest[key])
        self.assertTrue(snapshot["identityReady"])
        self.assertEqual(snapshot["generationKind"], bridge.GENERATION_KIND)
        expected = bridge.build_runtime_status_files(manifest, recovery, market)
        for symbol in manifest["symbols"]:
            actual = json.loads((status_dir / f"{symbol}.json").read_text())
            actual.pop("generatedUnixMs")
            expected[symbol].pop("generatedUnixMs")
            self.assertEqual(actual, expected[symbol])
            self.assertEqual(actual["dataGeneration"], 1790121600000)
            self.assertTrue(actual["identityReady"] and actual["live"] and actual["fresh"] and actual["cacheReady"])
            self.assertEqual((actual["cacheIntraday"], actual["cacheEod"]), (1500, 300))
        self.assert_no_staging()

    def test_concurrent_ordinary_reader_stress(self):
        self.path.write_text('{"seq":-1}', encoding="utf-8")
        stop = threading.Event()
        writer_started = threading.Event()
        writer_finished = threading.Event()
        evidence = ConcurrentReadEvidence(writer_started, writer_finished)
        invalid = []
        failures = []
        ready = threading.Event()

        def reading():
            while not stop.is_set():
                try:
                    evidence.read(self.path)
                except PermissionError:
                    pass  # Ordinary reader may itself lose a replacement race.
                except Exception as exc:
                    invalid.append(repr(exc))
                ready.set()
                time.sleep(0.001)

        worker = threading.Thread(target=reading)
        worker.start()
        try:
            self.assertTrue(ready.wait(2))
            writer_started.set()
            for seq in range(1000):
                try:
                    bridge.write_atomic(self.path, {"seq": seq, "identityReady": True})
                except OSError as exc:
                    failures.append(repr(exc))
        finally:
            writer_finished.set()
            stop.set()
            worker.join(3)
        self.assertFalse(worker.is_alive())
        print(f'IDENTITY_STRESS_PUBLICATIONS=1000 WRITER_FAILURES={len(failures)} '
              f'INVALID_READS={len(invalid)} TOTAL_READS={evidence.total_reads} '
              f'CONCURRENT_PUBLISHED_READS={evidence.concurrent_published_reads} '
              f'STAGING_LEAKS={len(list(self.root.rglob("*.tmp")))}')
        self.assertEqual(failures, [])
        self.assertEqual(invalid, [])
        evidence.require_concurrent_publication()
        self.assertEqual(json.loads(self.path.read_text()), {"seq": 999, "identityReady": True})
        self.assert_no_staging()

    def test_seed_plus_final_is_rejected(self):
        writer_started = threading.Event()
        writer_finished = threading.Event()
        evidence = ConcurrentReadEvidence(writer_started, writer_finished)
        self.path.write_text('{"seq":-1}', encoding="utf-8")
        writer_started.set()
        self.assertEqual(evidence.read(self.path), {"seq": -1})
        writer_finished.set()
        bridge.write_atomic(self.path, {"seq": 999, "identityReady": True})
        self.assertEqual(evidence.read(self.path), {"seq": 999, "identityReady": True})
        self.assertEqual(evidence.total_reads, 2)
        self.assertEqual(evidence.concurrent_published_reads, 0)
        with self.assertRaisesRegex(
                AssertionError, "no published identity snapshot was read while writer was active"):
            evidence.require_concurrent_publication()


if __name__ == "__main__":
    unittest.main()
