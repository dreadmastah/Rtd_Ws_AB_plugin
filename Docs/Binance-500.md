# Binance 500-symbol extension

This implementation preserves the repository's existing route:
Binance → Python sender → rolesend relay → rolerecv WSRTD DLL → AmiBroker → RADAR.
No DLL, JSON protocol, or database format changes are required by the Python code.
The checkout contains no DLL implementation and no previous Binance sender or
13-symbol configuration. Native symbol limits and actual ingestion behavior
cannot be confirmed from this repository.

## Run on Windows (Python 3.12+)

From the repository root, in separate terminals:

```powershell
py -m pip install -r Binance/requirements.txt
py Relay/Server/Python/relay.py 10101 startserver
py Binance/sender.py --limit 500
```

Connect WSRTD to 127.0.0.1:10101 with its existing receiver role.
Enable local database storage, use a 1-minute base interval, and add the selected
symbols to an AmiBroker watchlist. Initially test BTCUSDT and ETHUSDT; compare
open/high/low/close and final base volume with Binance before expanding.
A whitespace-separated priority list supports incremental rollout:

```powershell
py Binance/sender.py --symbols my-symbols.txt --limit 13
```

Discovery uses exchangeInfo and selects TRADING, PERPETUAL, quoteAsset USDT only.
Without a file, selection is alphabetical. Up to 500 are selected; the available
universe may be smaller. The universe is fixed until restart. Existing plugin
addsym/remsym requests receive a clear unsupported response rather than a false
success. Refresh the universe by restarting after editing the priority file.

## Implementation and tuning

- Five shards of at most 100 subscriptions by default, using SUBSCRIBE messages
  for lowercase `<symbol>@kline_1m`, avoiding giant combined-stream URLs.
- Current official market endpoint defaults to
  `wss://fstream.binance.com/market/stream`; `--ws` overrides it for migration
  or environments that still require `wss://fstream.binance.com/stream`.
- Binance kline updates can arrive every 250 ms when available. A planning load
  of 500 × 4 = 2,000 updates/sec is a synthetic upper-cadence scenario, not a
  measured guarantee. Worst-case output is 20 batches/sec at 100 records/batch.
- `--flush-ms 250` coalesces successive updates for the same symbol and minute.
  Distinct minutes remain ordered. Kline open time determines UTC d/t, preventing
  local-time/DST shifts. Do not reinterpret these UTC dates as Manila dates.
- Cumulative kline v replaces previous volume; it is never added repeatedly.
  Unavailable bid/ask, daily totals and open interest are omitted rather than
  manufactured. Realtime Quote window fields beyond candle price may be absent.
- Final versions reject later unfinished versions of the same candle. Old
  event times are rejected. Pending capacity is 5,000 symbol-minute entries;
  exceeding it stops the sender explicitly rather than silently losing bars.
- Each relay peer gets a bounded FIFO and one writer. Overflow disconnects the
  slow peer with 1013. History and commands retain the same opaque wire format.
  Binding remains local. Legacy `zzz` remote shutdown is deliberately disabled.
- Compression is disabled locally to avoid unnecessary CPU work; upstream
  compression is also disabled. Reconnect uses exponential backoff and jitter.
  Shards rotate after 23 hours; this is reconnect rotation, not overlap handover.
- REST history uses aiohttp (no pandas or blocking queue polling), one global
  request gate, 499-bar pages, 429/418 cooldown and bounded server-error retries.
  No API key is needed for these public market endpoints.

## History and recovery limits

The sender answers bfsym (`y SYMBOL DAYS`), bffull and bfauto using the existing
hist + format + bars schema. History is ascending, closed bars only, UTC, and
limited to 1..7 days. bfauto currently reloads `--history-days` (default one day),
not the supplied exact last-bar timestamp. History pages interleave RTD flushes.
Check DLL history merge behavior while a live bar is present: native behavior
cannot be audited here. A one-day preload across 500 symbols needs about 1,500
REST calls and takes minutes at the deliberately conservative request pace.

There is no automatic gap-repair scheduler or durable outage spool in this
version. After upstream, relay or DLL outages, explicitly request backfill for
affected symbols. Reconnect resumes live updates but does not prove continuity.
The sender removes a batch after relay socket send completes; this is not an
AmiBroker ingestion acknowledgement. If no receiver is connected the relay does
not retain data. After DLL reconnect, ensure backfill requests run (reset the
plugin's one-time backfill flags if needed). Do not use a 10-bar ring buffer
until you have measured the longest interval each symbol goes unaccessed.

## RADAR benchmark

Use a separate database for synthetic TEST0000..TEST0499 symbols. Start the relay,
connect the plugin, then run:

```powershell
py Benchmarks/load_sender.py --symbols 500 --seconds 600
```

Use Benchmarks/radar.afl in Analysis at 1-minute periodicity, last-bar range, and
start RADAR. Test 13, 100, 250, then 500 symbols for ten minutes each. Repeat with
your production AFL, 500 / 2,000 / 10,000 stored bars, and one versus multiple
receivers. Keep the watchlist identical to the active feed universe.

Record complete RADAR sweep duration (median/p95/max using Analysis timing or
screen capture), CPU, memory, sender pending_bars, relay overflow count, and
whether every symbol is present and changes. Suggested initial acceptance goals:
p95 complete sweep <=1 second, no relay overflow, bounded memory, no missing
minute boundaries, and exact final OHLCV/volume agreement. These are targets,
not claimed results.

Now(4) measures evaluation time only, at second resolution. The displayed bar
time is minute-open time, not freshness or receive latency. To measure transport
latency, timestamp event receipt, relay send, and DLL receive/commit with a common
clock; the DLL instrumentation requires its unavailable C++ source. Hardware,
AFL lookback and DLL locking may dominate at 500 symbols. RADAR double buffering
preserves display continuity; it does not establish changed-symbol-only execution.

Failure tests: restart sender, restart relay, disconnect DLL, simulate a slow
receiver, and check a UTC date rollover. Backfill after each disruption and
compare closed bars against REST. Confirm whether the installed DLL replaces
same-minute records rather than accumulating volume or appending duplicates.

## Validation and sources

Run `py -m unittest discover -s Tests -v`.
Tests cover 500-symbol coalescing, chronological minute preservation, finalized
candle protection, invalid OHLCV, explicit backlog failure, slow-peer isolation,
and the bidirectional legacy protocol through real local WebSockets.
A five-second local 500-symbol load delivered all 10,500 records in 105 frames
with zero relay overflows. This is a short Python loopback smoke benchmark, not
a sustained or native-plugin throughput result. Live Binance and Windows/AmiBroker
RADAR throughput were not measured here.

Official sources checked during implementation:
- https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/market
- https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info
- https://forum.amibroker.com/t/amibroker-7-20-0-beta-released/40853
