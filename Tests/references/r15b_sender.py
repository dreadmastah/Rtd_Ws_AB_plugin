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
DAY_MS = 86400000
DAILY_SETTLE_SECONDS = 60
DAILY_RECHECK_SECONDS = 300


def daily_end(now):
    # A just-closed REST candle can still change immediately after midnight.
    return int((now - DAILY_SETTLE_SECONDS) * 1000) // DAY_MS * DAY_MS



def eligible_symbols(info):
    """One deterministic futures-only universe for feeds and watchlists."""
    return sorted({s['symbol'] for s in info['symbols']
                   if s.get('quoteAsset') == 'USDT'
                   and s.get('contractType') == 'PERPETUAL'
                   and s.get('status') == 'TRADING'})


def save_universe(directory, info, selected):
    """Create a fresh evidence directory; never overwrite a prior selection."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    eligible = eligible_symbols(info)
    (directory / 'exchangeInfo.json').write_text(
        json.dumps(info, indent=2) + '\n', encoding='utf-8')
    (directory / 'selected-symbols.txt').write_text(
        '\n'.join(selected) + '\n', encoding='utf-8')
    counts = {}
    for requested in (13, 100, 250, 500):
        subset = selected[:requested]
        counts[str(requested)] = len(subset)
        # AmiBroker import-watchlist format: CRLF, including on non-Windows hosts.
        (directory / f'watchlist-{requested}.tls').write_text(
            '\n'.join(subset) + '\n', encoding='utf-8', newline='\r\n')
    (directory / 'universe.json').write_text(json.dumps(dict(
        discovered_at_utc=datetime.now(timezone.utc).isoformat(),
        filter=dict(status='TRADING', quoteAsset='USDT', contractType='PERPETUAL'),
        eligible_count=len(eligible), selected_count=len(selected),
        selected=selected, stage_actual_counts=counts), indent=2) + '\n',
        encoding='utf-8')


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
        self.latest = {}
        self.quotes = {}
        self.quote_versions = {}

    def ingest_quote(self, event):
        symbol, kind = event['s'], event.get('e')
        fields = {'24hrTicker': {'s': 'v', 'do': 'o', 'dh': 'h', 'dl': 'l'},
                  'bookTicker': {'bp': 'b', 'bs': 'B', 'ap': 'a', 'as': 'A'}}
        if kind not in fields:
            return False
        version_key = (symbol, kind)
        version = int(event['E'])
        if version < self.quote_versions.get(version_key, -1):
            return False
        values = {dst: float(event[src]) for dst, src in fields[kind].items()}
        if kind == '24hrTicker':
            values['pc'] = float(event['c']) - float(event['p'])
        if not all(math.isfinite(v) and v >= 0 for v in values.values()):
            raise ValueError('Invalid quote values')
        self.quote_versions[version_key] = version
        self.quotes.setdefault(symbol, {}).update(values)
        if symbol in self.latest:
            key, candle = self.latest[symbol]
            if key not in self.pending and len(self.pending) >= self.capacity:
                raise OverflowError('Candle backlog full; refusing to discard bars')
            # Quote updates must never replace OHLCV with 24-hour totals.
            self.pending[key] = dict(candle, **self.quotes[symbol])
        return True

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
        self.latest[symbol] = (key, rec)
        self.pending[key] = dict(rec, **self.quotes.get(symbol, {}))
        return True


class Sender:
    def __init__(self, args, session):
        self.args, self.session = args, session
        self.buffer = CandleBuffer()
        self.symbols = []
        self.last_request = 0
        self._rest_next_ns = 0
        self._rest_clock_ns = None
        self._rest_clock_failed = False
        self._rest_options = {}
        if isinstance(session, aiohttp.ClientSession):
            # Public per-request middleware runs for internal retries and
            # redirects too. Preserve their policy and any existing middleware.
            self._rest_options = dict(middlewares=(
                *session._middlewares, self._paced_rest_attempt))
        self.rest_lock = asyncio.Lock()
        self.commands = asyncio.Queue(128)
        self.received = self.sent = 0
        self.repairs = {}
        self.retry_after = {}
        self.daily_through = {}
        self.daily_rechecked = {}
        self.stale_retry_after = {}
        self.flush_lock = asyncio.Lock()
        self.send_lock = asyncio.Lock()

    def queue_repair(self, symbol, interval, start, end):
        """Coalesce closed-bar ranges; end is exclusive. At most two jobs/symbol."""
        if start >= end:
            return
        key = (symbol, interval)
        old = self.repairs.get(key)
        bounds = (min(start, old[0]), max(end, old[1])) if old else (start, end)
        if old != bounds:
            self.repairs[key] = bounds

    def repair_shard(self, symbols):
        end = int(time.time() * 1000) // 60000 * 60000
        for symbol in symbols:
            old = self.buffer.seen.get(symbol)
            if old:
                self.queue_repair(symbol, '1m', old[0] + (60000 if old[2] else 0), end)

    def ingest(self, event):
        payload = event.get('data', event)
        if payload.get('e') != 'kline':
            return self.buffer.ingest_quote(payload)
        old = self.buffer.seen.get(payload['s'])
        accepted = self.buffer.ingest(event)
        if accepted and old and int(payload['k']['t']) > old[0]:
            # Repair the previous minute too if its final update was missed.
            self.queue_repair(payload['s'], '1m',
                              old[0] + (60000 if old[2] else 0), int(payload['k']['t']))
        return accepted

    def schedule_rollover(self):
        if not getattr(self.args, 'native_history', False):
            return
        now = time.time()
        end = daily_end(now)
        for symbol, start in list(self.daily_through.items()):
            self.queue_repair(symbol, '1d', start, end)
            if (now * 1000 >= end + DAILY_RECHECK_SECONDS * 1000 and
                    self.daily_rechecked.get(symbol, 0) < end):
                self.queue_repair(symbol, '1d', end - DAY_MS, end)

    def schedule_stale_repairs(self):
        # Other symbols or quote streams can keep a shard alive while one
        # symbol's minute feed stalls. Repair real closed bars without inventing
        # a current candle or interpreting quote arrival as candle freshness.
        if not getattr(self.args, 'native_history', False):
            return
        now = time.time()
        end = int(now * 1000) // 60000 * 60000
        for symbol, old in list(self.buffer.seen.items()):
            if now * 1000 - old[0] <= 90000:
                continue
            if self.stale_retry_after.get(symbol, 0) > time.monotonic():
                continue
            start = old[0] + (60000 if old[2] else 0)
            if start < end:
                self.queue_repair(symbol, '1m', start, end)
                self.stale_retry_after[symbol] = time.monotonic() + 60

    async def send(self, ws, message):
        async with self.send_lock:
            await asyncio.wait_for(ws.send(message), 10)

    async def repair_one(self, ws):
        for key, bounds in list(self.repairs.items()):
            if self.retry_after.get(key, 0) > time.monotonic():
                continue
            symbol, interval = key
            step = 60000 if interval == '1m' else 86400000
            count = (300 if interval == '1d' else 1500 if
                     getattr(self.args, 'native_history', False) else self.args.history_days * 1440)
            end = bounds[1]
            start = max(bounds[0], end - count * step)
            if start != bounds[0]:
                LOG.warning('Repair retention limit symbol=%s interval=%s omitted_before=%s',
                            symbol, interval, start)
            requested_at = time.time()
            try:
                total = await self.history_range(ws, symbol, interval, start, end, strict=True)
            except (aiohttp.ClientError, TimeoutError, RuntimeError, ValueError) as exc:
                self.retry_after[key] = time.monotonic() + 60
                LOG.warning('Repair deferred symbol=%s interval=%s: %s', symbol, interval, exc)
            else:
                if self.repairs.get(key) == bounds:
                    del self.repairs[key]
                self.retry_after.pop(key, None)
                if interval == '1d':
                    self.daily_through[symbol] = max(end, self.daily_through.get(symbol, 0))
                    if requested_at * 1000 >= end + DAILY_RECHECK_SECONDS * 1000:
                        self.daily_rechecked[symbol] = max(
                            end, self.daily_rechecked.get(symbol, 0))
                LOG.info('Repair complete symbol=%s interval=%s start=%s end=%s bars=%s',
                         symbol, interval, start, end, total)
            return True
        return False

    async def live_output(self, ws):
        # REST cooldowns and slow responses must not stall live delivery.
        while True:
            await self.flush(ws)
            await asyncio.sleep(self.args.flush_ms / 1000)

    def _rest_now(self):
        now = time.perf_counter_ns()
        if (self._rest_clock_failed or type(now) is not int or now < 0 or
                (self._rest_clock_ns is not None and now < self._rest_clock_ns)):
            self._rest_clock_failed = True
            raise RuntimeError('REST monotonic clock anomaly; no request authorized')
        self._rest_clock_ns = now
        return now

    def _rest_finish(self):
        try:
            now = self._rest_now()
        except RuntimeError:
            # Poisoned clock prevents future requests; do not replace the
            # original cancellation/HTTP exception during cleanup.
            return
        self._rest_next_ns = max(self._rest_next_ns, now + 250_000_000)

    async def _rest_wait(self):
        # A wake is not proof of elapsed time. A stalled clock fails closed
        # after bounded nonprogress wakes; cancellation always propagates.
        stalled = 0
        while True:
            before = self._rest_now()
            remaining = self._rest_next_ns - before
            if remaining <= 0:
                return
            await asyncio.sleep(remaining / 1_000_000_000)
            after = self._rest_now()
            stalled = stalled + 1 if after == before else 0
            if stalled >= 16:
                raise RuntimeError('REST monotonic clock stalled; no request authorized')

    async def _paced_rest_attempt(self, request, handler):
        await self._rest_wait()
        try:
            return await handler(request)
        finally:
            # Completion is at or after actual dispatch, unlike construction
            # of get(). This conservative floor also covers hidden attempts.
            self._rest_finish()

    async def rest(self, path, **params):
        # Serialize REST globally; 499-bar kline requests cost less than 500+.
        async with self.rest_lock:
            for attempt in range(6):
                await self._rest_wait()
                self.last_request = time.monotonic()
                try:
                    async with self.session.get(self.args.rest + path, params=params,
                                                **self._rest_options) as resp:
                        if resp.status in (418, 429):
                            delay = max(60 if resp.status == 418 else 1,
                                        float(resp.headers.get('Retry-After', 60)))
                            # Persist the original policy's deadline before
                            # any cancellable wait releases the global lock.
                            self._rest_next_ns = max(self._rest_next_ns,
                                self._rest_now() + math.ceil(delay * 1_000_000_000))
                            LOG.warning('REST throttled %s; pausing %ss', resp.status, delay)
                            await self._rest_wait()
                            continue
                        if resp.status >= 500:
                            await asyncio.sleep(min(30, 2 ** attempt))
                            continue
                        resp.raise_for_status()
                        return await resp.json()
                finally:
                    self._rest_finish()
            raise RuntimeError('REST retries exhausted')

    async def discover(self):
        info = await self.rest('/fapi/v1/exchangeInfo')
        eligible = set(eligible_symbols(info))
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
        if getattr(self.args, 'universe_dir', None):
            save_universe(self.args.universe_dir, info, self.symbols)

    async def shard(self, symbols, public=False):
        delay = 1
        while True:
            try:
                endpoint = self.args.public_ws if public else self.args.ws
                streams = ['bookTicker'] if public else ['kline_1m']
                if not public and getattr(self.args, 'quotes', False):
                    streams.append('ticker')
                async with connect(endpoint, ping_interval=None, compression=None,
                                   max_queue=256, max_size=1024 * 1024) as ws:
                    # Subscription request, not a 500-symbol URL. Reader runs immediately.
                    await ws.send(compact(dict(method='SUBSCRIBE',
                                               params=[s.lower() + '@' + stream
                                                       for s in sorted(symbols) for stream in streams],
                                               id=str(time.time_ns()))))
                    if not public:
                        self.repair_shard(symbols)
                    delay = 1
                    started = time.monotonic()
                    while time.monotonic() - started < 23 * 3600:
                        message = await asyncio.wait_for(ws.recv(), 180)
                        event = json.loads(message)
                        if 'code' in event:
                            raise RuntimeError(f'Subscription rejected: {event}')
                        payload = event.get('data', event)
                        if payload.get('s') in symbols:
                            accepted = self.ingest(event)
                            if accepted:
                                self.received += 1
                LOG.info('Rotating shard; closed-bar recovery will follow reconnect')
            except (OSError, ConnectionClosed, TimeoutError, RuntimeError, ValueError) as exc:
                LOG.warning('Shard reconnect: %s', exc)
            await asyncio.sleep(delay + random.random())
            delay = min(60, delay * 2)

    async def history(self, ws, symbol, days, *, interval='1m', count=None):
        if symbol not in self.symbols:
            raise ValueError('Symbol outside configured universe')
        step = {'1m': 60000, '1d': 86400000}[interval]
        requested_at = time.time()
        end = (daily_end(requested_at) if interval == '1d' else
               int(requested_at * 1000) // step * step) - 1  # closed bars only
        start = end + 1 - (count * step if count is not None else days * 86400000)
        total = await self.history_range(ws, symbol, interval, start, end + 1)
        if interval == '1d':
            self.daily_through[symbol] = max(end + 1, self.daily_through.get(symbol, 0))
            if requested_at * 1000 >= end + 1 + DAILY_RECHECK_SECONDS * 1000:
                self.daily_rechecked[symbol] = max(
                    end + 1, self.daily_rechecked.get(symbol, 0))
        LOG.info('History symbol=%s interval=%s bars=%s', symbol, interval, total)
        return total

    async def history_range(self, ws, symbol, interval, start, end, *, strict=False):
        step = {'1m': 60000, '1d': 86400000}[interval]
        if symbol not in self.symbols or start % step or end % step or start > end:
            raise ValueError('Invalid history range or symbol')
        total = 0
        while start < end:
            rows = await self.rest('/fapi/v1/klines', symbol=symbol, interval=interval,
                                   startTime=start, endTime=end - 1, limit=499)
            if not rows:
                if strict:
                    raise ValueError('REST has not supplied the full repair range')
                break
            bars = []
            records = []
            previous = start - step
            for row in rows:
                stamp = int(row[0])
                if not start <= stamp < end or stamp % step or stamp <= previous:
                    raise ValueError('REST returned unordered, out-of-range or unfinished candles')
                if strict and stamp != previous + step:
                    raise ValueError('REST repair range has missing candles')
                rec = record(symbol, row[0], row[1:6])
                fields = 'dohlcv' if interval == '1d' else 'dtohlcv'
                bars.append([rec[x] for x in fields])
                records.append((stamp, rec))
                previous = stamp
            async with self.flush_lock:
                await self.send(ws, compact(dict(hist=symbol, format=fields, bars=bars)))
                if interval == '1m':
                    for stamp, rec in records:
                        self.buffer.pending.pop((symbol, stamp), None)
                        latest = self.buffer.latest.get(symbol)
                        if latest and latest[0][1] <= stamp:
                            self.buffer.latest[symbol] = ((symbol, stamp), rec)
                            old = self.buffer.seen[symbol]
                            self.buffer.seen[symbol] = (stamp, old[1], True)
                            # History already delivered the page. Only re-emit
                            # its newest real closed bar as the live snapshot.
                            if stamp == records[-1][0]:
                                if len(self.buffer.pending) >= self.buffer.capacity:
                                    raise OverflowError('Candle backlog full after repair')
                                self.buffer.pending[(symbol, stamp)] = dict(
                                    rec, **self.buffer.quotes.get(symbol, {}))
            total += len(bars)
            start = int(rows[-1][0]) + step
        return total

    async def native_history(self, ws, symbol):
        await self.history(ws, symbol, 0, count=1500)
        await self.history(ws, symbol, 0, interval='1d', count=300)

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
        # History/commands share a short send lock with the independent live pump.
        # Preload even if AmiBroker already consumed its one-time backfill flag
        # while the sender was offline. The receiver must be connected first.
        preload = list(self.symbols) if getattr(self.args, 'native_history', False) else []
        preload_retry = {}
        while True:
            self.schedule_rollover()
            self.schedule_stale_repairs()
            await self.repair_one(ws)
            try:
                cmd = self.commands.get_nowait()
            except asyncio.QueueEmpty:
                cmd = None
            if cmd:
                name = cmd['cmd']
                try:
                    arg = str(cmd.get('arg', '')).split()
                    if name in ('bfauto', 'bffull', 'bfsym'):
                        symbol = (arg[1] if name == 'bfsym' else arg[0]).upper()
                        days = int(arg[2]) if name == 'bfsym' else self.args.history_days
                        if not 1 <= days <= 7:
                            raise ValueError('Backfill days must be 1..7')
                        if name != 'bfsym' and getattr(self.args, 'native_history', False):
                            await self.native_history(ws, symbol)
                            if symbol in preload:
                                preload.remove(symbol)
                        else:
                            await self.history(ws, symbol, days)
                    elif name == 'bfsymeod':
                        symbol = arg[1].upper()
                        preset = int(arg[2]) if len(arg) > 2 else 1
                        await self.history(ws, symbol, 0, interval='1d',
                                           count=30 if preset <= 1 else 300)
                    elif name in ('bfall', 'bfeodall'):
                        for symbol in self.symbols:
                            if name == 'bfeodall':
                                await self.history(ws, symbol, 0, interval='1d', count=300)
                            elif getattr(self.args, 'native_history', False):
                                await self.native_history(ws, symbol)
                            else:
                                await self.history(ws, symbol, self.args.history_days)
                    else:
                        raise ValueError('Fixed universe: edit symbols file and restart; unsupported command')
                    await self.send(ws, compact(dict(cmd=name, code=200, arg='Backfill complete')))
                except (ValueError, IndexError, aiohttp.ClientError, RuntimeError) as exc:
                    await self.send(ws, compact(dict(cmd=name, code=400, arg=str(exc))))
            elif preload:
                symbol = preload.pop(0)
                if preload_retry.get(symbol, 0) > time.monotonic():
                    preload.append(symbol)
                else:
                    try:
                        await self.native_history(ws, symbol)
                    except (aiohttp.ClientError, TimeoutError, RuntimeError, ValueError) as exc:
                        LOG.error('Native preload deferred symbol=%s: %s', symbol, exc)
                        preload_retry[symbol] = time.monotonic() + 60
                        preload.append(symbol)
            await asyncio.sleep(self.args.flush_ms / 1000)

    async def flush(self, ws):
        async with self.flush_lock:
            await self._flush(ws)

    async def _flush(self, ws):
        items = sorted(self.buffer.pending.items(), key=lambda item: (item[0][1], item[0][0]))
        for pos in range(0, len(items), self.args.batch_size):
            chunk = items[pos:pos + self.args.batch_size]
            await self.send(ws, compact([rec for _, rec in chunk]))
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
                             asyncio.create_task(self.output(ws)),
                             asyncio.create_task(self.live_output(ws))]
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
            LOG.info('received=%s sent_records=%s pending_bars=%s repair_jobs=%s',
                     self.received, self.sent, len(self.buffer.pending), len(self.repairs))

    async def run(self):
        await self.discover()
        if getattr(self.args, 'discover_only', False):
            return
        tasks = [asyncio.create_task(self.relay()), asyncio.create_task(self.metrics())]
        tasks += [asyncio.create_task(self.shard(set(self.symbols[i:i+self.args.shard_size])))
                  for i in range(0, len(self.symbols), self.args.shard_size)]
        if getattr(self.args, 'quotes', False):
            tasks += [asyncio.create_task(self.shard(set(self.symbols[i:i+self.args.shard_size]), public=True))
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
    p.add_argument('--universe-dir', help='Fresh directory for exchangeInfo, selection and watchlists')
    p.add_argument('--discover-only', action='store_true', help='Save discovery without connecting the relay')
    p.add_argument('--shard-size', type=int, default=100)
    p.add_argument('--batch-size', type=int, default=100)
    p.add_argument('--flush-ms', type=int, default=250)
    p.add_argument('--history-days', type=int, default=1)
    p.add_argument('--native-history', action='store_true',
                   help='Preload 1500 closed minute and 300 daily bars per symbol on relay connect')
    p.add_argument('--quotes', action='store_true', help='Include live ticker and bid/ask fields')
    p.add_argument('--public-ws', default='wss://fstream.binance.com/public/stream')
    p.add_argument('--relay', default='ws://127.0.0.1:10101')
    p.add_argument('--ws', default='wss://fstream.binance.com/market/stream')
    p.add_argument('--rest', default='https://fapi.binance.com')
    a = p.parse_args()
    if a.discover_only and not a.universe_dir:
        p.error('--discover-only requires --universe-dir')
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
