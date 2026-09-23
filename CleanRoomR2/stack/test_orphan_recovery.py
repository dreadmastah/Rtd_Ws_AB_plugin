"""Synthetic Windows cohorts only: no live process, registry, or port actions."""
import contextlib
import copy
import io
import json
import ntpath
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest import mock

import orphan_recovery as recovery
import stack_launcher as launcher


class OrphanRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.scope = contextlib.ExitStack()
        self.addCleanup(self.scope.close)
        self.temp = self.scope.enter_context(tempfile.TemporaryDirectory())
        self.base = Path(self.temp)
        self.shim = recovery.normalized(self.base / ".venv" / "Scripts" / "python.exe")
        self.python = recovery.normalized(Path(sys._base_executable).with_name("python.exe"))
        for name, value in (("BASE", self.base), ("RUNTIME", self.base), ("LOGS", self.base),
                            ("PIDFILE", self.base / "pids.json"),
                            ("PAUSEFILE", self.base / "pause")):
            self.patch(launcher, name, value)
        self.patch(launcher, "console_python", return_value=self.shim)
        self.scope.enter_context(mock.patch.dict(launcher.CFG, {"identity_bridge": {"enabled": True}}))
        self.identities = {}
        self.rows = {}
        self.data = {
            "schemaVersion": 2, "launchNonce": "a" * 32,
            "dbname": "Data", "relay_port": 10101,
            "instance_lock": launcher.instance_lock_identity("Data", 10101),
            "working_directory": str(self.base),
            "processes": {"launcher": self.record(11, 100, self.python)}, "launcher": 11,
        }
        for index, (role, script) in enumerate(recovery.SCRIPTS.items()):
            pid = 21 + index
            root = self.record(pid, 200 + index * 10, self.shim)
            child = self.record(pid + 10, 205 + index * 10, self.python)
            self.data["processes"][role] = root
            self.data[role] = pid
            self.add_process(root, 11, script)
            self.add_process(child, pid, script)
        self.add_process(self.record(80, 1000, self.python), 999, "unrelated.py")
        self.add_process(self.record(90, 1000, str(self.base / "Broker.exe")), 999, None)
        self.identities[os.getpid()] = self.record(os.getpid(), 5000, self.python)
        self.write()
        self.original = launcher.PIDFILE.read_bytes()
        self.patch(launcher, "process_identity", side_effect=lambda pid: copy.deepcopy(self.identities.get(pid)))
        self.patch(launcher, "pid_alive", side_effect=lambda pid: pid in self.identities)
        self.patch(recovery, "process_snapshot", side_effect=lambda: copy.deepcopy(self.rows))
        # Unexpected use of real process primitives must fail the test.
        self.patch(launcher.subprocess, "run", side_effect=AssertionError("real subprocess forbidden"))
        self.patch(launcher.subprocess, "Popen", side_effect=AssertionError("real spawn forbidden"))
        self.patch(launcher.os, "kill", side_effect=AssertionError("real kill forbidden"))
        self.spawn = self.patch(launcher, "popen_with_sanitized_environment", return_value=SimpleNamespace(pid=777))
        self.registry = self.patch(launcher, "configure_registry", return_value=True)
        self.supervise = self.patch(launcher, "run_supervisor_locked", return_value=0)
        self.provenance = self.patch(launcher, "append_stop_provenance", side_effect=AssertionError("stop audit forbidden"))
        self.terminated = []
        self.closed = []
        self.fail_pid = None
        self.timeout_pid = None
        test = self

        class FakePinned:
            def __init__(self, record):
                self.record = record
                if test.identities.get(record["pid"]) != record:
                    raise OSError("identity changed")

            def terminate(self):
                pid = self.record["pid"]
                if pid == test.fail_pid:
                    raise OSError("injected termination failure")
                test.terminated.append(pid)
                if pid != test.timeout_pid:
                    test.identities.pop(pid, None)
                    test.rows.pop(pid, None)

            def wait(self, timeout):
                return self.record["pid"] not in test.identities

            def close(self):
                test.closed.append(self.record["pid"])

        self.pins = self.patch(recovery, "_PinnedProcess", side_effect=FakePinned)

        class FakeLock:
            guard = threading.Lock()
            held = False

            def __init__(self, dbname, port):
                self.identity = launcher.instance_lock_identity(dbname, port)

            def acquire(self):
                with self.guard:
                    if type(self).held:
                        return False
                    type(self).held = True
                    return True

            def release(self):
                with self.guard:
                    type(self).held = False

        self.lock_class = FakeLock
        self.patch(launcher, "InstanceLock", FakeLock)

    def patch(self, obj, name, *args, **kwargs):
        return self.scope.enter_context(mock.patch.object(obj, name, *args, **kwargs))

    def record(self, pid, created, executable):
        return {"pid": pid, "creationTime100ns": created,
                "executable": recovery.normalized(executable)}

    def add_process(self, record, parent, script):
        self.identities[record["pid"]] = record
        self.rows[record["pid"]] = {
            "pid": record["pid"], "parent": parent, "created": record["creationTime100ns"],
            "executable": record["executable"],
            "argv": [record["executable"], "-u", str(self.base / script)] if script else [record["executable"]],
        }

    def write(self):
        launcher.PIDFILE.write_text(json.dumps(self.data), encoding="utf-8")

    def classify(self):
        return launcher.adjudicate_pid_state("Data", 10101)

    def assert_refused(self):
        before = launcher.PIDFILE.read_bytes()
        self.assertEqual(launcher.ensure_running("Data", 10101), 4)
        self.assertFalse(self.terminated)
        self.spawn.assert_not_called()
        self.supervise.assert_not_called()
        self.assertEqual(launcher.PIDFILE.read_bytes(), before)

    def test_live_launcher_already_running_no_cleanup(self):
        self.identities[11] = self.data["processes"]["launcher"]
        self.assertEqual(self.classify(), launcher.LAUNCH_OWNERSHIP_ALREADY_RUNNING)
        self.assertEqual(launcher.ensure_running("Data", 10101), 0)
        self.assertFalse(self.terminated)
        self.spawn.assert_not_called()

    def test_all_children_dead_normal_recovery(self):
        for pid in range(21, 34):
            self.rows.pop(pid, None)
            self.identities.pop(pid, None)
        self.assertEqual(self.classify(), launcher.LAUNCH_OWNERSHIP_ACQUIRED)
        self.assertEqual(launcher.ensure_running("Data", 10101), 0)
        self.spawn.assert_called_once()
        self.assertFalse(self.terminated)

    def test_complete_cohort_classified(self):
        self.assertEqual(self.classify(), launcher.LAUNCH_OWNERSHIP_ORPHANED_MANAGED_COHORT)

    def test_ensure_defers_cleanup_to_detached_lock_owner(self):
        self.assertEqual(launcher.ensure_running("Data", 10101), 0)
        self.spawn.assert_called_once()
        self.registry.assert_not_called()
        self.assertFalse(self.terminated)
        self.assertFalse(self.lock_class.held)

    def test_worker_cleans_once_and_publishes_fresh_state_under_same_lock(self):
        def supervised(*args):
            self.assertTrue(self.lock_class.held)
            state = launcher.load_pidfile()
            self.assertEqual(state["launcher"], os.getpid())
            self.assertNotEqual(state["launchNonce"], self.data["launchNonce"])
            self.assertEqual(state["processes"]["launcher"], self.identities[os.getpid()])
            return 0
        self.supervise.side_effect = supervised
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(launcher.run_supervisor("Data", 10101), 0)
        self.assertEqual(self.terminated, [21, 31, 22, 32, 23, 33])
        self.assertEqual(len(self.closed), 6)
        self.supervise.assert_called_once()
        self.assertFalse(self.lock_class.held)
        for outcome in ("VERIFIED", "CLEANUP_STARTED", "CLEANUP_COMPLETE"):
            self.assertIn("WSRTD_ORPHAN_RECOVERY=" + outcome, out.getvalue())
        self.assertIn("WSRTD_ENSURE_RUNNING=STARTED", out.getvalue())

    def test_ambiguous_child_refuses(self):
        self.patch(launcher, "process_identity", side_effect=lambda pid: None if pid == 22 else self.identities.get(pid))
        self.assert_refused()

    def test_child_executable_mismatch_refuses(self):
        self.identities[22] = dict(self.identities[22], executable=str(self.base / "other.exe"))
        self.assert_refused()

    def test_child_pid_reuse_refuses(self):
        self.identities[22] = dict(self.identities[22], creationTime100ns=9999)
        self.assert_refused()

    def test_stale_launcher_identity_does_not_kill_reused_launcher_pid(self):
        self.identities[11] = self.record(11, 9999, self.python)
        self.assertEqual(launcher.run_supervisor("Data", 10101), 0)
        self.assertNotIn(11, self.terminated)

    def test_role_command_mismatch_refuses(self):
        self.rows[22]["argv"][-1] = str(self.base / "unrelated.py")
        self.assert_refused()

    def test_script_basename_in_different_directory_refuses(self):
        self.rows[22]["argv"][-1] = str(self.base / "elsewhere" / "binance_usdm_server.py")
        self.assert_refused()

    def test_unreadable_command_refuses(self):
        self.rows[22]["argv"] = []
        self.assert_refused()

    def test_unrelated_descendant_refuses_entire_cleanup(self):
        self.rows[32]["argv"][-1] = str(self.base / "unrelated.py")
        self.assert_refused()

    def test_grandchild_refuses(self):
        self.add_process(self.record(70, 400, self.python), 32, "binance_usdm_server.py")
        self.assert_refused()

    def test_unrelated_python_and_broker_survive(self):
        self.assertEqual(launcher.run_supervisor("Data", 10101), 0)
        self.assertIn(80, self.identities)
        self.assertIn(90, self.identities)
        self.assertNotIn(80, self.terminated)
        self.assertNotIn(90, self.terminated)

    def test_recorded_broker_preserved(self):
        self.data["processes"]["amibroker"] = self.identities[90]
        self.data["amibroker"] = 90
        self.rows[90]["parent"] = 11
        self.write()
        self.assertEqual(launcher.run_supervisor("Data", 10101), 0)
        self.assertIn(90, self.identities)

    def test_stale_broker_child_refuses(self):
        self.data["processes"]["amibroker"] = dict(self.identities[90], creationTime100ns=1)
        self.data["amibroker"] = 90
        self.rows[90]["parent"] = 11
        self.write()
        self.assertEqual(launcher.process_record_status(self.data["processes"]["amibroker"]), "STALE")
        self.assertIsNone(launcher.inspect_orphaned_cohort(self.data, "Data", 10101))
        self.assert_refused()
        self.pins.assert_not_called()

    def broker_reuse(self, status, *, dead_services=False, child=False):
        self.data["processes"]["amibroker"] = copy.deepcopy(self.identities[90])
        self.data["amibroker"] = 90
        if dead_services:
            for pid in (21, 22, 23, 31, 32, 33):
                self.rows.pop(pid)
                self.identities.pop(pid)
        if status == "DEAD":
            self.rows.pop(90)
            self.identities.pop(90)
        else:
            self.rows[90]["parent"] = 11 if child else 999
            if status != "MATCH":
                self.identities[90] = dict(self.identities[90], creationTime100ns=9999)
                self.rows[90]["created"] = 9999
                if not child:
                    self.rows[90]["executable"] = str(self.base / "svchost.exe")
                    self.identities[90]["executable"] = self.rows[90]["executable"]
            if status == "AMBIGUOUS":
                self.patch(launcher, "process_identity", side_effect=lambda pid:
                           None if pid == 90 else copy.deepcopy(self.identities.get(pid)))
                self.assertTrue(launcher.pid_alive(90))
                self.assertIsNone(launcher.process_identity(90))
        self.write()
        self.assertEqual(launcher.process_record_status(self.data["processes"]["amibroker"]), status)

    def assert_reboot_recovery(self, status):
        self.broker_reuse(status, dead_services=True)
        self.assertEqual(self.classify(), launcher.LAUNCH_OWNERSHIP_ACQUIRED)
        plan = launcher.inspect_orphaned_cohort(self.data, "Data", 10101)
        self.assertEqual(plan.records, [])
        self.assertEqual(launcher.ensure_running("Data", 10101), 0)
        self.spawn.assert_called_once()
        self.pins.assert_not_called()
        self.assertEqual(self.terminated, [])

    def test_reboot_broker_ambiguous_unrelated_pid_reuse(self):
        self.assert_reboot_recovery("AMBIGUOUS")
        self.assertIn(90, self.identities)

    def test_reboot_broker_stale_unrelated_pid_reuse(self):
        self.assert_reboot_recovery("STALE")
        self.assertIn(90, self.identities)

    def test_reboot_dead_broker_record(self):
        self.assert_reboot_recovery("DEAD")

    def test_ambiguous_broker_child_basename_does_not_prove_ownership(self):
        self.broker_reuse("AMBIGUOUS", child=True)
        self.assertEqual(Path(self.rows[90]["executable"]).name.lower(), "broker.exe")
        self.assertIsNone(launcher.inspect_orphaned_cohort(self.data, "Data", 10101))
        self.assertEqual(self.classify(), launcher.LAUNCH_OWNERSHIP_LIVE_AMBIGUOUS)
        self.assert_refused()
        self.pins.assert_not_called()

    def assert_broker_preserved_during_cleanup(self, status):
        self.broker_reuse(status, child=status == "MATCH")
        self.assertEqual(self.classify(), launcher.LAUNCH_OWNERSHIP_ORPHANED_MANAGED_COHORT)
        plan = launcher.inspect_orphaned_cohort(self.data, "Data", 10101)
        expected = {21, 22, 23, 31, 32, 33}
        expected.update(pid for pid in (41, 42, 43) if pid in self.rows)
        self.assertEqual({r["pid"] for r in plan.records}, expected)
        self.assertEqual(launcher.run_supervisor("Data", 10101), 0)
        self.assertEqual(set(self.terminated), expected)
        self.assertEqual({c.args[0]["pid"] for c in self.pins.call_args_list}, expected)
        self.assertIn(90, self.identities)
        self.assertIn(90, self.rows)

    def test_live_orphans_ambiguous_broker_reuse_preserved(self):
        self.assert_broker_preserved_during_cleanup("AMBIGUOUS")

    def test_live_orphans_stale_broker_reuse_preserved(self):
        self.assert_broker_preserved_during_cleanup("STALE")

    def test_matched_broker_child_never_pinned(self):
        self.assert_broker_preserved_during_cleanup("MATCH")

    def test_malformed_broker_records_still_refuse(self):
        valid = copy.deepcopy(self.identities[90])
        for record in (None, {}, dict(valid, pid=0), dict(valid, creationTime100ns=0),
                       dict(valid, executable="Broker.exe"), dict(valid, pid=21)):
            with self.subTest(record=record):
                self.data["processes"]["amibroker"] = record
                self.data["amibroker"] = 90
                self.write()
                self.assert_refused()

    def test_pause_no_cleanup_or_spawn(self):
        launcher.PAUSEFILE.touch()
        self.assertEqual(launcher.ensure_running("Data", 10101), 0)
        self.spawn.assert_not_called()
        self.assertFalse(self.terminated)

    def test_pause_arriving_after_adjudication_prevents_cleanup(self):
        ownership, lock = launcher.claim_launcher_ownership("Data", 10101)
        self.assertEqual(ownership, launcher.LAUNCH_OWNERSHIP_ORPHANED_MANAGED_COHORT)
        try:
            launcher.PAUSEFILE.touch()
            self.assertEqual(launcher.start_owned_supervisor("Data", "127.0.0.1", 10101, lock, recovering=True), 0)
        finally:
            lock.release()
        self.assertFalse(self.terminated)

    def test_concurrent_ensure_only_one_cleanup_start_winner(self):
        barrier = threading.Barrier(2)
        loser_finished = threading.Event()
        def spawn(*args, **kwargs):
            barrier.wait(timeout=5)
            result = launcher.run_supervisor("Data", 10101)
            if result == 3:
                loser_finished.set()
            return SimpleNamespace(pid=777)
        def supervise(*args):
            self.assertTrue(loser_finished.wait(5))
            self.assertTrue(self.lock_class.held)
            return 0
        self.spawn.side_effect = spawn
        self.supervise.side_effect = supervise
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: launcher.ensure_running("Data", 10101), range(2)))
        self.assertEqual(results, [0, 0])
        self.assertEqual(len(self.terminated), 6)
        self.supervise.assert_called_once()

    def test_cleanup_timeout_retains_pid_evidence_no_start(self):
        self.timeout_pid = 32
        self.assertEqual(launcher.run_supervisor("Data", 10101), 4)
        self.supervise.assert_not_called()
        self.assertEqual(launcher.PIDFILE.read_bytes(), self.original)

    def test_partial_cleanup_failure_retains_evidence_no_start(self):
        self.fail_pid = 22
        self.assertEqual(launcher.run_supervisor("Data", 10101), 4)
        self.assertEqual(self.terminated, [21, 31])
        self.supervise.assert_not_called()
        self.assertEqual(launcher.PIDFILE.read_bytes(), self.original)
        self.assertFalse(self.lock_class.held)

    def test_malformed_pid_json_refuses(self):
        launcher.PIDFILE.write_text("{broken")
        self.assert_refused()

    def test_malformed_nonce_refuses(self):
        self.data["launchNonce"] = "owner"
        self.write()
        self.assert_refused()

    def test_instance_mismatch_refuses(self):
        for field, value in (("dbname", "ASTU_DEMO"), ("relay_port", 10102)):
            with self.subTest(field=field):
                old = self.data[field]
                self.data[field] = value
                self.write()
                self.assert_refused()
                self.data[field] = old

    def test_missing_role_refuses_partial_cohort(self):
        self.data["processes"].pop("identity")
        self.write()
        self.assert_refused()

    def test_unknown_role_refuses(self):
        self.data["processes"]["extra"] = self.identities[80]
        self.data["extra"] = 80
        self.write()
        self.assert_refused()

    def test_unexpected_live_service_outside_tree_refuses(self):
        self.add_process(self.record(70, 400, self.python), 999, "binance_usdm_server.py")
        self.assert_refused()

    def test_dead_shim_with_surviving_base_child_refuses(self):
        self.identities.pop(22)
        self.rows.pop(22)
        self.assert_refused()

    def test_metadata_snapshot_failure_refuses(self):
        self.patch(recovery, "process_snapshot", side_effect=OSError("denied"))
        self.assert_refused()

    def test_pid_reuse_between_inspection_and_pinning_refuses(self):
        original_pin = self.pins.side_effect
        def pin(record):
            if record["pid"] == 22:
                self.identities[22] = dict(record, creationTime100ns=9999)
            return original_pin(record)
        self.pins.side_effect = pin
        self.assertEqual(launcher.run_supervisor("Data", 10101), 4)
        self.assertFalse(self.terminated)
        self.assertEqual(launcher.PIDFILE.read_bytes(), self.original)

    def test_pidfile_changed_before_cleanup_refuses(self):
        original_pin = self.pins.side_effect
        def pin(record):
            handle = original_pin(record)
            self.data["launchNonce"] = "b" * 32
            self.write()
            return handle
        self.pins.side_effect = pin
        self.assertEqual(launcher.run_supervisor("Data", 10101), 4)
        self.assertFalse(self.terminated)
        self.supervise.assert_not_called()

    def test_mutex_busy_no_cleanup(self):
        self.lock_class.held = True
        self.assertEqual(launcher.run_supervisor("Data", 10101), 3)
        self.assertFalse(self.terminated)

    def test_stop_provenance_not_written(self):
        self.assertEqual(launcher.run_supervisor("Data", 10101), 0)
        self.provenance.assert_not_called()
        self.assertFalse((self.base / "stop_provenance.jsonl").exists())
        self.assertFalse(launcher.PAUSEFILE.exists())

    def test_fresh_pid_publication_failure_releases_lock(self):
        self.patch(launcher, "save_pids", side_effect=OSError("disk full"))
        with self.assertRaises(OSError):
            launcher.run_supervisor("Data", 10101)
        self.assertEqual(launcher.PIDFILE.read_bytes(), self.original)
        self.assertFalse(self.lock_class.held)
        self.supervise.assert_not_called()

    def test_each_verified_surviving_role_can_recover(self):
        original_rows = copy.deepcopy(self.rows)
        original_ids = copy.deepcopy(self.identities)
        for survivor in (21, 22, 23):
            with self.subTest(survivor=survivor):
                self.rows = copy.deepcopy(original_rows)
                self.identities = copy.deepcopy(original_ids)
                for pid in (21, 22, 23):
                    if pid != survivor:
                        for gone in (pid, pid + 10):
                            self.rows.pop(gone)
                            self.identities.pop(gone)
                self.assertEqual(self.classify(), launcher.LAUNCH_OWNERSHIP_ORPHANED_MANAGED_COHORT)

    def test_new_descendant_during_cleanup_prevents_start(self):
        original_pin = self.pins.side_effect
        def pin(record):
            handle = original_pin(record)
            terminate = handle.terminate
            def with_new_descendant():
                terminate()
                if record["pid"] == 22:
                    self.add_process(self.record(71, 500, self.python), 22, "binance_usdm_server.py")
            handle.terminate = with_new_descendant
            return handle
        self.pins.side_effect = pin
        self.assertEqual(launcher.run_supervisor("Data", 10101), 4)
        self.supervise.assert_not_called()
        self.assertEqual(launcher.PIDFILE.read_bytes(), self.original)

    def test_existing_broker_is_not_restarted_by_fresh_supervisor(self):
        # Exercise the real startup loop, with every external operation faked.
        self.supervise.side_effect = None
        broker = self.base / "Broker.exe"
        broker.touch()
        request = self.base / "stop.request"
        request.touch()
        children = [SimpleNamespace(pid=pid, poll=lambda: 0) for pid in (21, 22, 23)]
        self.spawn.side_effect = children
        self.patch(launcher, "wait_port", return_value=True)
        self.patch(launcher, "process_name_running", return_value=True)
        self.patch(launcher, "save_pids")
        self.patch(launcher.signal, "signal")
        self.patch(launcher.time, "sleep")
        self.scope.enter_context(mock.patch.dict(launcher.CFG["launcher"], {
            "start_amibroker": True, "keep_amibroker_running": True,
            "amibroker_exe": str(broker), "amibroker_start_delay_seconds": 0,
        }))
        # Retrieve the original function replaced in setUp.
        real_loop = self.supervise._mock_wraps
        self.assertIsNone(real_loop)
        self.assertEqual(REAL_SUPERVISOR_LOOP(
            "Data", "127.0.0.1", 10101, "fake-lock", request, "b" * 32,
            self.identities[os.getpid()]), 0)
        self.assertEqual(self.spawn.call_count, 3)
        self.assertTrue(all("Broker.exe" not in str(call) for call in self.spawn.call_args_list))


