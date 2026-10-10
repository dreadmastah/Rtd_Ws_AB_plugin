"""Passive, bounded UTC rollover observer for the isolated 18101 test relay."""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import time

import aiohttp
from websockets.asyncio.client import connect


def assess(expected, pre, post, daily, samples, connected, stable, fresh):
    checks = dict(before_500=pre == expected, after_500=post == expected,
                  daily_500=set(daily) == expected, sample_ohlcv=set(samples) == {'BTCUSDT', 'ETHUSDT', 'XRPUSDT'} and all(samples.values()),
                  uninterrupted_receiver=connected, stable_sender_and_native=stable,
                  fresh_500=fresh == expected)
    return dict(status='PASS' if all(checks.values()) else 'FAIL', checks=checks,
                missing_before=sorted(expected-pre), missing_after=sorted(expected-post),
                missing_daily=sorted(expected-set(daily)), stale_live=sorted(expected-fresh))


def read_state(runtime):
    state = json.loads((runtime / 'status.json').read_text())
    if time.time() - datetime.fromisoformat(state['utc']).timestamp() > 30:
        raise ValueError('Stale supervisor heartbeat')
    if state['port'] != 18101 or not state['sender_running'] or not state['native_receivers']:
        raise ValueError('Test feed is not ready')
    return state


async def observe(args, boundary):
    args.output.mkdir(parents=True, exist_ok=False)
    result = dict(status='INCOMPLETE', boundary_utc=boundary.isoformat(),
                  scope='passive Python relay observation; no native export')
    result_path = args.output / 'result.json'
    result_path.write_text(json.dumps(result, indent=2))
    expected = set(args.symbols.read_text().split())
    pre, post, daily, latest = set(), set(), {}, {}
    samples = {}
    states = []
    started = time.time()
    end = boundary.timestamp() + 15 * 60
    target_date = int((boundary - timedelta(days=1)).strftime('%Y%m%d'))
    new_date = int(boundary.strftime('%Y%m%d'))
    try:
        if len(expected) != 500:
            raise ValueError('Observer requires the verified 500-symbol list')
        if started < boundary.timestamp() - 180:
            raise ValueError('Observer started too early; maximum lead time is three minutes')
        if started >= boundary.timestamp():
            raise ValueError('Observer started after the UTC boundary; crossing not observed')
        states.append(read_state(args.runtime))
        last_status = 0
        async with connect('ws://127.0.0.1:18101/receiver',
                           compression=None, max_size=4*1024*1024) as ws:
            with (args.output / 'daily-frames.jsonl').open('x', encoding='utf-8') as frames:
                while time.time() < end:
                    now = time.time()
                    if now - last_status >= 10:
                        states.append(read_state(args.runtime))
                        (args.output / 'progress.json').write_text(json.dumps(dict(
                            utc=datetime.now(timezone.utc).isoformat(), before=len(pre),
                            after=len(post), daily=len(daily)), indent=2))
                        last_status = now
                    try:
                        data = json.loads(await asyncio.wait_for(ws.recv(), 3))
                    except TimeoutError:
                        continue
                    now = time.time()
                    if isinstance(data, list):
                        for row in data:
                            symbol = row['n']
                            if symbol not in expected:
                                continue
                            if now < boundary.timestamp():
                                pre.add(symbol)
                            elif int(row['d']) >= new_date:
                                post.add(symbol)
                                latest[symbol] = now
                    elif data.get('format') == 'dohlcv' and data.get('hist') in expected:
                        if now >= boundary.timestamp():
                            bars = [bar for bar in data['bars'] if bar[0] == target_date]
                            if bars:
                                daily[data['hist']] = bars[-1]
                                frames.write(json.dumps(dict(received_utc=now, frame=data)) + '\n')
                                frames.flush()
                    # Observe at least five real minutes after midnight, even if all jobs finish early.
                    if now >= boundary.timestamp() + 300 and set(daily) == expected and post == expected:
                        break
        observed_end = time.time()
        states.append(read_state(args.runtime))
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            for symbol in ('BTCUSDT', 'ETHUSDT', 'XRPUSDT'):
                params = dict(symbol=symbol, interval='1d', limit=1,
                              startTime=int(boundary.timestamp()*1000)-86400000,
                              endTime=int(boundary.timestamp()*1000)-1)
                async with session.get('https://fapi.binance.com/fapi/v1/klines', params=params) as response:
                    response.raise_for_status()
                    rows = await response.json()
                (args.output / f'{symbol}-daily-rest.json').write_text(json.dumps(rows, indent=2))
                samples[symbol] = (len(rows) == 1 and int(rows[0][0]) == params['startTime'] and
                                   daily.get(symbol) == [target_date, *[float(v) for v in rows[0][1:6]]])
        identity = lambda s: (s['supervisor_pid'], s['sender_pid'], s['native_receivers'])
        stable = all(identity(s) == identity(states[0]) for s in states)
        fresh = {s for s, t in latest.items() if observed_end-t <= 90}
        result.update(assess(expected, pre, post, daily, samples, True, stable, fresh))
    except Exception as exc:
        result.update(status='FAIL', error=f'{type(exc).__name__}: {exc}')
    finally:
        result.update(started_utc=datetime.fromtimestamp(started, timezone.utc).isoformat(),
                      finished_utc=datetime.now(timezone.utc).isoformat(),
                      before_count=len(pre), after_count=len(post), daily_count=len(daily),
                      sample_matches=samples, states=states,
                      actual_boundary_observed=started < boundary.timestamp() <= time.time())
        result_path.write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--symbols', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--boundary', required=True, help='UTC midnight, ISO 8601 with offset')
    args = parser.parse_args()
    boundary = datetime.fromisoformat(args.boundary.replace('Z', '+00:00'))
    if boundary.tzinfo is None or boundary.utcoffset() != timedelta(0) or any(
            (boundary.hour, boundary.minute, boundary.second, boundary.microsecond)):
        parser.error('Boundary must be exactly midnight UTC')
    result = asyncio.run(observe(args, boundary))
    raise SystemExit(0 if result['status'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
