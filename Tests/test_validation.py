import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from Binance.sender import Sender, eligible_symbols, save_universe
from Benchmarks.load_sender import synthetic_records, run as run_load
from test_binance import event, relay


class UniverseTests(unittest.TestCase):
    def test_exact_filter_and_saved_nested_watchlists(self):
        def item(symbol, **kw):
            return dict(symbol=symbol, **(dict(quoteAsset='USDT',
                        contractType='PERPETUAL', status='TRADING') | kw))
        info = dict(symbols=[item(f'S{i:03d}USDT') for i in range(260)] + [
            item('USDC', quoteAsset='USDC'), item('DELIVERY', contractType='CURRENT_QUARTER'),
            item('HALTED', status='SETTLING'), item('SPOT', contractType=''),
            item('S000USDT')])
        selected = eligible_symbols(info)
        self.assertEqual(len(selected), 260)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'universe'
            save_universe(root, info, selected)
            for n in (13, 100, 250, 500):
                self.assertEqual((root / f'watchlist-{n}.tls').read_text().split(),
                                 selected[:n])
                self.assertEqual((root / f'watchlist-{n}.tls').read_bytes(),
                                 ('\r\n'.join(selected[:n])+'\r\n').encode('utf-8'))
            self.assertEqual(json.loads((root/'universe.json').read_text())
                             ['stage_actual_counts']['500'], 260)
            with self.assertRaises(FileExistsError):
                save_universe(root, info, selected)

    def test_utc_date_boundary_synthetic_volume(self):
        before = synthetic_records(['BTCUSDT'], 1767225599000, 9)[0]
        after = synthetic_records(['BTCUSDT'], 1767225600000, 0)[0]
        self.assertEqual((before['d'], before['t'], before['v']), (20251231, 235900, 10))
        self.assertEqual((after['d'], after['t'], after['v']), (20260101, 0, 1))


