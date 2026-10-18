import argparse
import asyncio
import ast
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from Binance import sender
from Binance.rest_telemetry import RestTelemetry
from Binance import telemetry_export as ex
from test_rest_pacing_r6a import ExactClock, Session

ROOT=Path(__file__).resolve().parents[1]


class ActivationTests(unittest.TestCase):
    def args(self,*values):
        p=argparse.ArgumentParser();ex.add_arguments(p);return p.parse_args(values)

    def test_default_disabled(self):
        self.assertIsNone(ex.config_from_args(self.args()))

    def test_explicit_enabled(self):
        c=ex.config_from_args(self.args('--rest-telemetry','--telemetry-output',str(ROOT/'evidence/example-export')))
        self.assertEqual(c.capacity,4096);self.assertEqual(c.max_files,32)

    def test_missing_output_and_relative_path_rejected(self):
        for values in [('--rest-telemetry',),('--rest-telemetry','--telemetry-output','relative')]:
            with self.assertRaises(ValueError):ex.config_from_args(self.args(*values))

    def test_resource_bounds_and_nan_rejected(self):
        for name,value in [('capacity',4097),('queue_capacity',5),('max_files',2),('max_files',33),('max_file_bytes',4095),('cadence',float('nan')),('drain_seconds',11),('duration_seconds',901)]:
            with self.assertRaises(ValueError):ex.ExportConfig(ROOT/'evidence/x',**{name:value}).validate()

    def test_generation_options_validate(self):
        with self.assertRaises(ValueError):ex.ExportConfig(ROOT/'evidence/x',supervisor_generation='not-a-uuid').validate()

    def test_disabled_does_not_touch_output(self):
        with patch.object(Path,'mkdir',side_effect=AssertionError('disabled IO')):
            self.assertIsNone(ex.config_from_args(self.args('--telemetry-output',str(ROOT/'evidence/unused'))))

    def test_direct_script_supervisor_compatible_help(self):
        result=subprocess.run([sys.executable,'-B',str(ROOT/'Binance/sender.py'),'--help'],cwd=ROOT,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('--rest-telemetry',result.stdout)

    def test_versioned_schema_rejects_secret_extra(self):
        s=RestTelemetry().snapshot();s['token']='PRIVATE'
        with self.assertRaises(ValueError):ex.validate_snapshot(s)

    def test_malformed_snapshot_and_headers(self):
        r=RestTelemetry();t=r.begin('/fapi/v1/klines',{'limit':499},'HISTORY',0);r.finish(t)
        s=r.snapshot();s['records'][0]['used_weight']['Authorization']='PRIVATE'
        with self.assertRaises(ValueError):ex.validate_snapshot(s)

    def test_missing_sender_generation_is_not_valid_schema(self):
        s=RestTelemetry().snapshot();s['sender_generation']=None
        with self.assertRaises(ValueError):ex.validate_snapshot(s)

    def test_huge_numeric_input_rejected_without_overflow(self):
        self.assertFalse(ex.number(10**400))
        s=RestTelemetry().snapshot();s['pid']=10**400
        with self.assertRaises(ValueError):ex.validate_snapshot(s)

    def test_schema_captures_missing_headers_and_supervisor(self):
        r=RestTelemetry();t=r.begin('/fapi/v1/exchangeInfo',{},'STARTUP',0);r.response(t,200,{},None);r.finish(t)
        s=ex.validate_snapshot(r.snapshot())
        self.assertEqual(s['supervisor_generation_confidence'],'UNAVAILABLE')
        self.assertTrue(all(x is None for x in s['records'][0]['used_weight'].values()))

    def test_rc2_supervisor_has_no_maintenance_activation(self):
        source=(ROOT/'Benchmarks/supervise_test_feed.py').read_text()
        self.assertNotIn('supervisor_maintenance',source)
        self.assertNotIn('windows_fixture_adapter',source)


class ExportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        asyncio.get_running_loop().set_debug(False)
        self.tmp=tempfile.TemporaryDirectory(dir=Path(os.environ['RC2_OUTPUT'])/'test-tmp');self.base=Path(self.tmp.name)
    async def asyncTearDown(self):self.tmp.cleanup()

    def setup_export(self,**kwargs):
        r=RestTelemetry(monotonic_ns=lambda:1000000000,utc_ns=lambda:1791849600000000000)
        t=r.begin('/fapi/v1/klines',{'limit':499},'MINUTE_REPAIR',0,True);r.response(t,200,{},None);r.finish(t)
        e=ex.SnapshotExporter(ex.ExportConfig(self.base/'capture',cadence=.05,**kwargs),r)
        return r,e

    async def test_graceful_export_and_ack_required(self):
        r,e=self.setup_export();e.start();e.submit(r.snapshot());closed=await e.close(r.snapshot())
        self.assertTrue(closed['complete']);self.assertTrue(ex.inspect_export(e.config.output)['complete'])
        self.assertTrue(ex.inspect_export(e.config.output,closed['ack'])['complete'])

    async def test_output_collision_preserves_old_bytes(self):
        r,e=self.setup_export();e.config.output.mkdir();(e.config.output/'original').write_bytes(b'keep')
        e.start();result=await e.close(r.snapshot())
        self.assertFalse(result['complete']);self.assertEqual((e.config.output/'original').read_bytes(),b'keep')

    async def test_duplicate_generation_same_output_rejected(self):
        r,e=self.setup_export();e.start();first=await e.close(r.snapshot())
        original={p.name:p.read_bytes() for p in e.config.output.iterdir()}
        other=ex.SnapshotExporter(e.config,r);other.start();second=await other.close(r.snapshot())
        self.assertTrue(first['complete']);self.assertFalse(second['complete'])
        self.assertEqual(original,{p.name:p.read_bytes() for p in e.config.output.iterdir()})
        self.assertNotEqual(e.session,other.session)

    async def test_multiple_generations_never_overwrite(self):
        outputs=[]
        for i in range(2):
            r=RestTelemetry();e=ex.SnapshotExporter(ex.ExportConfig(self.base/f'gen{i}'),r);e.start()
            self.assertTrue((await e.close(r.snapshot()))['complete']);outputs.append(json.loads((e.config.output/'session.json').read_text()))
        self.assertNotEqual(outputs[0]['sender_generation'],outputs[1]['sender_generation'])

    async def test_repeated_generation_across_output_directories_detected(self):
        r=RestTelemetry();directories=[]
        for i in range(2):
            e=ex.SnapshotExporter(ex.ExportConfig(self.base/f'repeated{i}'),r);e.start()
            await e.close(r.snapshot());directories.append(e.config.output)
        result=ex.inspect_sessions(directories)
        self.assertTrue(result['duplicate_generation_detected']);self.assertFalse(result['aggregate_public_ip_acceptance'])

    async def test_permission_error_is_contained(self):
        r,e=self.setup_export()
        with patch.object(e,'_write',side_effect=PermissionError('PRIVATE')):
            e.start();closed=await e.close(r.snapshot())
        self.assertFalse(closed['complete']);self.assertEqual(e.errors,1)

    async def test_disk_full_is_contained(self):
        r,e=self.setup_export()
        with patch.object(e,'_write',side_effect=OSError(28,'PRIVATE')):
            e.start();closed=await e.close(r.snapshot())
        self.assertFalse(closed['complete']);self.assertEqual(e.errors,1)

    async def test_queue_overflow_bounded(self):
        r,e=self.setup_export(queue_capacity=1)
        self.assertTrue(e.submit(r.snapshot()))
        for _ in range(30):self.assertFalse(e.submit(r.snapshot()))
        self.assertEqual(e._queue.qsize(),1);self.assertEqual(e.dropped,30)
        e.start();closed=await e.close(r.snapshot())
        self.assertFalse(ex.inspect_export(e.config.output,closed['ack'])['complete'])

    async def test_retention_exhaustion_and_hard_bytes_bound(self):
        r,e=self.setup_export(max_files=4,max_file_bytes=4096,queue_capacity=4)
        for _ in range(4):e.submit(r.snapshot())
        e.start();closed=await e.close(r.snapshot())
        self.assertGreater(e.retention_dropped,0)
        self.assertLessEqual(len(list(e.config.output.iterdir())),4)
        self.assertLessEqual(sum(p.stat().st_size for p in e.config.output.iterdir()),4*4096)
        self.assertFalse(ex.inspect_export(e.config.output,closed['ack'])['complete'])

    async def test_oversize_snapshot_does_not_exceed_file_bound(self):
        r,e=self.setup_export(max_file_bytes=4096)
        for _ in range(10):t=r.begin('/fapi/v1/exchangeInfo',{},'STARTUP',0);r.finish(t)
        e.start();closed=await e.close(r.snapshot())
        self.assertFalse(closed['complete']);self.assertTrue(all(p.stat().st_size<=4096 for p in e.config.output.iterdir()))

    async def test_writer_blocked_drain_is_bounded_and_no_late_ack(self):
        r,e=self.setup_export(drain_seconds=.05);started=threading.Event();release=threading.Event();original=e._write
        def slow(*a):started.set();release.wait(2);return original(*a)
        with patch.object(e,'_write',side_effect=slow):
            e.start()
            for _ in range(100):
                if started.is_set():break
                await asyncio.sleep(.001)
            before=time.monotonic();closed=await e.close(r.snapshot());elapsed=time.monotonic()-before
            self.assertLess(elapsed,.5);self.assertIsNone(closed['ack']);release.set()
            for _ in range(100):
                if e._done.is_set():break
                await asyncio.sleep(.005)
        self.assertIsNone(e.ack);self.assertFalse(ex.inspect_export(e.config.output)['complete'])

    async def test_abrupt_termination_leaves_incomplete_artifact(self):
        r,e=self.setup_export();e.start();e.submit(r.snapshot())
        for _ in range(100):
            if (e.config.output/'0001.json').exists():break
            await asyncio.sleep(.005)
        e._abort.set()
        for _ in range(100):
            if e._done.is_set():break
            await asyncio.sleep(.005)
        self.assertFalse(ex.inspect_export(e.config.output)['complete']);self.assertFalse((e.config.output/'final.json').exists())

    async def test_malformed_truncated_output_rejected(self):
        r,e=self.setup_export();e.start();closed=await e.close(r.snapshot())
        (e.config.output/'0001.json').write_text('{')
        self.assertFalse(ex.inspect_export(e.config.output,closed['ack'])['complete'])

    async def test_deterministic_order_and_recovery_flags(self):
        r,e=self.setup_export(queue_capacity=4)
        for _ in range(3):e.submit(r.snapshot())
        e.start();closed=await e.close(r.snapshot())
        final=json.loads((e.config.output/'final.json').read_text())
        self.assertEqual([x['name'] for x in final['files']],['0001.json','0002.json','0003.json','0004.json'])
        payload=json.loads((e.config.output/'0001.json').read_text())
        self.assertTrue(payload['snapshot']['records'][0]['reconnect'])
        self.assertEqual(payload['weight_provenance'],'R11_PINNED_DOCUMENTED_ENDPOINT_MODEL_NOT_EXCHANGE_CHARGE')

    async def test_secret_redaction_end_to_end(self):
        r,e=self.setup_export();t=r.begin('/PRIVATE?key=PRIVATE',{'key':'PRIVATE'},'PRIVATE',0)
        r.response(t,429,{'X-MBX-USED-WEIGHT-1M':'PRIVATE','Authorization':'PRIVATE'},1);r.finish(t)
        e.start();await e.close(r.snapshot())
        self.assertNotIn('PRIVATE',''.join(p.read_text() for p in e.config.output.iterdir()))

    async def test_spacing_violations_and_clock_anomaly_exported(self):
        r,e=self.setup_export();t=r.begin('/fapi/v1/exchangeInfo',{},'STARTUP',0);r.finish(t);r.clock_anomalies=1
        e.start();closed=await e.close(r.snapshot())
        value=json.loads((e.config.output/'0001.json').read_text())
        self.assertEqual(value['spacing_violations'],1)
        self.assertFalse(ex.inspect_export(e.config.output,closed['ack'])['complete'])

    async def test_writer_never_runs_on_request_thread(self):
        r,e=self.setup_export();original=e._write;threads=[]
        def checked(*a):threads.append(threading.get_ident());return original(*a)
        with patch.object(e,'_write',side_effect=checked):
            e.start();await e.close(r.snapshot())
        self.assertTrue(threads);self.assertNotIn(threading.get_ident(),threads)

    async def test_enabled_startup_failure_does_not_interrupt_sender(self):
        args=argparse.Namespace();p=argparse.ArgumentParser();ex.add_arguments(p)
        args=p.parse_args(['--rest-telemetry','--telemetry-output',str(self.base/'capture')])
        completed=[]
        class FakeSender:
            def __init__(self,args,session,rest_telemetry):self.r=rest_telemetry
            def rest_telemetry_snapshot(self):return self.r.snapshot()
            async def run(self):completed.append(True);return 42
        with patch.object(ex.SnapshotExporter,'_write',side_effect=PermissionError('PRIVATE')):
            self.assertEqual(await ex.run_with_telemetry(FakeSender,args,None),42)
        self.assertEqual(completed,[True])

    async def test_enabled_startup_preserves_sender_exception(self):
        p=argparse.ArgumentParser();ex.add_arguments(p);args=p.parse_args(['--rest-telemetry','--telemetry-output',str(self.base/'capture')])
        class FakeSender:
            def __init__(self,args,session,rest_telemetry):self.r=rest_telemetry
            def rest_telemetry_snapshot(self):return self.r.snapshot()
            async def run(self):raise RuntimeError('original feed failure')
        with self.assertRaisesRegex(RuntimeError,'original feed failure'):await ex.run_with_telemetry(FakeSender,args,None)

    async def test_exporter_initialization_failure_falls_back_to_original_sender(self):
        p=argparse.ArgumentParser();ex.add_arguments(p);args=p.parse_args(['--rest-telemetry','--telemetry-output',str(self.base/'capture')])
        class FakeSender:
            def __init__(self,args,session):pass
            async def run(self):return 'original feed'
        with patch.object(ex,'SnapshotExporter',side_effect=OSError('PRIVATE_CLOCK')):
            with self.assertLogs('binance',level='WARNING') as messages:
                self.assertEqual(await ex.run_with_telemetry(FakeSender,args,None),'original feed')
        self.assertNotIn('PRIVATE_CLOCK',''.join(messages.output))

    async def test_sampler_task_creation_failure_keeps_feed_running(self):
        p=argparse.ArgumentParser();ex.add_arguments(p);args=p.parse_args(['--rest-telemetry','--telemetry-output',str(self.base/'capture')])
        class FakeSender:
            def __init__(self,args,session,rest_telemetry):self.r=rest_telemetry
            def rest_telemetry_snapshot(self):return self.r.snapshot()
            async def run(self):return 'original feed'
        with patch.object(ex.asyncio,'create_task',side_effect=OSError('PRIVATE')):
            self.assertEqual(await ex.run_with_telemetry(FakeSender,args,None),'original feed')

    async def test_observation_expiry_does_not_stop_feed(self):
        p=argparse.ArgumentParser();ex.add_arguments(p);args=p.parse_args(['--rest-telemetry','--telemetry-output',str(self.base/'capture'),'--telemetry-duration-seconds','.05','--telemetry-flush-seconds','.05'])
        class FakeSender:
            def __init__(self,args,session,rest_telemetry):self.r=rest_telemetry
            def rest_telemetry_snapshot(self):return self.r.snapshot()
            async def run(self):await asyncio.sleep(.15);return 'feed continued'
        self.assertEqual(await ex.run_with_telemetry(FakeSender,args,None),'feed continued')
        self.assertTrue((self.base/'capture/final.json').exists())
