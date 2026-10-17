import asyncio
from collections import Counter
from dataclasses import FrozenInstanceError
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from Binance import sender as mod
from Binance.diagnostics import Diagnostics
from Benchmarks.offline_fairness import Clock, FakeRelay, run_case, fake_event
from Benchmarks.reference_oracle import ReferenceFixture, DeliveryOracle


class OracleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self): asyncio.get_running_loop().set_debug(False)

    async def test_original_zero_to_17_mutation_rejected(self):
        original = mod.record
        def corrupt(*args):
            result = original(*args); result['v'] = 17.; return result
        with patch.object(mod, 'record', corrupt):
            result, _ = await run_case('J_ZERO_TRADE', 'CANDIDATE_B')
        self.assertEqual(result['verdict'], 'FAIL')
        self.assertFalse(result['checks']['exact_ohlcv'])
        self.assertEqual(result['oracle']['rejected_frames'], 10)

    async def test_valid_zero_trade_and_normal_volume(self):
        for scenario in ('J_ZERO_TRADE', 'K_MISSING_MINUTES'):
            result, _ = await run_case(scenario)
            self.assertEqual(result['verdict'], 'PASS')
            self.assertEqual(result['oracle']['validated_frames'], result['oracle']['expected_frames'])

    def test_reference_is_immutable_and_independent(self):
        reference = ReferenceFixture(True)
        with self.assertRaises(FrozenInstanceError): reference.zero_trade = False
        with patch.object(mod, 'record', side_effect=AssertionError('encoder must not be consulted')):
            self.assertEqual(reference.bar(60000, '1m'), (19700101, 100, 10., 12., 9., 11., 0.))

    async def test_delivered_price_volume_missing_duplicate_timestamp_controls(self):
        for defect in ('price', 'volume', 'missing', 'duplicate', 'timestamp', 'extra_frame'):
            relay = FakeRelay(Clock(0), zero=True)
            relay.oracle.authorize(dict(symbol='BTCUSDT', interval='1m', startTime=60000, endTime=119999, limit=500))
            frame = dict(hist='BTCUSDT', format='dtohlcv', bars=[[19700101,100,10.,12.,9.,11.,0.]])
            if defect == 'price': frame['bars'][0][5] = 10.5
            if defect == 'volume': frame['bars'][0][6] = 17.
            if defect == 'missing': frame['bars'] = []
            if defect == 'duplicate': frame['bars'] *= 2
            if defect == 'timestamp': frame['bars'][0][1] = 200
            await relay.send(json.dumps(frame))
            if defect == 'extra_frame': await relay.send(json.dumps(frame))
            self.assertFalse(relay.oracle.complete, defect)
            self.assertFalse(relay.exact, defect)

    def test_nonzero_to_zero_volume_rejected(self):
        oracle = DeliveryOracle(ReferenceFixture(False))
        oracle.authorize(dict(symbol='BTCUSDT', interval='1m', startTime=60000, endTime=119999, limit=500))
        self.assertFalse(oracle.receive(dict(hist='BTCUSDT',format='dtohlcv',bars=[[19700101,100,10,12,9,11,0]])))

    def test_lost_entire_delivery_is_pending_not_pass(self):
        oracle = DeliveryOracle(ReferenceFixture())
        oracle.authorize(dict(symbol='BTCUSDT', interval='1m', startTime=60000, endTime=119999, limit=500))
        self.assertFalse(oracle.complete)
        self.assertEqual(len(oracle.pending), 1)

    def test_authorized_recheck_upsert_is_not_duplicate_corruption(self):
        oracle = DeliveryOracle(ReferenceFixture())
        params = dict(symbol='BTCUSDT', interval='1m', startTime=60000, endTime=119999, limit=500)
        for _ in range(2):
            oracle.authorize(params)
            self.assertTrue(oracle.receive(dict(hist='BTCUSDT',format='dtohlcv',bars=[[19700101,100,10,12,9,11,17]])))
        self.assertTrue(oracle.complete)


class ClockTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self): asyncio.get_running_loop().set_debug(False)

    async def clean(self, tasks):
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def test_original_twelve_yield_repro_and_deeper_ready_chains(self):
        for depth in (12, 100, 1000):
            clock = Clock(0); observed = []
            async def work():
                for _ in range(depth): await asyncio.sleep(0)
                observed.append(clock.time())
            tasks = [asyncio.create_task(work()), asyncio.create_task(clock.sleep(10))]
            try:
                self.assertTrue(await clock.drive(tasks, lambda: bool(observed)))
                self.assertEqual(observed, [0])
            finally: await self.clean(tasks)

    async def test_ready_callbacks_drained(self):
        clock = Clock(0); times = []; loop = asyncio.get_running_loop()
        def callback(n):
            if n: loop.call_soon(callback, n-1)
            else: times.append(clock.time())
        loop.call_soon(callback, 25)
        task = asyncio.create_task(clock.sleep(10))
        try:
            await clock.drive([task], lambda: bool(times)); self.assertEqual(times, [0])
        finally: await self.clean([task])

    async def test_creation_orders_simultaneous_eligibility(self):
        for order in (('a','b','c'), ('c','a','b')):
            clock = Clock(0); seen = []
            async def work(name):
                await clock.sleep(2); seen.append((name, clock.time()))
            tasks = [asyncio.create_task(work(n)) for n in order]
            await clock.drive(tasks, lambda: all(t.done() for t in tasks))
            self.assertEqual(seen, [(n,2) for n in order])

    async def test_cancelled_sleeper_does_not_advance_clock(self):
        clock = Clock(0); seen = []
        cancelled = asyncio.create_task(clock.sleep(1))
        await asyncio.sleep(0); cancelled.cancel(); await asyncio.gather(cancelled, return_exceptions=True)
        async def work(): await clock.sleep(2); seen.append(clock.time())
        task = asyncio.create_task(work())
        await clock.drive([task], task.done)
        self.assertEqual(seen, [2])

    async def test_virtual_timeout_cleans_children(self):
        clock = Clock(0)
        task = asyncio.create_task(clock.wait_for(clock.sleep(20), 3))
        with self.assertRaises(TimeoutError): await clock.drive([task], task.done)
        self.assertEqual(clock.time(), 3)
        self.assertFalse(clock.helpers)

    async def test_timeout_success_and_parent_cancellation(self):
        clock = Clock(0)
        task = asyncio.create_task(clock.wait_for(clock.sleep(2), 3))
        await clock.drive([task], task.done)
        self.assertIsNone(task.result()); self.assertFalse(clock.helpers)
        task = asyncio.create_task(clock.wait_for(clock.sleep(20), 30))
        await asyncio.sleep(0); task.cancel(); await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(task.cancelled()); self.assertFalse(clock.helpers)

    async def test_unobserved_completed_task_is_rejected(self):
        clock = Clock(0)
        async def short(): return None
        async def owner():
            asyncio.create_task(short()); await clock.sleep(1)
        task = asyncio.create_task(owner())
        try:
            with self.assertRaisesRegex(AssertionError, 'Unobserved'): await clock.drive([task], task.done)
        finally: await self.clean([task])

    async def test_blocked_without_future_work_reports_deadlock(self):
        clock = Clock(0); task = asyncio.create_task(asyncio.Event().wait())
        try:
            with self.assertRaisesRegex(AssertionError, 'deadlock'): await clock.drive([task], task.done)
        finally: await self.clean([task])

    async def test_server_retry_limit_and_virtual_backoff(self):
        clock = Clock(0); starts = []
        class Response:
            status = 503
            async def __aenter__(self): starts.append(clock.time()); return self
            async def __aexit__(self, *args): pass
        s = mod.Sender(SimpleNamespace(rest='memory://fixtures'),
                       SimpleNamespace(get=lambda *a, **kw: Response()))
        proxy = SimpleNamespace(**{n:getattr(asyncio,n) for n in dir(asyncio) if not n.startswith('__')})
        proxy.sleep = clock.sleep
        with patch.object(mod,'time',clock), patch.object(mod,'asyncio',proxy):
            task = asyncio.create_task(s.rest('/fapi/v1/klines'))
            with self.assertRaisesRegex(RuntimeError,'retries exhausted'):
                await clock.drive([task], task.done)
        self.assertEqual(starts, [0,1,3,7,15,31])
        self.assertEqual(clock.time(), 61)

    async def test_rejected_unobserved_task_is_cancelled(self):
        clock = Clock(0); leaked=[]
        async def owner():
            leaked.append(asyncio.create_task(asyncio.Event().wait()))
            await clock.sleep(1)
        task=asyncio.create_task(owner())
        try:
            with self.assertRaisesRegex(AssertionError,'Unobserved'):
                await clock.drive([task],task.done)
            self.assertTrue(leaked[0].cancelled())
        finally: await self.clean([task])

    async def test_repeatability_retry_and_cooldown_fixtures(self):
        for scenario in ('H_429','I_418','N_OUTPUT_DELAY'):
            first, _ = await run_case(scenario, 'CANDIDATE_B')
            second, _ = await run_case(scenario, 'CANDIDATE_B')
            self.assertEqual(first, second)
            self.assertEqual(first['verdict'], 'PASS')
            self.assertEqual(first['pending_tasks_after_shutdown'], 0)
            self.assertEqual(first['minute_wait']['count'], first['jobs_completed']['1m'])


