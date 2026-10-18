import asyncio,ast,copy,hashlib,importlib.util,json,os,tempfile,time,unittest,uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from Binance import sender,telemetry_export as ex
from Binance.telemetry_sender import TelemetrySender
from Binance.rest_telemetry import RestTelemetry
import test_pacing_r15b as pacing
ROOT=Path(__file__).resolve().parents[1]
OBS=[]

class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def workload(self,mode,statuses=()):
        c=pacing.Clock(early=15000000);session=pacing.Session(c,statuses=statuses)
        recorder=RestTelemetry(monotonic_ns=c.perf_counter_ns,utc_ns=lambda:1791800000000000000+c.ns)
        cls=sender.Sender if mode=='disabled' else TelemetrySender
        args=SimpleNamespace(rest='UNUSED',native_history=True,history_days=1,batch_size=100,flush_ms=50)
        a=cls(args,session,rest_telemetry=recorder) if mode=='enabled' else cls(args,session)
        a.symbols=['BTCUSDT','ETHUSDT'];frames=[]
        class WS:
            async def send(self,msg):frames.append(json.loads(msg))
        with patch.object(sender,'time',c),patch.object(sender,'asyncio',SimpleNamespace(sleep=c.sleep,wait_for=asyncio.wait_for)):
            await a.rest('/fapi/v1/exchangeInfo')
            a.queue_repair('BTCUSDT','1m',60000,120000);a.queue_repair('ETHUSDT','1d',86400000,172800000)
            while a.repairs:await a.repair_one(WS())
        return session.entries,frames,recorder.snapshot()
    async def test_enabled_disabled_request_payload_timing_equivalence(self):
        a=await self.workload('disabled');b=await self.workload('enabled')
        self.assertEqual(a[:2],b[:2]);self.assertEqual([r['request_class'] for r in b[2]['records']],['STARTUP','MINUTE_REPAIR','DAILY_REPAIR'])
        self.assertTrue(all(r['finished'] for r in b[2]['records']));OBS.append(dict(case=self.id(),equivalent=True,requests=len(a[0])))
    async def test_enabled_retry_noninterference(self):
        a=await self.workload('disabled',[429,200]);b=await self.workload('enabled',[429,200]);self.assertEqual(a[:2],b[:2])
        self.assertEqual(b[2]['records'][0]['cooldown_seconds'],60)
    async def test_recorder_failure_never_weakens_pacing(self):
        with patch.object(RestTelemetry,'begin',side_effect=MemoryError('PRIVATE')):
            a=await self.workload('enabled');self.assertEqual(len(a[0]),3)
            self.assertTrue(all(b['ns']-a['ns']>=250000000 for a,b in zip(a[0],a[0][1:])))
    async def test_actual_enabled_redirect_attempt_endpoint_accuracy(self):
        import aiohttp
        requests=[]
        async def server(reader,writer):
            try:
                data=await reader.readuntil(b'\r\n\r\n');requests.append(data)
                result=(b'HTTP/1.1 302 Found\r\nLocation: /fapi/v1/klines?limit=499&secret=PRIVATE\r\nContent-Length: 0\r\nConnection: close\r\n\r\n' if len(requests)==1 else b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nX-MBX-USED-WEIGHT-1M: 2\r\nContent-Length: 2\r\nConnection: close\r\n\r\n[]')
                writer.write(result);await writer.drain()
            finally:writer.close();await writer.wait_closed()
        srv=await asyncio.start_server(server,'127.0.0.1',0)
        try:
            async with aiohttp.ClientSession() as session:
                rec=RestTelemetry();a=TelemetrySender(SimpleNamespace(rest='http://127.0.0.1:'+str(srv.sockets[0].getsockname()[1])),session,rec)
                await a.rest('/fapi/v1/exchangeInfo');snap=rec.snapshot()
            self.assertEqual([r['endpoint'] for r in snap['records']],['EXCHANGE_INFO','KLINES'])
            self.assertEqual(snap['records'][1]['documented_request_weight'],2)
            self.assertEqual(snap['records'][1]['used_weight']['X-MBX-USED-WEIGHT-1M'],2)
            self.assertNotIn('PRIVATE',json.dumps(snap));self.assertGreaterEqual(snap['records'][1]['initiation_gap_ns'],250000000)
        finally:srv.close();await srv.wait_closed()
    def test_telemetry_adapter_does_not_override_scheduling(self):
        self.assertNotIn('select_repair',TelemetrySender.__dict__)
        self.assertNotIn('repair_span',TelemetrySender.__dict__)
        self.assertNotIn('history_range',TelemetrySender.__dict__)


class DurableTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=Path(os.environ['RC2_OUTPUT'])/'fixtures');self.base=Path(self.tmp.name)
    async def asyncTearDown(self):self.tmp.cleanup()
    def setup_export(self,**kw):
        rec=RestTelemetry();t=rec.begin('/fapi/v1/klines',{'limit':499},'HISTORY',0);rec.response(t,200,{},None);rec.finish(t)
        return rec,ex.SnapshotExporter(ex.ExportConfig(self.base/'capture',**kw),rec)
    async def test_persistent_ack_readback_without_inmemory_ack(self):
        r,e=self.setup_export();e.start();closed=await e.close(r.snapshot());self.assertTrue(closed['complete'])
        self.assertTrue(ex.inspect_export(e.config.output)['complete']);self.assertTrue((e.config.output/'ack.json').is_file())
        ack=json.loads((e.config.output/'ack.json').read_text());self.assertEqual(ack['EXPORTED_RECORD_COUNT'],1)
        self.assertEqual(ack['OS_FLUSH_STATUS'],'SUCCESS');self.assertEqual(ack['physical_power_loss_durability'],'NOT_PROVEN')
    async def test_persistent_ack_survives_fresh_process_reader(self):
        import subprocess,sys
        r,e=self.setup_export();e.start();await e.close(r.snapshot())
        code='import json,sys;from Binance.telemetry_export import inspect_export;print(json.dumps(inspect_export(sys.argv[1])))'
        p=subprocess.run([sys.executable,'-B','-c',code,str(e.config.output)],capture_output=True,text=True,env=os.environ,timeout=5)
        self.assertEqual(p.returncode,0,p.stderr);self.assertTrue(json.loads(p.stdout)['complete'])
    async def test_no_transient_ack_substitution(self):
        r,e=self.setup_export();e.start();closed=await e.close(r.snapshot());(e.config.output/'ack.json').unlink()
        self.assertFalse(ex.inspect_export(e.config.output,closed['ack'])['complete'])
    async def test_ack_content_tamper_rejected(self):
        r,e=self.setup_export();e.start();await e.close(r.snapshot());p=e.config.output/'ack.json';a=json.loads(p.read_text());a['EXPORTED_RECORD_COUNT']=99;p.write_text(json.dumps(a))
        self.assertFalse(ex.inspect_export(e.config.output)['complete'])
    async def test_manifest_payload_corruption_rejected(self):
        r,e=self.setup_export();e.start();await e.close(r.snapshot());(e.config.output/'0001.json').write_text('{}')
        self.assertFalse(ex.inspect_export(e.config.output)['complete'])
    async def test_all_files_and_partials_bounded(self):
        r,e=self.setup_export(max_files=4,max_file_bytes=4096,queue_capacity=4)
        for _ in range(8):e.submit(r.snapshot())
        e.start();await e.close(r.snapshot());files=list(e.config.output.iterdir())
        self.assertLessEqual(len(files),4);self.assertLessEqual(sum(p.stat().st_size for p in files),4*4096)
        self.assertFalse(ex.inspect_export(e.config.output)['complete']);self.assertGreater(e.retention_dropped,0)
    async def test_fsync_failure_no_ack(self):
        r,e=self.setup_export()
        with patch.object(ex.os,'fsync',side_effect=OSError('PRIVATE')):
            e.start();result=await e.close(r.snapshot())
        self.assertFalse(result['complete']);self.assertFalse(ex.inspect_export(e.config.output)['complete'])
    async def test_delayed_ack_no_late_publication(self):
        import threading
        r,e=self.setup_export(drain_seconds=2);clock=[100.];e._clock=lambda:clock[0]
        original=e._write;entered=threading.Event();release=threading.Event()
        def slow(name,value):
            if name=='ack.json':entered.set();release.wait(5)
            return original(name,value)
        with patch.object(e,'_write',side_effect=slow):
            e.start();closing=asyncio.create_task(e.close(r.snapshot()))
            for _ in range(400):
                if entered.is_set():break
                await asyncio.sleep(.005)
            self.assertTrue(entered.is_set());clock[0]=103.
            result=await closing;self.assertFalse(result['complete']);release.set()
            for _ in range(100):
                if e._done.is_set():break
                await asyncio.sleep(.005)
        self.assertTrue(entered.is_set());self.assertFalse((e.config.output/'ack.json').exists())
    async def test_writer_crash_leaves_partial_incomplete(self):
        r,e=self.setup_export();original=e._write
        def crash(name,value):
            if name=='final.json':(e.config.output/'final.part').write_bytes(b'{');raise OSError('simulated crash')
            return original(name,value)
        with patch.object(e,'_write',side_effect=crash):e.start();result=await e.close(r.snapshot())
        self.assertFalse(result['complete']);self.assertFalse(ex.inspect_export(e.config.output)['complete'])
    async def test_abrupt_writer_process_exit_partial_incomplete(self):
        import subprocess,sys
        directory=self.base/'abrupt'
        script="import sys,os,time;from pathlib import Path;from Binance.telemetry_export import ExportConfig,SnapshotExporter;from Binance.rest_telemetry import RestTelemetry;import Binance.telemetry_export as ex;ex.os.fsync=lambda fd:os._exit(23);r=RestTelemetry();e=SnapshotExporter(ExportConfig(Path(sys.argv[1])),r);e.start();time.sleep(3);os._exit(24)"
        p=subprocess.run([sys.executable,'-B','-c',script,str(directory)],timeout=5,creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(p.returncode,23);self.assertTrue((directory/'session.part').exists());self.assertFalse(ex.inspect_export(directory)['complete'])
    async def test_loss_not_falsely_complete(self):
        r,e=self.setup_export();r.dropped=1;e.start();await e.close(r.snapshot());self.assertFalse(ex.inspect_export(e.config.output)['complete'])
