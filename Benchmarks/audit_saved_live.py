"""Read saved transport evidence; preserve fresh REST comparisons separately."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import aiohttp
from Benchmarks.validate_transport import stamp
from Binance.sender import record


async def main(args):
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    results = []
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        for count in (13,100,250,500):
            root = Path(args.input)/f'live-{count}'
            bars = json.loads((root/'received-bars.json').read_text())
            by_symbol = {}
            for rec in bars:
                by_symbol.setdefault(rec['n'], {})[stamp(rec)] = rec
            stage = dict(count=count, matched=0, mismatches=[], missing_interior=[],
                         missing_symbols=[], rest_errors=[], raw_rest={})
            # Exclude each symbol's last minute conservatively: the collector
            # may have stopped mid-candle. Compare every interior minute too.
            for symbol in Path(args.symbols).read_text().split()[:count]:
                observed = by_symbol.get(symbol,{})
                if len(observed)<2:
                    stage['missing_symbols'].append(symbol)
                    continue
                first, last = min(observed), max(observed)
                try:
                    async with session.get('https://fapi.binance.com/fapi/v1/klines',
                        params=dict(symbol=symbol, interval='1m',startTime=first,
                                    endTime=last-1,limit=499)) as response:
                        response.raise_for_status()
                        rows = await response.json()
                    stage['raw_rest'][symbol] = rows
                    expected = {int(r[0]):record(symbol,r[0],r[1:6]) for r in rows}
                    for ts in range(first,last,60000):
                        if ts not in observed:
                            stage['missing_interior'].append(dict(symbol=symbol,stamp=ts))
                        elif expected.get(ts) != observed[ts]:
                            stage['mismatches'].append(dict(symbol=symbol,stamp=ts,
                                                           actual=observed[ts],
                                                           expected=expected.get(ts)))
                        else:
                            stage['matched'] += 1
                except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
                    stage['rest_errors'].append(dict(symbol=symbol,error=str(exc)))
                await asyncio.sleep(.25)
            history = json.loads((root/'backfill.json').read_text())
            times = [stamp(dict(d=r[0],t=r[1])) for r in history['bars']]
            stage['backfill_strict_1m_ascending'] = (
                len(times)>1 and all(b-a==60000 for a,b in zip(times,times[1:])))
            stage['backfill_unique_count'] = len(set(times))
            stage['backfill_success_response'] = any(r.get('code')==200 for r in history['responses'])
            stage['audit_utc'] = datetime.now(timezone.utc).isoformat()
            (output/f'live-{count}.json').write_text(json.dumps(stage,indent=2)+'\n')
            brief = {k:v for k,v in stage.items() if k!='raw_rest'}
            results.append(brief)
            print(json.dumps(brief),flush=True)
    (output/'summary.json').write_text(json.dumps(results,indent=2)+'\n')
    if any(r['mismatches'] or r['missing_interior'] or r['missing_symbols']
           or r['rest_errors'] or not r['backfill_strict_1m_ascending']
           or not r['backfill_success_response'] for r in results):
        raise SystemExit(1)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--symbols',required=True)
    asyncio.run(main(p.parse_args()))
