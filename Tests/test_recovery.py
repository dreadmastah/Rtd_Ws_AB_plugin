import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from Binance.sender import Sender
from test_binance import event


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    def sender(self, symbols=None):
        s = Sender(SimpleNamespace(batch_size=100, flush_ms=50,
                                   native_history=True, history_days=1), None)
        s.symbols = symbols or ['BTCUSDT']
        return s

    async def full_rest(self, path, **p):
        step = 60000 if p['interval'] == '1m' else 86400000
        return [[t, '10', '12', '9', '11', '17'] for t in
                list(range(p['startTime'], p['endTime'] + 1, step))[:p['limit']]]

    async def test_reconnect_repairs_unfinished_minute_and_missing_minutes(self):
        s = self.sender()
        s.ingest(event())
        with patch('Binance.sender.time.time', return_value=245):
            s.repair_shard(s.symbols)
        self.assertEqual(s.repairs, {('BTCUSDT', '1m'): (60000, 240000)})
        s.rest = AsyncMock(side_effect=self.full_rest)
        ws = SimpleNamespace(send=AsyncMock())
        await s.repair_one(ws)
        frame = json.loads(ws.send.call_args.args[0])
        self.assertEqual([r[1] for r in frame['bars']], [100, 200, 300])
        self.assertTrue(all(r[-1] == 17 for r in frame['bars']))
        self.assertFalse(s.repairs)
        # A later quote must never re-emit the unfinished pre-outage volume.
        s.buffer.ingest_quote(dict(e='bookTicker', s='BTCUSDT', E=250000,
                                   b='10', B='1', a='12', A='1'))
        self.assertEqual(s.buffer.pending[('BTCUSDT', 180000)]['v'], 17)
        self.assertNotIn(('BTCUSDT', 60000), s.buffer.pending)
        self.assertFalse(s.ingest(event(E=250001, volume='8')))

    async def test_boundary_repairs_missing_final_even_without_disconnect(self):
        s = self.sender()
        s.ingest(event())
        s.ingest(event(stamp=120000, E=120001))
        self.assertEqual(s.repairs[('BTCUSDT', '1m')], (60000, 120000))
        s = self.sender()
        s.ingest(event(closed=True))
        s.ingest(event(stamp=120000, E=120001))
        self.assertFalse(s.repairs)
        s.ingest(event(stamp=300000, E=300001))
        self.assertEqual(s.repairs[('BTCUSDT', '1m')], (120000, 300000))

    async def test_retry_does_not_claim_sparse_or_failed_rest_is_complete(self):
        s = self.sender()
        s.queue_repair('BTCUSDT', '1m', 60000, 240000)
        s.rest = AsyncMock(return_value=[[120000, '10', '12', '9', '11', '17']])
        ws = SimpleNamespace(send=AsyncMock())
        await s.repair_one(ws)
        self.assertTrue(s.repairs)
        ws.send.assert_not_awaited()
        self.assertFalse(await s.repair_one(ws))
        s.retry_after.clear()
        s.rest = AsyncMock(side_effect=self.full_rest)
        await s.repair_one(ws)
        self.assertFalse(s.repairs)

    async def test_utc_rollover_catches_multiple_days_and_never_current_day(self):
        s = self.sender()
        day = 86400000
        s.daily_through['BTCUSDT'] = day * 10
        s.daily_rechecked['BTCUSDT'] = day * 10
        with patch('Binance.sender.time.time', return_value=day * 10 / 1000 + 86399):
            s.schedule_rollover()
        self.assertFalse(s.repairs)
        with patch('Binance.sender.time.time', return_value=day * 12 / 1000 + 60):
            s.schedule_rollover()
            s.schedule_rollover()
        self.assertEqual(s.repairs, {('BTCUSDT', '1d'): (day * 10, day * 12)})
        s.rest = AsyncMock(side_effect=self.full_rest)
        ws = SimpleNamespace(send=AsyncMock())
        await s.repair_one(ws)
        frame = json.loads(ws.send.call_args.args[0])
        self.assertEqual(frame['format'], 'dohlcv')
        self.assertEqual([r[0] for r in frame['bars']], [19700111, 19700112])
        self.assertEqual(s.daily_through['BTCUSDT'], day * 12)
        self.assertFalse(s.repairs)

    async def test_failed_daily_repair_keeps_cursor_and_retries(self):
        s = self.sender()
        s.daily_through['BTCUSDT'] = 86400000
        s.queue_repair('BTCUSDT', '1d', 86400000, 172800000)
        s.rest = AsyncMock(return_value=[])
        await s.repair_one(SimpleNamespace(send=AsyncMock()))
        self.assertEqual(s.daily_through['BTCUSDT'], 86400000)
        self.assertTrue(s.repairs)

    async def test_slow_rest_does_not_stop_live_updates(self):
        s = self.sender()
        entered, release = asyncio.Event(), asyncio.Event()
        async def rest(path, **p):
            entered.set()
            await release.wait()
            return await self.full_rest(path, **p)
        s.rest = rest
        ws = SimpleNamespace(send=AsyncMock())
        s.ingest(event(stamp=180000, E=180001))
        s.queue_repair('BTCUSDT', '1m', 60000, 180000)
        repair = asyncio.create_task(s.repair_one(ws))
        pump = asyncio.create_task(s.live_output(ws))
        try:
            async with asyncio.timeout(2):
                await entered.wait()
                while not ws.send.await_count:
                    await asyncio.sleep(.01)
            self.assertIsInstance(json.loads(ws.send.call_args.args[0]), list)
            self.assertFalse(repair.done())
            release.set()
            await repair
        finally:
            repair.cancel()
            pump.cancel()
            await asyncio.gather(repair, pump, return_exceptions=True)

    async def test_new_gap_queued_during_rest_is_not_lost(self):
        s = self.sender()
        s.queue_repair('BTCUSDT', '1m', 60000, 120000)
        async def rest(path, **p):
            s.queue_repair('BTCUSDT', '1m', 120000, 180000)
            return await self.full_rest(path, **p)
        s.rest = rest
        await s.repair_one(SimpleNamespace(send=AsyncMock()))
        self.assertEqual(s.repairs[('BTCUSDT', '1m')], (60000, 180000))
        s.rest = self.full_rest
        await s.repair_one(SimpleNamespace(send=AsyncMock()))
        self.assertFalse(s.repairs)

    async def test_long_outage_is_bounded_to_native_retention(self):
        s = self.sender()
        s.queue_repair('BTCUSDT', '1m', 0, 2000 * 60000)
        s.rest = AsyncMock(side_effect=self.full_rest)
        ws = SimpleNamespace(send=AsyncMock())
        await s.repair_one(ws)
        frames = [json.loads(c.args[0]) for c in ws.send.call_args_list]
        self.assertEqual(sum(len(f['bars']) for f in frames), 1500)
        self.assertEqual(s.rest.call_args_list[0].kwargs['startTime'], 500 * 60000)

    async def test_500_symbol_jobs_coalesce_and_no_daily_jobs_in_default_mode(self):
        s = self.sender([f'S{i}' for i in range(500)])
        for symbol in s.symbols:
            for end in (120000, 180000, 240000):
                s.queue_repair(symbol, '1m', 60000, end)
        self.assertEqual(len(s.repairs), 500)
        s.args.native_history = False
        s.daily_through = dict.fromkeys(s.symbols, 0)
        s.schedule_rollover()
        self.assertEqual(len(s.repairs), 500)

    async def test_out_of_order_history_is_rejected_before_send(self):
        s = self.sender()
        s.rest = AsyncMock(return_value=[[120000, 10, 12, 9, 11, 7],
                                        [60000, 10, 12, 9, 11, 7]])
        ws = SimpleNamespace(send=AsyncMock())
        with self.assertRaises(ValueError):
            await s.history_range(ws, 'BTCUSDT', '1m', 60000, 180000)
        ws.send.assert_not_awaited()


    async def test_daily_settlement_delay_and_later_volume_correction(self):
        s = self.sender()
        day = 86400000
        boundary = day * 12
        s.daily_through['BTCUSDT'] = boundary-day
        s.daily_rechecked['BTCUSDT'] = boundary-day
        ws = SimpleNamespace(send=AsyncMock())
        s.rest = AsyncMock(return_value=[[boundary-day, 10, 12, 9, 11, 100]])
        with patch('Binance.sender.time.time', return_value=boundary/1000+1):
            s.schedule_rollover()
            self.assertFalse(s.repairs)
        with patch('Binance.sender.time.time', return_value=boundary/1000+60):
            s.schedule_rollover()
            await s.repair_one(ws)
        self.assertEqual(s.daily_through['BTCUSDT'], boundary)
        with patch('Binance.sender.time.time', return_value=boundary/1000+299):
            s.schedule_rollover()
            self.assertFalse(s.repairs)
        s.rest.return_value = [[boundary-day, 10, 12, 9, 11, 125]]
        with patch('Binance.sender.time.time', return_value=boundary/1000+300):
            s.schedule_rollover()
            await s.repair_one(ws)
            s.schedule_rollover()
        self.assertFalse(s.repairs)
        self.assertEqual(json.loads(ws.send.call_args.args[0])['bars'][0][-1], 125)
        self.assertEqual(s.daily_rechecked['BTCUSDT'], boundary)

    async def test_daily_preload_near_boundary_defers_newly_closed_bar(self):
        s = self.sender()
        day = 86400000
        s.rest = AsyncMock(side_effect=self.full_rest)
        with patch('Binance.sender.time.time', return_value=12*day/1000+1):
            await s.history(SimpleNamespace(send=AsyncMock()), 'BTCUSDT', 0,
                            interval='1d', count=1)
        self.assertEqual(s.rest.call_args.kwargs['endTime'], 11*day-1)
        self.assertEqual(s.daily_through['BTCUSDT'], 11*day)

    async def test_failed_daily_recheck_remains_pending(self):
        s = self.sender()
        day = 86400000
        s.daily_through['BTCUSDT'] = day*12
        s.daily_rechecked['BTCUSDT'] = day*11
        s.rest = AsyncMock(return_value=[])
        with patch('Binance.sender.time.time', return_value=12*day/1000+300):
            s.schedule_rollover()
            await s.repair_one(SimpleNamespace(send=AsyncMock()))
        self.assertIn(('BTCUSDT', '1d'), s.repairs)
        self.assertEqual(s.daily_rechecked['BTCUSDT'], day*11)

    async def test_stalled_symbol_repairs_without_shard_reconnect(self):
        s = self.sender(['BTCUSDT', 'ETHUSDT'])
        s.ingest(event(stamp=60000, E=60001, closed=True))
        s.buffer.ingest_quote(dict(e='bookTicker', s='BTCUSDT', E=210000,
                                  b='10', B='1', a='12', A='1'))
        with patch('Binance.sender.time.time', return_value=211):
            s.schedule_stale_repairs()
        self.assertEqual(s.repairs[('BTCUSDT', '1m')], (120000, 180000))
        s.rest = AsyncMock(side_effect=self.full_rest)
        ws = SimpleNamespace(send=AsyncMock())
        await s.repair_one(ws)
        self.assertEqual(s.buffer.latest['BTCUSDT'][0][1], 120000)
        self.assertEqual(s.buffer.latest['BTCUSDT'][1]['v'], 17)
        self.assertEqual(s.buffer.pending[('BTCUSDT', 120000)]['bp'], 10)
        s.schedule_stale_repairs()
        self.assertFalse(s.repairs)  # per-symbol cooldown
        self.assertNotIn('ETHUSDT', s.buffer.latest)  # no fabricated unseen bar

    async def test_rest_repair_does_not_replace_newer_websocket_candle(self):
        s = self.sender()
        s.ingest(event(stamp=60000, E=60001, closed=True))
        s.queue_repair('BTCUSDT', '1m', 120000, 180000)
        async def rest(path, **params):
            s.ingest(event(stamp=240000, E=240001, volume='4'))
            return await self.full_rest(path, **params)
        s.rest = rest
        await s.repair_one(SimpleNamespace(send=AsyncMock()))
        self.assertEqual(s.buffer.latest['BTCUSDT'][0][1], 240000)
        self.assertEqual(s.buffer.latest['BTCUSDT'][1]['v'], 4)


    async def test_request_started_before_recheck_window_is_not_confirmation(self):
        s = self.sender()
        day = 86400000
        s.daily_through['BTCUSDT'] = day*11
        s.queue_repair('BTCUSDT', '1d', day*11, day*12)
        s.rest = AsyncMock(side_effect=self.full_rest)
        # Completion time may cross the threshold; the request began too early.
        with patch('Binance.sender.time.time', side_effect=[12*day/1000+299,
                                                           12*day/1000+301]):
            await s.repair_one(SimpleNamespace(send=AsyncMock()))
        self.assertNotIn('BTCUSDT', s.daily_rechecked)
        with patch('Binance.sender.time.time', return_value=12*day/1000+301):
            s.schedule_rollover()
        self.assertIn(('BTCUSDT', '1d'), s.repairs)

    async def test_history_page_does_not_reenqueue_every_repaired_candle(self):
        s = self.sender()
        s.ingest(event(stamp=60000, E=60001, closed=True))
        s.buffer.pending.clear()
        s.rest = AsyncMock(side_effect=self.full_rest)
        await s.history_range(SimpleNamespace(send=AsyncMock()), 'BTCUSDT',
                              '1m', 120000, 300000)
        self.assertEqual(set(s.buffer.pending), {('BTCUSDT', 240000)})
