"""Bounded isolated Python transport benchmark; NEVER certifies DLL/RADAR."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

import aiohttp
import psutil
from websockets.asyncio.client import connect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from Binance.sender import record


def stamp(rec):
    return int(datetime.strptime(f"{rec['d']:08d}{rec['t']:06d}",
                                '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc).timestamp()*1000)


def process_sample(pid):
    try:
        processes = [psutil.Process(pid)]
        processes += processes[0].children(recursive=True)
        return dict(cpu_s=sum(p.cpu_times().user + p.cpu_times().system for p in processes),
                    rss_bytes=sum(p.memory_info().rss for p in processes))
    except psutil.Error:
        return None


async def launch(script, args, log):
    return await asyncio.create_subprocess_exec(
        sys.executable, '-u', str(ROOT/script), *map(str, args), cwd=ROOT,
        stdout=log, stderr=log,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)


async def stop(proc):
    if proc and proc.returncode is None:
        # Only owned benchmark process and its venv interpreter child.
        try:
            children = psutil.Process(proc.pid).children(recursive=True)
        except psutil.Error:
            children = []
        for child in children:
            try:
                child.terminate()
            except psutil.Error:
                pass
        try:
            proc.terminate()
        except ProcessLookupError:
            pass
        await asyncio.wait_for(proc.wait(), 10)


async def stage(args, requested):
    symbols = Path(args.symbols).read_text().split()[:requested]
    if not symbols:
        raise ValueError('Empty universe')
    if len(symbols) != len(set(symbols)):
        raise ValueError('Duplicate symbols in saved universe')
    out = Path(args.output)/f'{args.mode}-{requested}'
    out.mkdir(parents=True, exist_ok=False)
    url = f'ws://127.0.0.1:{args.port}'
    # Refuse an already occupied port, especially an existing production relay.
    import socket
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', args.port))
    relay = sender = None
    bars, seen, errors, samples = {}, set(), [], []
    frames = records = replacements = volume_regressions = 0
    histories, responses = [], []
    started_utc = datetime.now(timezone.utc).isoformat()
    with (out/'relay.log').open('x') as relaylog, (out/'sender.log').open('x') as senderlog:
        try:
            relay = await launch(Path('Relay/Server/Python/relay.py'), [args.port], relaylog)
            for _ in range(100):
                try:
                    receiver = await connect(url, compression=None, max_size=4*1024*1024)
                    break
                except OSError:
                    if relay.returncode is not None:
                        raise RuntimeError('Relay exited during startup')
                    await asyncio.sleep(.1)
            else:
                raise TimeoutError('Relay startup')
            async with receiver:
                await receiver.send('rolerecv')
                await asyncio.sleep(.1)
                if args.mode == 'live':
                    sender = await launch(Path('Binance/sender.py'), [
                        '--symbols', args.symbols, '--limit', requested, '--relay', url], senderlog)
                else:
                    sender = await launch(Path('Benchmarks/load_sender.py'), [
                        '--symbols-file', args.symbols, '--symbols', requested,
                        '--seconds', args.seconds, '--relay', url], senderlog)
                start = time.monotonic()
                async def receive():
                    nonlocal frames, records, replacements, volume_regressions
                    async for message in receiver:
                        data = json.loads(message)
                        if isinstance(data, dict):
                            if 'hist' in data:
                                histories.extend(data['bars'])
                            elif 'cmd' in data:
                                responses.append(data)
                            continue
                        frames += 1
                        for rec in data:
                            records += 1
                            if rec['n'] not in symbols:
                                errors.append('Unexpected symbol')
                            ts = stamp(rec)
                            if ts % 60000:
                                errors.append('Non-minute timestamp')
                            record(rec['n'], ts, [rec[k] for k in ('o','h','l','c','v')])
                            key = (rec['n'], ts)
                            old = bars.get(key)
                            if old:
                                replacements += 1
                                if rec['v'] < old['v']:
                                    volume_regressions += 1
                            bars[key] = rec
                            seen.add(rec['n'])
                reader = asyncio.create_task(receive())
                try:
                    while time.monotonic()-start < args.seconds:
                        if reader.done():
                            reader.result()
                            raise RuntimeError('Receiver stopped unexpectedly')
                        if sender.returncode is not None and args.mode == 'live':
                            raise RuntimeError('Live sender exited')
                        samples.append(dict(elapsed=time.monotonic()-start,
                                            sender=process_sample(sender.pid),
                                            relay=process_sample(relay.pid)))
                        await asyncio.sleep(1)
                    if args.mode == 'live':
                        await receiver.send(json.dumps(dict(cmd='bffull', arg=symbols[0])))
                        deadline = time.monotonic()+45
                        while not responses and time.monotonic() < deadline:
                            if reader.done():
                                reader.result()
                                raise RuntimeError('Receiver stopped during backfill')
                            await asyncio.sleep(.2)
                    else:
                        await asyncio.wait_for(sender.wait(), 10)
                        await asyncio.sleep(.5)
                finally:
                    if reader.done() and not reader.cancelled():
                        reader.result()
                    reader.cancel()
                    await asyncio.gather(reader, return_exceptions=True)
        finally:
            await stop(sender)
            await stop(relay)
    ended = int(time.time()*1000)
    (out/'received-bars.json').write_text(json.dumps(list(bars.values()), indent=2)+'\n')
    (out/'resources.json').write_text(json.dumps(samples, indent=2)+'\n')
    (out/'backfill.json').write_text(json.dumps(dict(bars=histories,responses=responses))+'\n')
    comparisons, mismatches, rest_errors = [], [], []
    if args.mode == 'live':
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            for symbol in symbols:
                # Compare every captured fully elapsed minute, not the in-progress bar.
                closed = [(ts, rec) for (sym, ts), rec in bars.items()
                          if sym == symbol and ts+61000 <= ended]
                if not closed:
                    rest_errors.append(dict(symbol=symbol, error='No closed observed bar'))
                    continue
                low, high = min(t for t,_ in closed), max(t for t,_ in closed)
                try:
                    async with session.get('https://fapi.binance.com/fapi/v1/klines',
                        params=dict(symbol=symbol, interval='1m', startTime=low,
                                    endTime=high+59999, limit=499)) as response:
                        response.raise_for_status()
                        rows = await response.json()
                    expected = {int(row[0]): record(symbol,row[0],row[1:6]) for row in rows}
                    for ts, rec in closed:
                        match = expected.get(ts) == rec
                        comparisons.append(dict(symbol=symbol,stamp=ts,match=match))
                        if not match:
                            mismatches.append(dict(symbol=symbol,stamp=ts,
                                                   received=rec,rest=expected.get(ts)))
                    observed = {ts for ts, _ in closed}
                    for ts in expected.keys() - observed:
                        rest_errors.append(dict(symbol=symbol, stamp=ts,
                                                error='Missing interior closed minute'))
                except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
                    rest_errors.append(dict(symbol=symbol,error=str(exc)))
                await asyncio.sleep(.25)
    def usage(name):
        valid = [(s['elapsed'],s[name]) for s in samples if s[name]]
        cpu = [100*(b['cpu_s']-a['cpu_s'])/(tb-ta)
               for (ta,a),(tb,b) in zip(valid,valid[1:]) if tb>ta]
        rss = [s['rss_bytes']/1024**2 for _,s in valid]
        return dict(cpu_percent_one_core_mean=statistics.mean(cpu) if cpu else None,
                    cpu_percent_one_core_max=max(cpu,default=None),
                    rss_mib_min=min(rss,default=None),rss_mib_max=max(rss,default=None))
    synthetic_counts = None
    if args.mode == 'synthetic':
        lines = (out/'sender.log').read_text().splitlines()
        synthetic_counts = json.loads(lines[-1]) if lines else None
        if not synthetic_counts or synthetic_counts.get('records') != records:
            errors.append('Synthetic sent/received record count mismatch')
    summary = dict(scope='PYTHON_TRANSPORT_ONLY', mode=args.mode, requested=requested,
                   actual=len(symbols), observed_symbols=len(seen),
                   missing_symbols=sorted(set(symbols)-seen),
                   duration_s=args.seconds, started_utc=started_utc, frames=frames,
                   records=records, replacements=replacements,
                   cumulative_volume_regressions=volume_regressions,
                   minute_counts={s:sum(sym==s for sym,_ in bars) for s in symbols},
                   validation_errors=errors, rest_compared_bars=len(comparisons),
                   rest_mismatches=mismatches, rest_errors=rest_errors,
                   backfill_bars=len(histories),backfill_responses=responses,
                   sender=usage('sender'),relay=usage('relay'),
                   relay_overflow_logged='queue overflow' in (out/'relay.log').read_text(),
                   DLL_INGESTION='NOT_TESTED', RADAR='NOT_TESTED')
    summary['synthetic_sender_counts'] = synthetic_counts
    summary['cpu_scope'] = ('Owned sender/relay process trees only, one logical core = 100%; '
                            'excludes collector, AmiBroker and other processes. '
                            'Zero CPU delta may reflect counter resolution.')
    summary['transport_checks_passed'] = not (
        errors or mismatches or rest_errors or volume_regressions or
        set(symbols)-seen or summary['relay_overflow_logged'] or
        (args.mode == 'live' and (not comparisons or not histories or
          not any(r.get('code') == 200 for r in responses))))
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('minute_counts','rest_mismatches')}),
          flush=True)
    return summary['transport_checks_passed']


async def main(args):
    passed = []
    for count in args.counts:
        passed.append(await stage(args,count))
    if not all(passed):
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--symbols',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--mode',choices=['live','synthetic'],required=True)
    parser.add_argument('--seconds',type=float,default=150)
    parser.add_argument('--counts',type=int,nargs='+',default=[13,100,250,500])
    parser.add_argument('--port',type=int,default=18101)
    a=parser.parse_args()
    if (a.port == 10101 or not 1024 <= a.port <= 65535
            or not math.isfinite(a.seconds) or a.seconds <= 0):
        parser.error('Use an isolated non-production port and positive duration')
    if any(not 1 <= n <= 500 for n in a.counts):
        parser.error('Counts must be 1..500')
    asyncio.run(main(a))
