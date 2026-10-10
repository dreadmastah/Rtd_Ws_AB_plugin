import asyncio
import importlib.util
import json
import unittest
from pathlib import Path
from Binance.sender import CandleBuffer, record

spec = importlib.util.spec_from_file_location('relay', Path(__file__).parents[1] / 'Relay/Server/Python/relay.py')
relay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relay)

def event(symbol='BTCUSDT', stamp=60000, E=61000, closed=False, volume='7'):
    return dict(e='kline', s=symbol, E=E,
                k=dict(i='1m', t=stamp, x=closed, o='10', h='12', l='9', c='11', v=volume))

class Candles(unittest.TestCase):
    def test_volume_replacement_and_minute_boundary(self):
        b = CandleBuffer()
        b.ingest(event())
        b.ingest(event(E=62000, volume='8'))
        b.ingest(event(E=63000, closed=True, volume='9'))
        b.ingest(event(stamp=120000, E=120001, volume='1'))
        self.assertEqual([r['v'] for r in b.pending.values()], [9, 1])
        self.assertEqual(next(iter(b.pending.values()))['t'], 100)
        self.assertEqual(next(iter(b.pending.values()))['d'], 19700101)
        self.assertEqual(next(iter(next(iter(b.pending.values())))), 'n')

    def test_stale_after_final_ignored(self):
        b = CandleBuffer()
        b.ingest(event(closed=True))
        self.assertFalse(b.ingest(event(E=62000)))
        self.assertFalse(b.ingest(event(E=60000, closed=True)))

    def test_500_symbols_coalesce(self):
        b = CandleBuffer()
        for cycle in range(4):
            for i in range(500):
                b.ingest(event(str(i), E=61000+cycle, volume=str(cycle)))
        self.assertEqual(len(b.pending), 500)
        self.assertTrue(all(r['v'] == 3 for r in b.pending.values()))

    def test_capacity_is_explicit_failure(self):
        b = CandleBuffer(1)
        b.ingest(event())
        with self.assertRaises(OverflowError):
            b.ingest(event('ETHUSDT'))

    def test_bad_values(self):
        for values in ([1, 2, 0, 1, 1], [10, 9, 8, 10, 1], [10,12,9,11,'NaN']):
            with self.assertRaises(ValueError):
                record('X', 0, values)

class RelayTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_peer_does_not_block_healthy(self):
        class Peer:
            def __init__(self): self.closed = False
            async def close(self, *args): self.closed = True
        r = relay.Relay(1)
        slow, fast = Peer(), Peer()
        q1, q2 = asyncio.Queue(1), asyncio.Queue(1)
        q1.put_nowait('old')
        peers = {slow:q1, fast:q2}
        await r.broadcast(peers, 'new')
        await asyncio.sleep(0)
        self.assertEqual(q2.get_nowait(), 'new')
        self.assertTrue(slow.closed)
        self.assertNotIn(slow, peers)
        self.assertEqual(r.overflows, 1)

    async def test_legacy_protocol_end_to_end(self):
        from websockets.asyncio.client import connect
        from websockets.asyncio.server import serve
        r = relay.Relay()
        async with serve(r.handler, '127.0.0.1', 0) as server:
            port = server.sockets[0].getsockname()[1]
            async with connect(f'ws://127.0.0.1:{port}') as receiver, connect(f'ws://127.0.0.1:{port}') as sender:
                await receiver.send('rolerecv')
                await sender.send('rolesend')
                # Wait until both handshake registrations are processed.
                for _ in range(100):
                    if r.clients and r.senders: break
                    await asyncio.sleep(.001)
                payload = json.dumps([record('BTCUSDT',60000,[10,12,9,11,7])])
                await sender.send(payload)
                self.assertEqual(await asyncio.wait_for(receiver.recv(), 1), payload)
                await receiver.send('{"cmd":"bffull","arg":"BTCUSDT"}')
                self.assertIn('bffull', await asyncio.wait_for(sender.recv(),1))
        self.assertFalse(r.clients)
        self.assertFalse(r.senders)

if __name__ == '__main__': unittest.main()
