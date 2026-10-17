import asyncio
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, AsyncMock

from Binance import sender as mod
from Binance.diagnostics import Diagnostics
from Benchmarks.offline_fairness import Clock, FakeREST, FakeRelay, fake_event, BOUNDARY
from Benchmarks.receiver_capture import PassiveCapture


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self): asyncio.get_running_loop().set_debug(False)

    def fixture(self, delay=0):
        clock=Clock(BOUNDARY+600)
        rest=FakeREST(clock);relay=FakeRelay(clock,delay)
        rest.oracle=relay.oracle
        diag=Diagnostics(4096,clock)
        args=SimpleNamespace(native_history=True,history_days=1,batch_size=100,flush_ms=250,rest='memory://fixtures')
        sender=mod.Sender(args,rest,diag)
        sender.symbols=[f'S{i:03}USDT' for i in range(500)]
        return clock,rest,relay,sender

    async def drive(self, clock, work, limit=2400):
        proxy=SimpleNamespace(**{n:getattr(asyncio,n) for n in dir(asyncio) if not n.startswith('__')})
        proxy.sleep=clock.sleep;proxy.wait_for=clock.wait_for
        with patch.object(mod,'time',clock),patch.object(mod,'asyncio',proxy):
            task=asyncio.create_task(work)
            try:
                self.assertTrue(await clock.drive([task],task.done,limit))
                return task.result()
            finally:
                task.cancel();await asyncio.gather(task,return_exceptions=True)

    def queue(self,sender,symbol,interval='1m',count=1,start=None):
        step=60000 if interval=='1m' else mod.DAY_MS
        end=BOUNDARY*1000
        sender.queue_repair(symbol,interval,end-count*step if start is None else start,end)

    async def test_exact_bound_policy_and_eligible_daily_opportunity(self):
        c,r,w,s=self.fixture()
        self.assertEqual(mod.MINUTE_REPAIR_WEIGHT,3)
        for n in s.symbols[:9]: self.queue(s,n)
        for n in s.symbols[100:103]: self.queue(s,n,'1d')
        async def work():
            while s.repairs: await s.repair_step(w)
        await self.drive(c,work())
        self.assertEqual([x['params']['interval'] for x in r.calls], ['1m','1m','1m','1d']*3)
        self.assertTrue(w.oracle.complete)

    async def test_continuous_daily_work_preserves_minute_progress(self):
        c,r,w,s=self.fixture()
        for n in s.symbols[:100]: self.queue(s,n)
        async def work():
            for turn in range(140):
                self.queue(s,s.symbols[100+turn],'1d')
                await s.repair_step(w)
        await self.drive(c,work())
        self.assertFalse(any(k[1]=='1m' for k in s.repairs))
        self.assertEqual(sum(x['params']['interval']=='1m' for x in r.calls),100)
        self.assertGreater(sum(x['params']['interval']=='1d' for x in r.calls),0)
        self.assertTrue(w.oracle.complete)

    async def test_continuous_minute_work_preserves_daily_progress(self):
        c,r,w,s=self.fixture()
        for n in s.symbols[300:330]: self.queue(s,n,'1d')
        async def work():
            for turn in range(125):
                self.queue(s,s.symbols[turn])
                await s.repair_step(w)
        await self.drive(c,work())
        self.assertFalse(any(k[1]=='1d' for k in s.repairs))
        self.assertEqual(sum(x['params']['interval']=='1d' for x in r.calls),30)
        self.assertTrue(w.oracle.complete)

    async def test_cooldown_ineligible_daily_does_not_block_minutes(self):
        c,r,w,s=self.fixture();self.queue(s,s.symbols[0],'1d');self.queue(s,s.symbols[1])
        s.retry_after[(s.symbols[0],'1d')]=c.monotonic()+60;s._minute_repair_streak=3
        await self.drive(c,s.repair_step(w))
        self.assertEqual(r.calls[0]['params']['interval'],'1m');self.assertEqual(len(s.repairs),1)

    async def test_page_bound_and_resume_without_duplicate_completed_bars(self):
        c,r,w,s=self.fixture();self.queue(s,s.symbols[0],count=1500)
        await self.drive(c,s.repair_step(w));self.assertEqual(len(r.calls),1)
        self.assertEqual(len(w.history),499);self.assertTrue(s.repairs)
        async def work():
            while s.repairs: await s.repair_step(w)
        await self.drive(c,work())
        self.assertEqual(len(r.calls),4);self.assertEqual(len(w.history),1500)
        self.assertEqual(w.duplicates,0);self.assertTrue(w.oracle.complete)
        self.assertFalse(s._repair_delivered)

    async def test_fifo_page_rotation_within_minute_class(self):
        c,r,w,s=self.fixture();self.queue(s,s.symbols[0],count=1000);self.queue(s,s.symbols[1])
        async def work():
            await s.repair_step(w);await s.repair_step(w)
        await self.drive(c,work())
        self.assertEqual([x['params']['symbol'] for x in r.calls],s.symbols[:2])
        self.assertIn((s.symbols[0],'1m'),s.repairs)

    async def test_failed_second_page_keeps_first_and_retries_cursor(self):
        c,r,w,s=self.fixture();self.queue(s,s.symbols[0],count=1000)
        await self.drive(c,s.repair_step(w));cursor=s.repair_span((s.symbols[0],'1m'))[0]
        original=s.rest
        async def failed(*a,**k): raise RuntimeError('offline response failure')
        s.rest=failed;await self.drive(c,s.repair_step(w))
        self.assertEqual(s.repair_span((s.symbols[0],'1m'))[0],cursor)
        self.assertEqual(len(w.history),499)
        s.rest=original;s.retry_after.clear()
        async def work():
            while s.repairs: await s.repair_step(w)
        await self.drive(c,work())
        self.assertEqual(w.duplicates,0);self.assertEqual(len(w.history),1000)
        self.assertEqual(r.calls[1]['params']['startTime'],cursor)

    async def test_send_failure_does_not_advance_unconfirmed_cursor(self):
        c,r,w,s=self.fixture();self.queue(s,s.symbols[0],count=1000)
        start=s.repair_span((s.symbols[0],'1m'))[0]
        peer=SimpleNamespace(send=AsyncMock(side_effect=RuntimeError('before receipt')))
        await self.drive(c,s.repair_step(peer))
        self.assertEqual(s.repair_span((s.symbols[0],'1m'))[0],start)
        self.assertTrue(s.repairs);self.assertEqual(s.repair_counters['failed_turns'],1)

    async def test_coalesced_extensions_while_awaiting_do_not_repeat_prefix(self):
        c,r,w,s=self.fixture();symbol=s.symbols[0];self.queue(s,symbol,count=1)
        original=r.get
        def get(url,params):
            if not r.calls:
                s.queue_repair(symbol,'1m',params['startTime']-60000,params['endTime']+1+60000,'MINUTE_RECONNECT')
            return original(url,params)
        r.get=get
        await self.drive(c,s.repair_step(w))
        self.assertEqual(len(s.repairs),1)
        async def work():
            while s.repairs: await s.repair_step(w)
        await self.drive(c,work())
        self.assertEqual(len(w.history),3);self.assertEqual(w.duplicates,0)
        self.assertTrue(w.oracle.complete)

    async def test_reentry_is_not_a_second_request(self):
        c,r,w,s=self.fixture();self.queue(s,s.symbols[0])
        peer=SimpleNamespace(send=AsyncMock())
        entered=asyncio.Event();release=asyncio.Event()
        async def rest(*a,**k):
            entered.set();await release.wait();return [[BOUNDARY*1000-60000,10,12,9,11,17]]
        s.rest=AsyncMock(side_effect=rest)
        task=asyncio.create_task(s.repair_step(peer))
        await entered.wait()
        self.assertFalse(await s.repair_step(peer));self.assertFalse(await s.repair_one(peer))
        release.set();await task
        self.assertEqual(s.rest.await_count,1)

    async def test_cancelled_page_preserves_confirmed_prefix_and_pending_work(self):
        c,r,w,s=self.fixture();self.queue(s,s.symbols[0],count=1000)
        await self.drive(c,s.repair_step(w));cursor=s.repair_span((s.symbols[0],'1m'))[0]
        entered=asyncio.Event()
        async def rest(*a,**k):entered.set();await asyncio.Event().wait()
        original=s.rest;s.rest=rest
        task=asyncio.create_task(s.repair_step(w));await entered.wait();task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertFalse(s.repair_lock.locked());self.assertIsNone(s._page_context.get())
        self.assertEqual(s.repair_span((s.symbols[0],'1m'))[0],cursor)
        s.rest=original
        async def work():
            while s.repairs:await s.repair_step(w)
        await self.drive(c,work());self.assertEqual(w.duplicates,0)

    async def test_long_manual_history_yields_without_changing_complete_count(self):
        c,r,w,s=self.fixture();self.queue(s,s.symbols[1],'1d')
        count=await self.drive(c,s.history(w,s.symbols[0],0,count=1500))
        self.assertEqual(count,1500)
        self.assertEqual([x['params']['interval'] for x in r.calls],['1m','1d','1m','1m','1m'])
        self.assertTrue(w.oracle.complete);self.assertFalse(s.repairs)

    async def test_native_preload_yields_at_safe_page_boundary(self):
        c,r,w,s=self.fixture();self.queue(s,s.symbols[1])
        await self.drive(c,s.native_history(w,s.symbols[0]))
        self.assertEqual(r.calls[1]['params']['symbol'],s.symbols[1])
        self.assertEqual(len(r.calls),6);self.assertTrue(w.oracle.complete)

    async def test_task_local_history_context_not_shared_with_concurrent_command(self):
        c,r,w,s=self.fixture();self.queue(s,s.symbols[0]);entered=asyncio.Event();release=asyncio.Event()
        original=s.rest
        async def rest(*a,**k):
            if k['symbol']==s.symbols[0]:entered.set();await release.wait()
            return await original(*a,**k)
        s.rest=rest
        proxy=SimpleNamespace(**{n:getattr(asyncio,n) for n in dir(asyncio) if not n.startswith('__')});proxy.sleep=c.sleep;proxy.wait_for=c.wait_for
        with patch.object(mod,'time',c),patch.object(mod,'asyncio',proxy):
            repair=asyncio.create_task(s.repair_step(w))
            async def command():
                await entered.wait();value=await s.history(w,s.symbols[1],0,count=1);release.set();return value
            manual=asyncio.create_task(command())
            try:
                self.assertTrue(await c.drive([repair,manual],lambda:repair.done() and manual.done()))
                self.assertEqual(manual.result(),1);self.assertFalse(s.repairs);self.assertTrue(w.oracle.complete)
            finally:
                repair.cancel();manual.cancel();await asyncio.gather(repair,manual,return_exceptions=True)

    async def test_classification_union_even_when_bounds_do_not_change(self):
        c,r,w,s=self.fixture();symbol=s.symbols[0];self.queue(s,symbol)
        s.queue_repair(symbol,'1m',*s.repairs[(symbol,'1m')],'MINUTE_STALE')
        self.assertEqual(s._repair_classes[(symbol,'1m')],{'MINUTE_GAP','MINUTE_STALE'})
        self.assertEqual(s.diagnostics.jobs[(symbol,'1m')]['classifications'],['MINUTE_GAP','MINUTE_STALE'])

    async def test_retention_and_invalid_universe_fail_explicitly(self):
        c,r,w,s=self.fixture();self.queue(s,s.symbols[0],count=2000)
        await self.drive(c,s.repair_one(w))
        self.assertEqual(len(w.history),1500);self.assertEqual(w.duplicates,0)
        with self.assertRaises(ValueError):self.queue(s,'UNKNOWN')
        with self.assertRaises(ValueError):s.queue_repair(s.symbols[0],'1d',0,mod.DAY_MS,'MINUTE_GAP')

    async def test_diagnostic_fault_during_repair_preserves_delivery(self):
        c,r,w,s=self.fixture();s.diagnostics.counts=None;self.queue(s,s.symbols[0])
        await self.drive(c,s.repair_step(w))
        self.assertFalse(s.repairs);self.assertTrue(w.oracle.complete)
        self.assertGreater(s._diagnostic_failures,0)

    async def test_raw_event_retains_exact_shard_generation(self):
        c,r,w,s=self.fixture();key=s.diagnostics.shard(2,set(s.symbols[100:200]),False)
        s.diagnostics.connection(key,'connected');s.diagnostics.connection(key,'connected')
        s.ingest(fake_event(s.symbols[100],BOUNDARY*1000,True),key)
        event=s.diagnostics.records[-1]
        self.assertEqual((event['shard'],event['generation'],event['accepted']),('market:2',2,True))

    async def test_capture_observer_failure_cannot_block_delivery(self):
        c,r,w,s=self.fixture();capture=PassiveCapture('broken-capture');capture.records=None
        async def send(raw):
            self.assertFalse(capture.offer(dict(kind='raw_frame',raw_received=True)))
            await w.send(raw)
        self.queue(s,s.symbols[0])
        await self.drive(c,s.repair_step(SimpleNamespace(send=send)))
        self.assertTrue(w.oracle.complete);self.assertFalse(s.repairs)
        self.assertEqual(capture.observer_failures,1);self.assertFalse(capture.health()['evidence_complete'])

    async def test_native_later_page_retry_resumes_confirmed_prefix(self):
        c,r,w,s=self.fixture();original=s.rest
        async def broken(*a,**k):
            if len(r.calls)==1:raise RuntimeError('later page failure')
            return await original(*a,**k)
        s.rest=broken
        with self.assertRaises(RuntimeError):await self.drive(c,s.native_history(w,s.symbols[0]))
        self.assertEqual(len(w.history),499)
        state=s._native_history_state[(s.symbols[0],'1m')]
        cursor=state['cursor'];s.rest=original
        await self.drive(c,s.native_history(w,s.symbols[0]))
        self.assertEqual(r.calls[1]['params']['startTime'],cursor)
        self.assertEqual(len(w.history),1800);self.assertEqual(w.duplicates,0);self.assertEqual(len(r.calls),5)
        self.assertFalse(s._native_history_state);self.assertFalse(s._native_history_cycles)

    async def test_native_daily_phase_retry_does_not_repeat_minute_phase(self):
        c,r,w,s=self.fixture();original=s.rest
        async def broken(*a,**k):
            if k['interval']=='1d':raise RuntimeError('daily phase failure')
            return await original(*a,**k)
        s.rest=broken
        with self.assertRaises(RuntimeError):await self.drive(c,s.native_history(w,s.symbols[0]))
        self.assertEqual(len(w.history),1500)
        s.rest=original;await self.drive(c,s.native_history(w,s.symbols[0]))
        self.assertEqual(w.duplicates,0);self.assertEqual(len(r.calls),5);self.assertTrue(w.oracle.complete)

    async def test_native_cancelled_later_page_keeps_phase_state(self):
        c,r,w,s=self.fixture();original=s.rest
        async def interrupted(*a,**k):
            if len(r.calls)==1:raise asyncio.CancelledError
            return await original(*a,**k)
        s.rest=interrupted
        with self.assertRaises(asyncio.CancelledError):await self.drive(c,s.native_history(w,s.symbols[0]))
        self.assertFalse(s._native_inflight);self.assertEqual(len(w.history),499)
        s.rest=original;await self.drive(c,s.native_history(w,s.symbols[0]))
        self.assertEqual(w.duplicates,0);self.assertEqual(len(r.calls),5)

    async def test_new_native_transport_requires_full_preload(self):
        c,r,w,s=self.fixture();original=s.rest
        async def broken(*a,**k):
            if len(r.calls)==1:raise RuntimeError('later page failure')
            return await original(*a,**k)
        s.rest=broken
        with self.assertRaises(RuntimeError):await self.drive(c,s.native_history(w,s.symbols[0]))
        new=FakeRelay(c);r.oracle=new.oracle;s.rest=original
        await self.drive(c,s.native_history(new,s.symbols[0]))
        self.assertEqual(len(new.history),1800);self.assertEqual(new.duplicates,0)
        self.assertEqual(len(r.calls),6) # distinct target intentionally receives its own full prefix

    async def test_explicit_manual_history_does_not_resume_native_job(self):
        c,r,w,s=self.fixture();original=s.rest
        async def broken(*a,**k):
            if len(r.calls)==1:raise RuntimeError('later page failure')
            return await original(*a,**k)
        s.rest=broken
        with self.assertRaises(RuntimeError):await self.drive(c,s.native_history(w,s.symbols[0]))
        cursor=s._native_history_state[(s.symbols[0],'1m')]['cursor'];s.rest=original
        count=await self.drive(c,s.history(w,s.symbols[1],0,count=10))
        self.assertEqual(count,10)
        self.assertEqual(s._native_history_state[(s.symbols[0],'1m')]['cursor'],cursor)