class DiagnosticIsolationTests(unittest.IsolatedAsyncioTestCase):
    def sender(self, diag):
        return mod.Sender(SimpleNamespace(batch_size=100,flush_ms=250), None, diag)

    async def test_original_counter_fault_delivery_and_loss_accounting(self):
        class Broken(Counter):
            def __setitem__(self, key, value): raise RuntimeError('counter failure')
        d=Diagnostics(); d.counts=Broken(); s=self.sender(d); peer=SimpleNamespace(send=AsyncMock())
        await s.send(peer, '[]')
        peer.send.assert_awaited_once_with('[]')
        self.assertEqual(s.diagnostic_health()['observer_failures'], 2)
        self.assertFalse(s.diagnostic_health()['observer_calls_complete'])

    async def test_malformed_counter_and_error_counter_do_not_block(self):
        d=Diagnostics(); d.counts=None; d.errors=None
        s=self.sender(d); peer=SimpleNamespace(send=AsyncMock())
        await s.send(peer, '[]')
        self.assertEqual(peer.send.await_count, 1)
        self.assertEqual(s.diagnostic_health()['observer_failures'], 2)

    async def test_failed_output_preserves_ingestion_buffer_and_delivery(self):
        d=Diagnostics(); d.emit=lambda *a,**k: (_ for _ in ()).throw(OSError('diagnostic sink failed'))
        s=self.sender(d); plain=self.sender(None)
        for e in (fake_event('BTCUSDT',60000),fake_event('BTCUSDT',60000,True)):
            self.assertEqual(s.ingest(e),plain.ingest(e))
        self.assertEqual(s.buffer.pending,plain.buffer.pending)
        peer=SimpleNamespace(send=AsyncMock()); await s.flush(peer)
        self.assertEqual(peer.send.await_count,1); self.assertFalse(s.buffer.pending)
        self.assertGreater(s._diagnostic_failures,0)

    async def test_saturation_explicit_loss_not_delivery_loss(self):
        d=Diagnostics(16); s=self.sender(d); peer=SimpleNamespace(send=AsyncMock())
        for _ in range(30): await s.send(peer,'[]')
        self.assertEqual(peer.send.await_count,30)
        self.assertEqual(len(d.records),16);self.assertEqual(d.overwritten,44)
        self.assertFalse(d.snapshot()['records_complete'])

    async def test_market_delivery_failure_not_masked(self):
        d=Diagnostics(); d.counts=None; s=self.sender(d)
        peer=SimpleNamespace(send=AsyncMock(side_effect=ValueError('market failure')))
        with self.assertRaisesRegex(ValueError,'market failure'): await s.send(peer,'[]')

    async def test_cancellation_preserved(self):
        d=Diagnostics(); d.counts=None; s=self.sender(d)
        peer=SimpleNamespace(send=AsyncMock(side_effect=asyncio.CancelledError))
        with self.assertRaises(asyncio.CancelledError): await s.send(peer,'[]')

    async def test_fatal_diagnostic_errors_not_suppressed(self):
        for error in (MemoryError, SystemExit, KeyboardInterrupt):
            d=Diagnostics(); d.emit=lambda *a,**k: (_ for _ in ()).throw(error())
            with self.assertRaises(error): self.sender(d).diagnostic('emit','test')

    def test_invalid_market_data_still_raises(self):
        d=Diagnostics(); d.counts=None; s=self.sender(d)
        event=fake_event('BTCUSDT',60000); event['k']['v']='-1'
        with self.assertRaises(ValueError): s.ingest(event)

    def test_observer_failure_counter_is_bounded(self):
        d=Diagnostics(); d.counts=None; s=self.sender(d);s._diagnostic_failures=2**63-1
        s.diagnostic('emit','test')
        self.assertEqual(s._diagnostic_failures,2**63-1)