class P1RegressionTests(unittest.TestCase):
    # Reuse the isolated fixture and helpers, not its existing test methods.
    setUp = OrphanRecoveryTests.setUp
    patch = OrphanRecoveryTests.patch
    record = OrphanRecoveryTests.record
    add_process = OrphanRecoveryTests.add_process
    write = OrphanRecoveryTests.write
    classify = OrphanRecoveryTests.classify
    assert_refused = OrphanRecoveryTests.assert_refused

    def dead_except(self, survivor=None):
        for pid in (21, 22, 23):
            if pid != survivor:
                for gone in (pid, pid + 10):
                    self.rows.pop(gone, None)
                    self.identities.pop(gone, None)

    def missing_flat_live(self, role):
        survivor = self.data[role]
        del self.data["processes"][role]
        self.dead_except(survivor)
        self.write()
        self.assert_refused()
        self.assertEqual(launcher.run_supervisor("Data", 10101), 4)
        self.supervise.assert_not_called()
        self.assertIn(survivor, self.identities)

    def test_p1_missing_relay_flat_live_exact_reproduction(self):
        self.missing_flat_live("relay")

    def test_p1_missing_server_flat_live(self):
        self.missing_flat_live("server")

    def test_p1_missing_identity_flat_live(self):
        self.missing_flat_live("identity")

    def test_p1_flat_pid_record_mismatch(self):
        self.data["relay"] = 80
        self.write()
        self.assert_refused()

    def test_p1_record_pid_flat_mismatch(self):
        self.data["processes"]["server"] = self.identities[80]
        self.write()
        self.assert_refused()

    def test_p1_record_without_flat_pid(self):
        del self.data["server"]
        self.write()
        self.assert_refused()

    def test_p1_missing_record_and_flat_discovered_service(self):
        del self.data["processes"]["relay"]
        del self.data["relay"]
        self.dead_except(21)
        self.write()
        self.assert_refused()

    def test_p1_dead_flat_pid_does_not_hide_discovered_service(self):
        del self.data["processes"]["relay"]
        self.data["relay"] = 9999
        self.dead_except(21)
        self.write()
        self.assert_refused()

    def absent_role_fixture(self):
        self.dead_except()
        del self.data["processes"]["relay"]
        del self.data["relay"]
        self.write()

    def test_p1_missing_role_apparent_absence_still_refuses(self):
        self.absent_role_fixture()
        snapshot = self.patch(recovery, "process_snapshot", return_value={})
        self.assert_refused()
        snapshot.assert_not_called()

    def test_partial_enumeration_cannot_authorize_incomplete_worker(self):
        self.dead_except(21)
        del self.data["processes"]["relay"]
        del self.data["relay"]
        self.write()
        before = launcher.PIDFILE.read_bytes()
        partial = {pid: row for pid, row in self.rows.items() if pid not in (21, 31)}
        self.assertTrue(partial)
        snapshot = self.patch(recovery, "process_snapshot", return_value=partial)
        self.assertEqual(launcher.run_supervisor("Data", 10101), 4)
        snapshot.assert_not_called()
        self.supervise.assert_not_called()
        self.spawn.assert_not_called()
        self.assertEqual(self.terminated, [])
        self.assertIn(21, self.identities)
        self.assertIn(31, self.identities)
        self.assertEqual(launcher.PIDFILE.read_bytes(), before)
        self.assertIsNone(launcher.inspect_orphaned_cohort(self.data, "Data", 10101))
        snapshot.assert_not_called()

    def test_each_missing_required_role_refuses_before_enumeration(self):
        original = copy.deepcopy(self.data)
        self.dead_except()
        snapshot = self.patch(recovery, "process_snapshot",
                              side_effect=AssertionError("must not enumerate incomplete state"))
        for role in recovery.SCRIPTS:
            for retain_flat in (True, False):
                with self.subTest(role=role, retain_flat=retain_flat):
                    self.data = copy.deepcopy(original)
                    del self.data["processes"][role]
                    if not retain_flat:
                        del self.data[role]
                    self.write()
                    self.assert_refused()
                    self.assertEqual(launcher.run_supervisor("Data", 10101), 4)
        snapshot.assert_not_called()

    def test_malformed_required_role_refuses_before_enumeration(self):
        self.data["processes"]["relay"] = {"pid": 21}
        self.write()
        snapshot = self.patch(recovery, "process_snapshot")
        self.assert_refused()
        snapshot.assert_not_called()

    def test_live_launcher_precedes_malformed_child_publication(self):
        self.identities[11] = self.data["processes"]["launcher"]
        self.data["processes"]["relay"] = {"pid": 21}
        self.write()
        snapshot = self.patch(recovery, "process_snapshot")
        self.assertEqual(self.classify(), launcher.LAUNCH_OWNERSHIP_ALREADY_RUNNING)
        self.assertEqual(launcher.ensure_running("Data", 10101), 0)
        snapshot.assert_not_called()
        self.spawn.assert_not_called()
        self.assertEqual(self.terminated, [])

    def test_complete_stale_child_identities_allow_recovery_without_killing_reused_pids(self):
        self.dead_except()
        for role in recovery.SCRIPTS:
            pid = self.data[role]
            self.add_process(self.record(pid, 9000, self.python), 999, "unrelated.py")
        self.assertEqual(self.classify(), launcher.LAUNCH_OWNERSHIP_ACQUIRED)
        self.assertEqual(launcher.run_supervisor("Data", 10101), 0)
        self.assertEqual(self.terminated, [])
        self.supervise.assert_called_once()

    def test_disabled_identity_role_is_not_required(self):
        self.dead_except()
        del self.data["processes"]["identity"]
        del self.data["identity"]
        self.write()
        with mock.patch.dict(launcher.CFG, {"identity_bridge": {"enabled": False}}):
            self.assertEqual(self.classify(), launcher.LAUNCH_OWNERSHIP_ACQUIRED)

    def test_p1_missing_role_inspection_throws(self):
        self.absent_role_fixture()
        self.patch(recovery, "process_snapshot", side_effect=OSError("unavailable"))
        self.assert_refused()

    def test_p1_missing_role_unreadable_metadata(self):
        self.absent_role_fixture()
        self.rows[80]["argv"] = []
        self.assert_refused()

    def test_p1_missing_role_relative_python_metadata_is_ambiguous(self):
        self.absent_role_fixture()
        self.rows[80]["argv"][2] = "wsrtd_relay.py"
        self.assert_refused()

    def test_p1_missing_role_unknown_executable_is_ambiguous(self):
        self.absent_role_fixture()
        self.rows[80]["executable"] = None
        self.assert_refused()

    def test_p1_live_launcher_incremental_publication_wins(self):
        self.identities[11] = self.data["processes"]["launcher"]
        self.data["processes"] = {"launcher": self.identities[11]}
        for role in recovery.SCRIPTS:
            del self.data[role]
        self.write()
        self.patch(recovery, "process_snapshot", side_effect=AssertionError("must not enumerate"))
        self.assertEqual(self.classify(), launcher.LAUNCH_OWNERSHIP_ALREADY_RUNNING)
        self.assertEqual(launcher.ensure_running("Data", 10101), 0)
        self.spawn.assert_not_called()
        self.assertEqual(self.terminated, [])

    def relative_script(self, script):
        # Reproduce the original cwd-based false acceptance, not merely an
        # incidental mismatch with the test runner's current directory.
        previous = os.getcwd()
        try:
            os.chdir(self.base)
            for pid in (22, 32):
                self.rows[pid]["argv"][2] = script
            self.assert_refused()
            self.assertEqual(self.classify(), launcher.LAUNCH_OWNERSHIP_LIVE_AMBIGUOUS)
        finally:
            os.chdir(previous)

    def test_p1_relative_basename_exact_reproduction(self):
        self.relative_script("binance_usdm_server.py")

    def test_p1_relative_dot_script(self):
        self.relative_script(r".\binance_usdm_server.py")

    def test_p1_relative_parent_script(self):
        self.relative_script(r"..\stack\binance_usdm_server.py")

    def test_p1_root_relative_script(self):
        self.relative_script(r"\binance_usdm_server.py")

    def test_p1_drive_relative_script(self):
        self.relative_script("C:binance_usdm_server.py")

    def test_p1_relative_executable_refuses(self):
        self.rows[22]["argv"][0] = "python.exe"
        self.assert_refused()

    def test_p1_script_substring_refuses(self):
        self.rows[22]["argv"][2] = str(self.base / "binance_usdm_server.py.backup")
        self.assert_refused()

    def test_p1_exact_absolute_paths_each_role(self):
        for survivor in (21, 22, 23):
            with self.subTest(role_pid=survivor):
                plan = launcher.inspect_orphaned_cohort(self.data, "Data", 10101)
                self.assertIsNotNone(plan)
                self.assertIn(survivor, plan.roots)

    def test_p1_case_variant_absolute_script(self):
        for pid in (21, 22, 23, 31, 32, 33):
            self.rows[pid]["argv"][2] = self.rows[pid]["argv"][2].upper()
        self.assertEqual(self.classify(), launcher.LAUNCH_OWNERSHIP_ORPHANED_MANAGED_COHORT)

    def test_p1_quoted_absolute_script_spaces(self):
        # Change only the synthetic BASE/script paths, preserving temp PID paths.
        spaced = self.base / "Stack With Spaces"
        self.patch(launcher, "BASE", spaced)
        self.data["working_directory"] = str(spaced)
        for role, script in recovery.SCRIPTS.items():
            for pid in (self.data[role], self.data[role] + 10):
                executable = self.rows[pid]["executable"]
                self.rows[pid]["argv"] = recovery.command_args(
                    launcher.subprocess.list2cmdline([executable, "-u", str(spaced / script)]))
        self.write()
        self.assertEqual(self.classify(), launcher.LAUNCH_OWNERSHIP_ORPHANED_MANAGED_COHORT)


