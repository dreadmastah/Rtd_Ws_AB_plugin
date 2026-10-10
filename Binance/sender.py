"""Binance USDT perpetual 1m sender for the existing WSRTD relay protocol."""
import argparse
import asyncio
import json
import logging
import math
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

LOG = logging.getLogger('binance')


def compact(value):
    return json.dumps(value, separators=(',', ':'), allow_nan=False)


def record(symbol, stamp, values):
    dt = datetime.fromtimestamp(stamp / 1000, timezone.utc)
    nums = [float(v) for v in values]
    if len(nums) != 5 or not all(math.isfinite(v) for v in nums):
        raise ValueError('Invalid OHLCV')
    o, h, l, c, v = nums
    if not (0 < l <= min(o, c) <= max(o, c) <= h) or v < 0:
        raise ValueError('Inconsistent OHLCV')
    # n must be first. v is cumulative BASE volume, never a delta.
    return dict(n=symbol, d=int(dt.strftime('%Y%m%d')),
                t=int(dt.strftime('%H%M%S')), o=o, h=h, l=l, c=c, v=v)


class CandleBuffer:
    """Coalesce within a bar, retain distinct minute boundaries until sent."""
    def __init__(self, capacity=5000):
        self.pending = {}
        self.seen = {}
        self.capacity = capacity

    def ingest(self, event):
        event = event.get('data', event)
        if event.get('e') != 'kline':
            return False
        k = event['k']
        if k['i'] != '1m':
            return False
        symbol, stamp = event['s'], int(k['t'])
        version = (stamp, int(event['E']), bool(k['x']))
        old = self.seen.get(symbol)
        if old and (version < old or (stamp == old[0] and old[2] and not k['x'])):
            return False
        rec = record(symbol, stamp, [k[x] for x in ('o', 'h', 'l', 'c', 'v')])
        key = (symbol, stamp)
        if key not in self.pending and len(self.pending) >= self.capacity:
            raise OverflowError('Candle backlog full; refusing to discard bars')
        self.seen[symbol] = version
        self.pending[key] = rec
        return True


