"""Synthetic 500-symbol sender. Use a separate AmiBroker test database."""
import argparse
import asyncio
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from websockets.asyncio.client import connect

def synthetic_records(symbols, now_ms, minute_cycle):
    now = datetime.fromtimestamp(now_ms / 1000, timezone.utc).replace(second=0, microsecond=0)
    return [dict(n=symbol, d=int(now.strftime('%Y%m%d')),
                 t=int(now.strftime('%H%M%S')), o=100, h=101, l=99,
                 c=100 + (minute_cycle % 100)/1000, v=minute_cycle + 1)
            for symbol in symbols]


async def run(args):
    symbols = (list(dict.fromkeys(Path(args.symbols_file).read_text().split()))[:args.symbols]
               if args.symbols_file else [f'TEST{i:04d}' for i in range(args.symbols)])
    if not symbols:
        raise ValueError('Empty symbol list')
    async with connect(args.relay, compression=None) as ws:
        await ws.send('rolesend')
        async def receive():
            async for _ in ws:
                pass
        reader = asyncio.create_task(receive())
        started = time.perf_counter()
        cycle = 0
        minute = None
        minute_cycle = 0
        try:
            while time.perf_counter() - started < args.seconds:
                target = started + cycle * args.interval
                await asyncio.sleep(max(0, min(target, started+args.seconds)-time.perf_counter()))
                if time.perf_counter() - started >= args.seconds:
                    break
                now_ms = time.time_ns() // 1000000
                current_minute = now_ms // 60000
                if current_minute != minute:
                    minute, minute_cycle = current_minute, 0
                data = synthetic_records(symbols, now_ms, minute_cycle)
                for pos in range(0, len(data), 100):
                    await ws.send(json.dumps(data[pos:pos+100], separators=(',', ':')))
                cycle += 1
                minute_cycle += 1
            print(json.dumps(dict(cycles=cycle, symbols=len(symbols), records=cycle*len(symbols),
                                  elapsed_s=time.perf_counter()-started)))
        finally:
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--symbols', type=int, default=500)
    p.add_argument('--symbols-file', help='Use saved discovery list in an ISOLATED synthetic test database only')
    p.add_argument('--seconds', type=float, default=60)
    p.add_argument('--interval', type=float, default=.25)
    p.add_argument('--relay', default='ws://127.0.0.1:10101')
    args=p.parse_args()
    if (not 1 <= args.symbols <= 500 or
            not math.isfinite(args.interval) or not math.isfinite(args.seconds) or
            args.interval <= 0 or args.seconds <= 0):
        p.error('Invalid load parameters')
    asyncio.run(run(args))