class PortableConhostParserTests(unittest.TestCase):
    def test_device_prefix_and_case(self):
        expected = ntpath.normcase(r'C:\Windows\System32\conhost.exe')
        for value in (r'\??\C:\Windows\System32\conhost.exe', r'C:\WINDOWS\SYSTEM32\CONHOST.EXE'):
            self.assertEqual(recovery.conhost_argv_path(value), expected)
        for value in ('conhost.exe', r'\\?\C:\Windows\System32\conhost.exe', r'\Windows\System32\conhost.exe', r'C:conhost.exe', r'C:\Windows\..\Temp\conhost.exe'):
            self.assertIsNone(recovery.conhost_argv_path(value))
        # A lexical drive path can parse without identifying the trusted image.
        self.assertNotEqual(recovery.conhost_argv_path(r'\??\C:\Temp\conhost.exe'), expected)


class PortableDescendantTests(unittest.TestCase):
    setUp = OrphanRecoveryTests.setUp
    patch = OrphanRecoveryTests.patch
    record = OrphanRecoveryTests.record
    add_process = OrphanRecoveryTests.add_process
    write = OrphanRecoveryTests.write
    classify = OrphanRecoveryTests.classify
    assert_refused = OrphanRecoveryTests.assert_refused

    def test_root_only_and_base_python_only(self):
        self.assertEqual(self.classify(), launcher.LAUNCH_OWNERSHIP_ORPHANED_MANAGED_COHORT)
        for pid in (31, 32, 33):
            self.rows.pop(pid); self.identities.pop(pid)
        self.assertEqual(self.classify(), launcher.LAUNCH_OWNERSHIP_ORPHANED_MANAGED_COHORT)

    def test_portable_negative_siblings(self):
        rows, identities = copy.deepcopy(self.rows), copy.deepcopy(self.identities)
        for case in ('second_python', 'third_utility', 'unknown_python'):
            with self.subTest(case=case):
                self.rows, self.identities = copy.deepcopy(rows), copy.deepcopy(identities)
                self.assertEqual(self.classify(), launcher.LAUNCH_OWNERSHIP_ORPHANED_MANAGED_COHORT)
                if case == 'second_python':
                    self.add_process(self.record(71, 250, self.python), 21, 'wsrtd_relay.py')
                else:
                    executable = self.base / ('utility.exe' if case == 'third_utility' else 'python.exe')
                    self.add_process(self.record(71, 250, str(executable)), 21, None)
                    if case == 'third_utility':
                        self.add_process(self.record(72, 260, str(executable)), 21, None)
                # Portable expected system path only; no Windows drive strings
                # are normalized using the host filesystem in this fixture.
                with mock.patch.object(recovery, 'trusted_conhost_path',
                                       return_value=recovery.normalized(self.base / 'system' / 'conhost.exe')):
                    self.assertIsNone(launcher.inspect_orphaned_cohort(self.data, 'Data', 10101))
                    self.assertEqual(self.classify(), launcher.LAUNCH_OWNERSHIP_LIVE_AMBIGUOUS)
                    self.assert_refused()
                    self.assertEqual(launcher.run_supervisor('Data', 10101), 4)
                    self.pins.assert_not_called()
                    self.supervise.assert_not_called()


