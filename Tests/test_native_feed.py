import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from Binance.sender import CandleBuffer, Sender
from test_binance import event


class QuoteTests(unittest.TestCase):
    def test_quote_updates_preserve_candle_and_cumulative_volume(self):
        b = CandleBuffer()
        b.ingest(event())
        b.pending.clear()
        ticker = dict(e='24hrTicker', s='BTCUSDT', E=62000,
                      o='8', h='20', l='5', c='11', p='2', v='9999')
        b.ingest_quote(ticker)
        b.ingest_quote(dict(e='bookTicker', s='BTCUSDT', E=62001,
                            b='10.9', B='12', a='11.1', A='13'))
        rec = next(iter(b.pending.values()))
        self.assertEqual([rec[k] for k in 'ohlcv'], [10, 12, 9, 11, 7])
        self.assertEqual([rec[k] for k in ('s', 'pc', 'do', 'dh', 'dl')],
                         [9999, 9, 8, 20, 5])
        self.assertEqual([rec[k] for k in ('bp', 'bs', 'ap', 'as')],
                         [10.9, 12, 11.1, 13])
        self.assertFalse(b.ingest_quote(ticker | {'E': 61000, 'v': '1'}))
        b.ingest(event(stamp=120000, E=120001, volume='2'))
        self.assertEqual(b.pending[('BTCUSDT', 120000)]['s'], 9999)

    def test_quote_before_candle_never_fabricates_bar(self):
        b = CandleBuffer()
        b.ingest_quote(dict(e='bookTicker', s='BTCUSDT', E=62001,
                            b='10.9', B='12', a='11.1', A='13'))
        self.assertFalse(b.pending)
        b.ingest(event())
        self.assertEqual(next(iter(b.pending.values()))['bp'], 10.9)


class HistoryTests(unittest.IsolatedAsyncioTestCase):
    def sender(self):
        s = Sender(SimpleNamespace(batch_size=100, flush_ms=50, native_history=True), None)
        s.symbols = ['BTCUSDT']
        return s

    async def test_native_preload_1500_minutes_300_native_daily_bars(self):
        s = self.sender()
        calls = []
        async def rest(path, **p):
            calls.append(p)
            step = 60000 if p['interval'] == '1m' else 86400000
            return [[t, '10', '12', '9', '11', '7'] for t in
                    list(range(p['startTime'], p['endTime'] + 1, step))[:p['limit']]]
        s.rest = rest
        ws = SimpleNamespace(send=AsyncMock())
        with patch('Binance.sender.time.time', return_value=1791624000):
            await s.native_history(ws, 'BTCUSDT')
        frames = [json.loads(c.args[0]) for c in ws.send.call_args_list]
        minute = [r for f in frames if f['format'] == 'dtohlcv' for r in f['bars']]
        daily = [r for f in frames if f['format'] == 'dohlcv' for r in f['bars']]
        self.assertEqual(len(minute), 1500)
        self.assertEqual(len(daily), 300)
        self.assertEqual(len({tuple(r[:2]) for r in minute}), 1500)
        self.assertTrue(all(len(r) == 6 for r in daily))
        self.assertEqual(daily[-1][0], 20261009)
        self.assertEqual(len(calls), 5)

    async def test_preload_runs_without_one_time_plugin_command(self):
        s = self.sender()
        s.native_history = AsyncMock()
        task = asyncio.create_task(s.output(SimpleNamespace(send=AsyncMock())))
        try:
            async with asyncio.timeout(1):
                while not s.native_history.await_count:
                    await asyncio.sleep(.01)
            self.assertEqual(s.native_history.call_args.args[1], 'BTCUSDT')
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_daily_command_and_out_of_universe_rejection(self):
        s = self.sender()
        s.args.native_history = False
        s.rest = AsyncMock(return_value=[])
        ws = SimpleNamespace(send=AsyncMock())
        await s.commands.put(dict(cmd='bfsymeod', arg='y BTCUSDT 2'))
        task = asyncio.create_task(s.output(ws))
        try:
            async with asyncio.timeout(1):
                while not ws.send.await_count:
                    await asyncio.sleep(.01)
            self.assertEqual(json.loads(ws.send.call_args.args[0])['code'], 200)
            self.assertEqual(s.rest.call_args.kwargs['interval'], '1d')
            with self.assertRaises(ValueError):
                await s.native_history(ws, 'UNKNOWN')
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
