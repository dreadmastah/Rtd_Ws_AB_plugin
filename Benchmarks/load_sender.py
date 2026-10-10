"""Synthetic 500-symbol sender. Use a separate AmiBroker test database."""
import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from websockets.asyncio.client import connect

async def run(args):
    async with connect(args.relay, compression=None) as ws:
        await ws.send('rolesend')
        async def receive():
            async for _ in ws:
                pass
        reader = asyncio.create_task(receive())
        started = time.perf_counter()
        cycle = 0
        try:
            while time.perf_counter() - started < args.seconds:
                target = started + cycle * args.interval
                await asyncio.sleep(max(0, target-time.perf_counter()))
                now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
                data = [dict(n=f'TEST{i:04d}', d=int(now.strftime('%Y%m%d')),
                             t=int(now.strftime('%H%M%S')), o=100, h=101, l=99,
                             c=100 + (cycle % 100)/1000, v=(cycle % int(60/args.interval))+1)
                        for i in range(args.symbols)]
                for pos in range(0, len(data), 100):
                    await ws.send(json.dumps(data[pos:pos+100], separators=(',', ':')))
                cycle += 1
            print(json.dumps(dict(cycles=cycle, records=cycle*args.symbols,
                                  elapsed_s=time.perf_counter()-started)))
        finally:
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--symbols', type=int, default=500)
    p.add_argument('--seconds', type=float, default=60)
    p.add_argument('--interval', type=float, default=.25)
    p.add_argument('--relay', default='ws://127.0.0.1:10101')
    args=p.parse_args()
    if not 1 <= args.symbols <= 500 or args.interval <= 0 or args.seconds <= 0:
        p.error('Invalid load parameters')
    asyncio.run(run(args))