@unittest.skipUnless(os.name == 'nt', 'Windows conhost topology and executable path semantics')
class ConhostTests(unittest.TestCase):
    broker_reuse = OrphanRecoveryTests.broker_reuse
    assert_broker_preserved_during_cleanup = OrphanRecoveryTests.assert_broker_preserved_during_cleanup
    test_live_orphans_ambiguous_broker_reuse_preserved = OrphanRecoveryTests.test_live_orphans_ambiguous_broker_reuse_preserved
    test_live_orphans_stale_broker_reuse_preserved = OrphanRecoveryTests.test_live_orphans_stale_broker_reuse_preserved
    patch = OrphanRecoveryTests.patch
    record = OrphanRecoveryTests.record
    add_process = OrphanRecoveryTests.add_process
    write = OrphanRecoveryTests.write
    classify = OrphanRecoveryTests.classify
    assert_refused = OrphanRecoveryTests.assert_refused

    def setUp(self):
        OrphanRecoveryTests.setUp(self)
        self.conhost = recovery.normalized(Path('C:/Windows/System32/conhost.exe'))
        self.patch(recovery, 'trusted_conhost_path', return_value=self.conhost)
        # Observed Windows topology: venv root -> base Python + system conhost.
        # Console hosts are optional, not universal; no live PID is used here.
        for root in (21, 22, 23):
            self.host(root + 20, root)

    def host(self, pid, parent):
        rec = self.record(pid, self.identities[parent]['creationTime100ns'] + 3, self.conhost)
        self.add_process(rec, parent, None)
        self.rows[pid]['argv'] = ['\\??\\' + self.conhost, '0x4']

    def test_live_topology_and_cleanup_plan(self):
        self.assertEqual(self.classify(), launcher.LAUNCH_OWNERSHIP_ORPHANED_MANAGED_COHORT)
        plan = launcher.inspect_orphaned_cohort(self.data, 'Data', 10101)
        self.assertEqual(plan.roots, [21, 22, 23])
        expected = {21, 22, 23, 31, 32, 33, 41, 42, 43}
        self.assertEqual({r['pid'] for r in plan.records}, expected)
        self.assertEqual(launcher.run_supervisor('Data', 10101), 0)
        self.assertEqual(set(self.terminated), expected)
        self.assertEqual({c.args[0]['pid'] for c in self.pins.call_args_list}, expected)
        self.assertTrue({80, 90} <= self.identities.keys())

    def test_optional_descendant_sets(self):
        original_rows, original_ids = copy.deepcopy(self.rows), copy.deepcopy(self.identities)
        for keep in (set(), {'python'}, {'conhost'}, {'python', 'conhost'}):
            with self.subTest(keep=keep):
                self.rows, self.identities = copy.deepcopy(original_rows), copy.deepcopy(original_ids)
                for root in (21, 22, 23):
                    for kind, pid in (('python', root + 10), ('conhost', root + 20)):
                        if kind not in keep:
                            self.rows.pop(pid); self.identities.pop(pid)
                self.assertEqual(self.classify(), launcher.LAUNCH_OWNERSHIP_ORPHANED_MANAGED_COHORT)

    def test_negative_console_predicates(self):
        rows, ids = copy.deepcopy(self.rows), copy.deepcopy(self.identities)
        def row(key, value): self.rows[41][key] = value
        def native(**values): self.identities[41].update(values)
        def outsider():
            path = recovery.normalized(self.base / 'conhost.exe')
            row('executable', path); native(executable=path); row('argv', [path, '0x4'])
        def second_host():
            self.rows.pop(31); self.identities.pop(31)
            self.host(71, 21)
        def second_python():
            self.rows.pop(41); self.identities.pop(41)
            self.add_process(self.record(71, 250, self.python), 21, 'wsrtd_relay.py')
        # Per-case portability audit (18 cases). The five PORTABLE cases also
        # run without this Windows fixture in the two portable classes above.
        # Remaining cases need a valid conhost topology as their positive control.
        portability = {
            'second_conhost': 'WINDOWS_ONLY', 'second_python': 'PORTABLE',
            'third_utility': 'PORTABLE', 'outside_system': 'WINDOWS_ONLY',
            'native_pid_mismatch': 'WINDOWS_ONLY', 'native_time_mismatch': 'WINDOWS_ONLY',
            'native_executable_mismatch': 'WINDOWS_ONLY', 'older_than_root': 'WINDOWS_ONLY',
            'empty_argv': 'WINDOWS_ONLY', 'malformed_argv': 'WINDOWS_ONLY',
            'wrong_argv0': 'PORTABLE', 'nonhex_token': 'WINDOWS_ONLY',
            'empty_hex_token': 'WINDOWS_ONLY', 'extra_argument': 'WINDOWS_ONLY',
            'grandchild': 'WINDOWS_ONLY', 'identity_unavailable': 'WINDOWS_ONLY',
            'unknown_python': 'PORTABLE', 'basename_only': 'PORTABLE',
        }
        cases = {
            'second_conhost': second_host,
            'second_python': second_python,
            'third_utility': lambda: self.add_process(self.record(71, 250, str(self.base/'utility.exe')), 21, None),
            'outside_system': outsider,
            'native_pid_mismatch': lambda: native(pid=999),
            'native_time_mismatch': lambda: native(creationTime100ns=999),
            'native_executable_mismatch': lambda: native(executable=str(self.base/'other.exe')),
            'older_than_root': lambda: (native(creationTime100ns=190), row('created', 190)),
            'empty_argv': lambda: row('argv', []),
            'malformed_argv': lambda: row('argv', None),
            'wrong_argv0': lambda: row('argv', [r'\??\C:\Temp\conhost.exe', '0x4']),
            'nonhex_token': lambda: row('argv', [self.conhost, '0xG']),
            'empty_hex_token': lambda: row('argv', [self.conhost, '0x']),
            'extra_argument': lambda: row('argv', [self.conhost, '0x4', 'extra']),
            'grandchild': lambda: self.add_process(self.record(71, 250, self.python), 41, 'wsrtd_relay.py'),
            'identity_unavailable': lambda: self.identities.pop(41),
            'unknown_python': lambda: self.add_process(self.record(71, 250, str(self.base/'python.exe')), 21, 'wsrtd_relay.py'),
            'basename_only': lambda: row('argv', ['conhost.exe', '0x4']),
        }
        self.assertEqual(set(cases), set(portability))
        for name, mutate in cases.items():
            with self.subTest(case=name):
                self.rows, self.identities = copy.deepcopy(rows), copy.deepcopy(ids)
                mutate()
                self.assertIsNone(launcher.inspect_orphaned_cohort(self.data, 'Data', 10101))
                self.assertEqual(self.classify(), launcher.LAUNCH_OWNERSHIP_LIVE_AMBIGUOUS)
                self.assert_refused()
                self.assertEqual(launcher.run_supervisor('Data', 10101), 4)
                self.supervise.assert_not_called()
                self.pins.assert_not_called()

    def test_unrelated_console_is_not_a_cleanup_target(self):
        self.rows[41]['parent'] = 999
        plan = launcher.inspect_orphaned_cohort(self.data, 'Data', 10101)
        self.assertIsNotNone(plan)
        self.assertNotIn(41, {r['pid'] for r in plan.records})

    def test_system_directory_lookup_failure_refuses(self):
        self.patch(recovery, 'trusted_conhost_path', side_effect=OSError('unavailable'))
        self.assert_refused()

    def test_identity_changes_during_console_validation(self):
        original = launcher.process_identity.side_effect
        calls = 0
        def changed(pid):
            nonlocal calls
            rec = original(pid)
            if pid == 41:
                calls += 1
                if calls > 1: rec['creationTime100ns'] += 100
            return rec
        self.patch(launcher, 'process_identity', side_effect=changed)
        self.assertIsNone(launcher.inspect_orphaned_cohort(self.data, 'Data', 10101))
        self.assertFalse(self.terminated)

    def test_device_prefix_and_case(self):
        for pid in (41, 42, 43): self.rows[pid]['argv'][0] = self.rows[pid]['argv'][0].upper()
        self.assertIsNotNone(launcher.inspect_orphaned_cohort(self.data, 'Data', 10101))

    def test_pin_failure_before_any_termination(self):
        pin = self.pins.side_effect
        def fail(record):
            if record['pid'] == 41: raise OSError('console pin denied')
            return pin(record)
        self.pins.side_effect = fail
        self.assertEqual(launcher.run_supervisor('Data', 10101), 4)
        self.assertEqual(self.terminated, [])
        self.supervise.assert_not_called()
        self.assertEqual(launcher.PIDFILE.read_bytes(), self.original)

    def test_conhost_termination_failure(self):
        self.fail_pid = 41
        self.assertEqual(launcher.run_supervisor('Data', 10101), 4)
        self.supervise.assert_not_called()
        self.assertEqual(launcher.PIDFILE.read_bytes(), self.original)

    def test_conhost_wait_timeout(self):
        self.timeout_pid = 41
        self.assertEqual(launcher.run_supervisor('Data', 10101), 4)
        self.supervise.assert_not_called()
        self.assertEqual(launcher.PIDFILE.read_bytes(), self.original)

    def test_new_descendant_during_conhost_cleanup(self):
        pin = self.pins.side_effect
        def wrapped(record):
            handle = pin(record); terminate = handle.terminate
            def changed():
                terminate()
                if record['pid'] == 41:
                    self.add_process(self.record(71, 500, self.python), 21, 'wsrtd_relay.py')
            handle.terminate = changed
            return handle
        self.pins.side_effect = wrapped
        self.assertEqual(launcher.run_supervisor('Data', 10101), 4)
        self.supervise.assert_not_called()
        self.assertEqual(launcher.PIDFILE.read_bytes(), self.original)