class Sender:
    def __init__(self, args, session):
        self.args, self.session = args, session
        self.buffer = CandleBuffer()
        self.symbols = []
        self.last_request = 0
        self.rest_lock = asyncio.Lock()
        self.commands = asyncio.Queue(128)
        self.received = self.sent = 0

    async def rest(self, path, **params):
        # Serialize REST globally; 499-bar kline requests cost less than 500+.
        async with self.rest_lock:
            for attempt in range(6):
                await asyncio.sleep(max(0, self.last_request + .25 - time.monotonic()))
                self.last_request = time.monotonic()
                async with self.session.get(self.args.rest + path, params=params) as resp:
                    if resp.status in (418, 429):
                        delay = max(60 if resp.status == 418 else 1,
                                    float(resp.headers.get('Retry-After', 60)))
                        LOG.warning('REST throttled %s; pausing %ss', resp.status, delay)
                        await asyncio.sleep(delay)
                        continue
                    if resp.status >= 500:
                        await asyncio.sleep(min(30, 2 ** attempt))
                        continue
                    resp.raise_for_status()
                    return await resp.json()
            raise RuntimeError('REST retries exhausted')

    async def discover(self):
        info = await self.rest('/fapi/v1/exchangeInfo')
        eligible = {s['symbol'] for s in info['symbols']
                    if s['quoteAsset'] == 'USDT' and s['contractType'] == 'PERPETUAL'
                    and s['status'] == 'TRADING'}
        if self.args.symbols:
            selected = list(dict.fromkeys(Path(self.args.symbols).read_text().upper().split()))
            bad = set(selected) - eligible
            if bad:
                raise ValueError(f'Not trading USDT perpetuals: {sorted(bad)}')
        else:
            selected = sorted(eligible)
        self.symbols = selected[:self.args.limit]
        if not self.symbols:
            raise ValueError('No eligible symbols')
        LOG.info('Universe: %s selected, %s eligible', len(self.symbols), len(eligible))

    async def shard(self, symbols):
        delay = 1
        while True:
            try:
                async with connect(self.args.ws, ping_interval=None, compression=None,
                                   max_queue=256, max_size=1024 * 1024) as ws:
                    # Subscription request, not a 500-symbol URL. Reader runs immediately.
                    await ws.send(compact(dict(method='SUBSCRIBE',
                                               params=[s.lower() + '@kline_1m' for s in symbols],
                                               id=str(time.time_ns()))))
                    delay = 1
                    started = time.monotonic()
                    while time.monotonic() - started < 23 * 3600:
                        message = await asyncio.wait_for(ws.recv(), 180)
                        event = json.loads(message)
                        if 'code' in event:
                            raise RuntimeError(f'Subscription rejected: {event}')
                        payload = event.get('data', event)
                        if payload.get('s') in symbols and self.buffer.ingest(event):
                            self.received += 1
                LOG.info('Rotating shard; use backfill to repair any missed bars')
            except (OSError, ConnectionClosed, TimeoutError, RuntimeError, ValueError) as exc:
                LOG.warning('Shard reconnect: %s', exc)
            await asyncio.sleep(delay + random.random())
            delay = min(60, delay * 2)

    async def history(self, ws, symbol, days):
        if symbol not in self.symbols:
            raise ValueError('Symbol outside configured universe')
        end = int(time.time() // 60 * 60000) - 1  # closed bars only
        start = end + 1 - days * 86400000
        while start <= end:
            rows = await self.rest('/fapi/v1/klines', symbol=symbol, interval='1m',
                                   startTime=start, endTime=end, limit=499)
            if not rows:
                break
            bars = []
            for row in rows:
                rec = record(symbol, row[0], row[1:6])
                bars.append([rec[x] for x in ('d', 't', 'o', 'h', 'l', 'c', 'v')])
            await ws.send(compact(dict(hist=symbol, format='dtohlcv', bars=bars)))
            start = int(rows[-1][0]) + 60000
            await self.flush(ws)

    async def receive_commands(self, ws):
        async for message in ws:
            try:
                cmd = json.loads(message)
                if isinstance(cmd, dict) and 'cmd' in cmd and 'code' not in cmd:
                    await self.commands.put(cmd)
            except ValueError:
                LOG.warning('Ignoring non-JSON command')
        raise ConnectionError('Relay disconnected')

    async def output(self, ws):
        # One writer owns RTD, history, and command responses.
        # History can temporarily delay RTD; pending bars remain keyed by minute.
        while True:
            try:
                cmd = self.commands.get_nowait()
            except asyncio.QueueEmpty:
                cmd = None
            if cmd:
                name = cmd['cmd']
                try:
                    arg = str(cmd.get('arg', '')).split()
                    if name in ('bfauto', 'bffull', 'bfsym'):
                        symbol = arg[1] if name == 'bfsym' else arg[0]
                        days = int(arg[2]) if name == 'bfsym' else self.args.history_days
                        if not 1 <= days <= 7:
                            raise ValueError('Backfill days must be 1..7')
                        await self.history(ws, symbol, days)
                    else:
                        raise ValueError('Fixed universe: edit symbols file and restart; unsupported command')
                    await ws.send(compact(dict(cmd=name, code=200, arg='Backfill complete')))
                except (ValueError, IndexError, aiohttp.ClientError, RuntimeError) as exc:
                    await ws.send(compact(dict(cmd=name, code=400, arg=str(exc))))
            await self.flush(ws)
            await asyncio.sleep(self.args.flush_ms / 1000)

    async def flush(self, ws):
        items = sorted(self.buffer.pending.items(), key=lambda item: (item[0][1], item[0][0]))
        for pos in range(0, len(items), self.args.batch_size):
            chunk = items[pos:pos + self.args.batch_size]
            await asyncio.wait_for(ws.send(compact([rec for _, rec in chunk])), 10)
            for key, rec in chunk:
                # An update may arrive while send yields: don't remove its replacement.
                if self.buffer.pending.get(key) is rec:
                    del self.buffer.pending[key]
            self.sent += len(chunk)

    async def relay(self):
        while True:
            try:
                async with connect(self.args.relay, compression=None, max_size=4*1024*1024) as ws:
                    await ws.send('rolesend')
                    tasks = [asyncio.create_task(self.receive_commands(ws)),
                             asyncio.create_task(self.output(ws))]
                    try:
                        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                        for task in done:
                            task.result()
                    finally:
                        for task in tasks:
                            task.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
            except (OSError, ConnectionClosed, TimeoutError) as exc:
                LOG.warning('Relay reconnect: %s', exc)
            await asyncio.sleep(2)

    async def metrics(self):
        while True:
            await asyncio.sleep(10)
            LOG.info('received=%s sent_records=%s pending_bars=%s',
                     self.received, self.sent, len(self.buffer.pending))

    async def run(self):
        await self.discover()
        tasks = [asyncio.create_task(self.relay()), asyncio.create_task(self.metrics())]
        tasks += [asyncio.create_task(self.shard(set(self.symbols[i:i+self.args.shard_size])))
                  for i in range(0, len(self.symbols), self.args.shard_size)]
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


def arguments():
    p = argparse.ArgumentParser()
    p.add_argument('--limit', type=int, default=500)
    p.add_argument('--symbols', help='Whitespace-separated priority list; optional')
    p.add_argument('--shard-size', type=int, default=100)
    p.add_argument('--batch-size', type=int, default=100)
    p.add_argument('--flush-ms', type=int, default=250)
    p.add_argument('--history-days', type=int, default=1)
    p.add_argument('--relay', default='ws://127.0.0.1:10101')
    p.add_argument('--ws', default='wss://fstream.binance.com/market/stream')
    p.add_argument('--rest', default='https://fapi.binance.com')
    a = p.parse_args()
    if not (1 <= a.limit <= 500 and 1 <= a.shard_size <= 100 and
            1 <= a.batch_size <= 100 and 50 <= a.flush_ms <= 5000 and
            1 <= a.history_days <= 7):
        p.error('Invalid limit, shard-size, batch-size, flush-ms, or history-days')
    return a


async def main(args):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        await Sender(args, session).run()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        asyncio.run(main(arguments()))
    except KeyboardInterrupt:
        pass