class SenderTests(unittest.IsolatedAsyncioTestCase):
    async def test_path_relay_receiver_without_handshake(self):
        instance = relay.Relay(protocol='path')
        async with serve(instance.handler, '127.0.0.1', 0) as server:
            url = f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}'
            async with connect(url) as receiver, connect(url+'/sender') as sender:
                await sender.send('rolesend')
                await sender.send('[{"n":"BTCUSDT"}]')
                self.assertEqual(await asyncio.wait_for(receiver.recv(), 2), '[{"n":"BTCUSDT"}]')
                await receiver.send('{"cmd":"bfauto","arg":"BTCUSDT"}')
                self.assertEqual(await asyncio.wait_for(sender.recv(), 2),
                                 '{"cmd":"bfauto","arg":"BTCUSDT"}')

    async def test_path_relay_rejects_unknown_path_and_conflicting_role(self):
        instance = relay.Relay(protocol='path')
        async with serve(instance.handler, '127.0.0.1', 0) as server:
            url = f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}'
            async with connect(url+'/unknown') as unknown:
                await asyncio.wait_for(unknown.wait_closed(), 2)
                self.assertEqual(unknown.close_code, 1008)
            async with connect(url) as receiver:
                await receiver.send('rolesend')
                await asyncio.wait_for(receiver.wait_closed(), 2)
                self.assertEqual(receiver.close_code, 1008)

    def sender(self):
        return Sender(SimpleNamespace(batch_size=100, history_days=1, flush_ms=50), None)

    async def test_synthetic_large_interval_respects_deadline(self):
        received = []
        async def collect(ws):
            self.assertEqual(await ws.recv(), 'rolesend')
            async for message in ws:
                received.extend(json.loads(message))
        async with serve(collect, '127.0.0.1', 0) as server:
            args = SimpleNamespace(symbols=1, symbols_file=None, interval=61,
                                   seconds=.05, relay=f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}')
            with patch('builtins.print'):
                await asyncio.wait_for(run_load(args), 2)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]['v'], 1)

    async def test_failed_send_retains_pending_and_reconnect_flushes(self):
        s = self.sender()
        s.buffer.ingest(event())
        ws = SimpleNamespace(send=AsyncMock(side_effect=OSError('disconnect')))
        with self.assertRaises(OSError):
            await s.flush(ws)
        self.assertEqual(len(s.buffer.pending), 1)
        ws.send = AsyncMock()
        await s.flush(ws)
        self.assertEqual(len(s.buffer.pending), 0)
        self.assertEqual(json.loads(ws.send.call_args.args[0])[0]['v'], 7)

    async def test_update_during_send_not_deleted(self):
        s = self.sender()
        s.buffer.ingest(event())
        async def send(_):
            s.buffer.ingest(event(E=62000, volume='8'))
        await s.flush(SimpleNamespace(send=send))
        self.assertEqual(next(iter(s.buffer.pending.values()))['v'], 8)

    async def test_history_pagination_and_closed_bar_cutoff(self):
        s = self.sender()
        s.symbols = ['BTCUSDT']
        calls = []
        async def rest(path, **params):
            calls.append(params)
            if len(calls) > 2:
                return []
            return [[params['startTime'], '10', '12', '9', '11', '7']]
        s.rest = rest
        ws = SimpleNamespace(send=AsyncMock())
        await s.history(ws, 'BTCUSDT', 1)
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0]['endTime'] % 60000, 59999)
        self.assertEqual(calls[1]['startTime'] - calls[0]['startTime'], 60000)
        payload = json.loads(ws.send.call_args.args[0])
        self.assertEqual(payload['format'], 'dtohlcv')
        self.assertEqual(payload['bars'][0][-1], 7)
        with self.assertRaises(ValueError):
            await s.history(ws, 'UNKNOWN', 1)

    async def test_real_websocket_relay_disconnect_reconnect_and_backfill(self):
        r = relay.Relay()
        s = self.sender()
        s.symbols = ['BTCUSDT']
        calls = 0
        async def rest(path, **params):
            nonlocal calls
            calls += 1
            return ([[params['startTime'], '10', '12', '9', '11', '7']]
                    if calls == 1 else [])
        s.rest = rest
        async with serve(r.handler, '127.0.0.1', 0) as server:
            s.args.relay = f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}'
            task = asyncio.create_task(s.relay())
            try:
                async with connect(s.args.relay) as receiver:
                    await receiver.send('rolerecv')
                    async with asyncio.timeout(5):
                        while not r.senders or not r.clients:
                            await asyncio.sleep(.01)
                    s.buffer.ingest(event())
                    first = json.loads(await asyncio.wait_for(receiver.recv(), 3))
                    self.assertEqual(first[0]['v'], 7)
                    old = next(iter(r.senders))
                    await old.close(1012, 'Controlled test disconnect')
                    s.buffer.ingest(event(stamp=120000, E=120001, volume='1'))
                    second = json.loads(await asyncio.wait_for(receiver.recv(), 6))
                    self.assertEqual(second[0]['t'], 200)
                    self.assertEqual(second[0]['v'], 1)
                    self.assertIsNot(next(iter(r.senders)), old)
                    await receiver.send(json.dumps(dict(cmd='bffull',arg='BTCUSDT')))
                    history = json.loads(await asyncio.wait_for(receiver.recv(), 3))
                    reply = json.loads(await asyncio.wait_for(receiver.recv(), 3))
                    self.assertEqual(history['bars'][0][-1], 7)
                    self.assertEqual(reply['code'], 200)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def test_upstream_reconnect_resubscribes(self):
        connections = 0
        subscriptions = []
        async def upstream(ws):
            nonlocal connections
            connections += 1
            subscriptions.append(json.loads(await ws.recv()))
            await ws.send(json.dumps(event(stamp=60000*connections,
                                          E=60000*connections+1)))
            if connections == 1:
                await ws.close(1012, 'Controlled upstream disconnect')
            else:
                await ws.wait_closed()
        s = self.sender()
        async with serve(upstream, '127.0.0.1', 0) as server:
            s.args.ws = f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}'
            task = asyncio.create_task(s.shard({'BTCUSDT'}))
            try:
                async with asyncio.timeout(6):
                    while s.received < 2:
                        await asyncio.sleep(.01)
                self.assertEqual([sub['params'] for sub in subscriptions],
                                 [['btcusdt@kline_1m'], ['btcusdt@kline_1m']])
                self.assertEqual(len(s.buffer.pending), 2)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