REAL_SUPERVISOR_LOOP = launcher.run_supervisor_locked


class WindowsHandleTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows system-directory API')
    def test_trusted_conhost_uses_system_api(self):
        api = mock.MagicMock()
        def directory(buffer, size):
            buffer.value = r'C:\Windows\System32'
            return len(buffer.value)
        api.GetSystemDirectoryW.side_effect = directory
        with mock.patch.object(recovery.ctypes, 'WinDLL', return_value=api):
            self.assertEqual(recovery.trusted_conhost_path(),
                             recovery.normalized(r'C:\Windows\System32\conhost.exe'))
        api.GetSystemDirectoryW.assert_called_once()

    @unittest.skipUnless(os.name == 'nt', 'Windows system-directory API')
    def test_trusted_conhost_api_failure_and_truncation(self):
        for size in (0, 32768):
            api = mock.MagicMock()
            api.GetSystemDirectoryW.return_value = size
            with mock.patch.object(recovery.ctypes, 'WinDLL', return_value=api):
                with self.assertRaises(OSError): recovery.trusted_conhost_path()

    def kernel(self, *, created=200, executable=None):
        api = mock.MagicMock()
        api.OpenProcess.return_value = 123
        api.WaitForSingleObject.return_value = 258
        api.TerminateProcess.return_value = True
        executable = executable or str(Path("C:/fake/python.exe"))
        def image(handle, flags, buffer, size):
            buffer.value = executable
            return True
        def times(handle, start, *rest):
            start._obj.dwHighDateTime = 0
            start._obj.dwLowDateTime = created
            return True
        api.QueryFullProcessImageNameW.side_effect = image
        api.GetProcessTimes.side_effect = times
        return api, {"pid": 1234, "creationTime100ns": 200,
                     "executable": recovery.normalized(executable)}

    def test_pinned_handle_checks_identity_and_terminates_same_handle(self):
        api, record = self.kernel()
        with mock.patch.object(recovery.ctypes, "WinDLL", return_value=api):
            pinned = recovery._PinnedProcess(record)
            pinned.terminate()
            api.TerminateProcess.assert_called_once_with(123, 1)
            api.WaitForSingleObject.return_value = 0
            self.assertTrue(pinned.wait(1))
            pinned.close()
            api.CloseHandle.assert_called_once_with(123)

    def test_native_creation_mismatch_closes_without_termination(self):
        api, record = self.kernel(created=999)
        with mock.patch.object(recovery.ctypes, "WinDLL", return_value=api):
            with self.assertRaises(OSError):
                recovery._PinnedProcess(record)
        api.TerminateProcess.assert_not_called()
        api.CloseHandle.assert_called_once_with(123)

    def test_signaled_process_object_is_not_live_identity(self):
        api, record = self.kernel()
        api.WaitForSingleObject.return_value = 0
        with mock.patch.object(recovery.ctypes, "WinDLL", return_value=api):
            self.assertIsNone(launcher.process_identity(record["pid"]))
        api.CloseHandle.assert_called_once_with(123)

    def test_windows_command_parser_preserves_quoted_absolute_script(self):
        args = recovery.command_args('"C:\\Python Dir\\python.exe" -u "D:\\Stack Dir\\wsrtd_relay.py"')
        self.assertEqual(args, [r"C:\Python Dir\python.exe", "-u", r"D:\Stack Dir\wsrtd_relay.py"])


if __name__ == "__main__":
    unittest.main()