class CaptureTests(unittest.TestCase):
    def temporary(self):
        import os
        root=Path(os.environ['RC2_OUTPUT'])/'capture-tests';root.mkdir(exist_ok=True)
        return tempfile.TemporaryDirectory(dir=root)

    def record(self):
        return dict(kind='candle',symbol='BTCUSDT',interval='1m',candle_open_ms=60000,
                    ohlcv=[10.,12.,9.,11.,0.],raw_received=True,parser_accepted=True,
                    relay_receipt_utc_ms=120001,relay_receipt_monotonic_ns=1234)

    def test_observable_and_unavailable_timestamps_are_distinct(self):
        capture=PassiveCapture('receiver-A');self.assertTrue(capture.offer(self.record()))
        row=json.loads(capture.records[0]);self.assertEqual(row['candle_open_ms'],60000)
        self.assertEqual(row['relay_receipt_utc_ms'],120001)
        for field in ('upstream_event_ms','upstream_close_ms','sender_generation','sender_sequence','shard','finalized','repair_class'):
            self.assertIsNone(row[field])
        self.assertEqual(capture.health()['native_storage_acceptance'],'NOT_PROVEN')

    def test_verified_sidecar_correlation_is_retained_explicitly(self):
        capture=PassiveCapture('receiver-A');row=self.record()
        row.update(sender_generation='sender-A',sender_sequence=2,shard='market:2',upstream_event_ms=61000,finalized=True,repair_class='MINUTE_STALE')
        self.assertTrue(capture.offer(row));saved=json.loads(capture.records[0])
        self.assertEqual(saved['sender_generation'],'sender-A');self.assertEqual(saved['upstream_event_ms'],61000)

    def test_overflow_is_bounded_and_loss_accounted(self):
        capture=PassiveCapture('receiver-A',capacity=2)
        for _ in range(10):capture.offer(self.record())
        self.assertEqual(len(capture.records),2);self.assertEqual(capture.counts['overflow'],8)
        self.assertLessEqual(capture.bytes,capture.byte_capacity);self.assertFalse(capture.health()['evidence_complete'])

    def test_record_validation_and_shutdown_do_not_block_feed(self):
        capture=PassiveCapture('receiver-A')
        self.assertFalse(capture.offer({'kind':'x'*10000}))
        self.assertFalse(capture.offer({'secret':'not retained'}))
        self.assertFalse(capture.offer({'ohlcv':[float('nan')]*5}))
        capture.close();self.assertFalse(capture.offer(self.record()))
        self.assertEqual(capture.counts['invalid'],3);self.assertEqual(capture.counts['closed'],1)

    def test_export_rotation_integrity_and_retention_loss(self):
        capture=PassiveCapture('receiver-A',record_limit=1024,artifact_limit=1024,retained_artifacts=2)
        for _ in range(10):self.assertTrue(capture.offer(self.record()))
        with self.temporary() as temporary:
            root=Path(temporary)/'fresh';self.assertTrue(capture.export(root))
            manifest=json.loads((root/'capture-manifest.json').read_text())
            self.assertEqual(len(manifest['segments']),2)
            for part in manifest['segments']:
                data=(root/part['path']).read_bytes();self.assertLessEqual(len(data),1024)
                self.assertEqual(hashlib.sha256(data).hexdigest(),part['sha256'])
            self.assertGreater(manifest['health']['counts']['retention_loss'],0)
            self.assertFalse(manifest['health']['evidence_complete']);self.assertEqual(capture.bytes,0)

    def test_failed_export_retains_records_and_marks_incomplete(self):
        capture=PassiveCapture('receiver-A');capture.offer(self.record())
        with self.temporary() as temporary:
            existing=Path(temporary)
            self.assertFalse(capture.export(existing));self.assertEqual(len(capture.records),1)
            self.assertFalse(capture.health()['evidence_complete'])
            self.assertTrue(capture.export(existing/'fresh'))
            self.assertEqual(capture.counts['export_errors'],1)

    def test_fresh_snapshot_does_not_overwrite_previous_artifact(self):
        capture=PassiveCapture('receiver-A');capture.offer(self.record())
        with self.temporary() as temporary:
            root=Path(temporary)/'fresh';self.assertTrue(capture.export(root))
            original=(root/'capture-manifest.json').read_bytes()
            capture.offer(self.record());self.assertFalse(capture.export(root))
            self.assertEqual((root/'capture-manifest.json').read_bytes(),original)

    def test_sequence_exhaustion_fails_closed(self):
        capture=PassiveCapture('receiver-A');capture.sequence=2**63-1
        self.assertFalse(capture.offer(self.record()));self.assertEqual(capture.counts['invalid'],1)
