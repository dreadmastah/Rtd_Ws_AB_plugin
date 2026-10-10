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
  By default bid/ask, daily totals and open interest are omitted. With `--quotes`,
  ticker and bookTicker supply the native quote fields without changing candle
  OHLCV or adding daily totals to minute volume. Open interest is still omitted.
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
not the supplied exact last-bar timestamp. An independent live pump continues
during history downloads and REST retries; socket writes are serialized.
Check DLL history merge behavior while a live bar is present: native behavior
cannot be audited here. A one-day preload across 500 symbols needs about 1,500
REST calls and takes minutes at the deliberately conservative request pace.

Upstream reconnects automatically queue closed-minute recovery from each
symbol's last observation, including that minute when its final update was
missed. A jump in candle timestamps also queues recovery even without a socket
disconnect. Jobs coalesce per symbol, use ascending REST pages, and retry after
60 seconds if REST fails or returns an incomplete range. Live data continues
while recovery is pending. Recovery is capped at the latest 1,500 minutes in
native-history mode, or `--history-days` otherwise; truncation is logged.
There is no durable outage spool or ingestion acknowledgement.
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

## Isolated validation and saved universe

Use a virtual environment in a separate checkout. Do not use the production
relay or database. From the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r Benchmarks/requirements.txt
.\.venv\Scripts\python.exe Binance/sender.py --discover-only --limit 500 --universe-dir validation/universe
```

Discovery logs the eligible count and creates a fresh directory containing raw
exchangeInfo, timestamped universe metadata, selected-symbols.txt, and nested
watchlist-13/100/250/500.tls files. Existing output directories are refused.
TRADING + USDT quote + PERPETUAL are all required; no spot, USDC, or delivery
contracts are substituted. If fewer than 500 exist, metadata records actual
stage sizes. Reuse this selection for all stages. The sender revalidates
eligibility on startup and rejects an ineligible symbol rather than replacing it.

In separate terminals, for each desired count:

```powershell
.\.venv\Scripts\python.exe Relay/Server/Python/relay.py 18101 startserver
.\.venv\Scripts\python.exe Binance/sender.py --symbols validation/universe/selected-symbols.txt --limit 13 --relay ws://127.0.0.1:18101
```

Connect only the separate live-test database to port 18101. Use a unique
database basename, not just a different folder named Data: WSRTD shares registry
settings between databases having the same basename. Enable local storage and
a 1-minute base interval. Import the corresponding saved .tls watchlist.

### CleanRoomR2 native receiver compatibility

The installed WSRTD Compatible 3.06.26 R2 receiver was observed connecting to
`/` without sending a role message. The default relay intentionally requires a
role message and therefore cannot register that receiver. For this DLL only,
explicitly select path mode on the isolated test relay:

```powershell
.\.venv\Scripts\python.exe Relay/Server/Python/relay.py 18101 --protocol path
.\.venv\Scripts\python.exe Binance/sender.py --symbols validation/universe/selected-symbols.txt --limit 13 --relay ws://127.0.0.1:18101/sender
```

Path mode assigns `/` and `/receiver` to receivers and `/sender` to senders.
Unknown paths and conflicting role messages are rejected. This remains a
loopback-only unauthenticated relay; it does not replicate production relay
authentication or status messages. Default `--protocol role` is unchanged.
For synthetic tests with this DLL, use the same explicit mode on 18102 and
append `/sender` to the load generator's relay URL.

### Restore daily/hourly history and live quotes with CleanRoomR2

After the test database receiver is connected to the path-mode relay, run:

```powershell
.\.venv\Scripts\python.exe Binance/sender.py --symbols validation/universe/selected-symbols.txt --limit 13 --relay ws://127.0.0.1:18101/sender --native-history --quotes
```

`--native-history` preloads the latest 1,500 completed one-minute bars and 300
completed daily bars for each selected symbol on every sender-to-relay connection.
Daily records use `dohlcv` (native EOD markers), while minute records use `dtohlcv`.
AmiBroker derives hourly candles from the retained minute bars. Newly listed
contracts may have fewer available daily bars. Live delivery continues
independently of history downloads. Preload does not depend on the plugin
repeating its first-access request, and failed attempts retry after 60 seconds.
`bfauto` and `bffull` also restore both histories in this mode; `bfsymeod`,
`bfeodall`, and `bfall` are supported. The default minute-only mode is unchanged.

`--quotes` subscribes to `ticker` on the market endpoint and `bookTicker` on
`wss://fstream.binance.com/public/stream` (override with `--public-ws`). It fills
the existing WSRTD daily-volume, previous-close, daily-range and bid/ask fields.
Quote changes re-emit the latest real minute candle; no candles are synthesized
from quotes, and OHLCV remains from `kline_1m`. This provides live quote updates,
not a historical tick-by-tick trade database. Binance ticker daily fields are
rolling 24-hour statistics, matching the previous sender's mapping.

The Realtime Quote list is separate from the chart selection. Right-click its
empty area and use **Add selected symbol**, or **Add symbol**, to populate it.
The sender runs until stopped; a bounded benchmark feed exits at its deadline.
Receiver-only reconnects still require explicit backfill or a supervisor that
restarts the sender when the native receiver reconnects: this relay mode has no
receiver-presence notifications. Upstream minute recovery is automatic.
With `--native-history`, the history worker detects a new UTC day and fetches
the newly closed daily bar for each symbol whose daily preload completed. It
catches up multiple missed days, capped at 300 days, retries incomplete results,
and never sends the current unfinished daily candle as EOD history. Failed
repairs remain queued and `repair_jobs` in the log indicates outstanding work.
Start the native receiver
before this sender, because a relay with no receivers does not retain preload.

The 13-symbol native check on 2026-10-10 loaded 1,500 minute and 300 daily bars
per selected symbol, and the operator confirmed both 1H/1D views and live quotes.
The operator subsequently confirmed smooth 500-symbol RADAR operation and
loaded history with advancing prices for BTCUSDT, ETHUSDT and XRPUSDT on 1m,
1H and 1D charts (2026-10-11). This is operator acceptance, not a native export
comparison of every stored bar or a measured RADAR latency percentile.

Sources: [Binance market streams](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/market),
[Binance public streams](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/public),
[AmiBroker Realtime Quote window](https://www.amibroker.com/guide/w_rtquote.html).

Generated `.tls` files use CRLF explicitly on every platform. Preserve their
bytes when copying: an LF-only copy imported incompletely in the native test.
Verify all imported counts and symbols against the saved selection; a file's
name does not prove its imported size. Do not count connection or Python relay
delivery as native OHLCV/RADAR acceptance; export and compare AmiBroker data.

For synthetic RADAR load, use another uniquely named, synthetic-only database,
connected to a separate relay on port 18102. Never mix fabricated prices with
the live-validation or production databases. Import the same saved watchlist,
then use Benchmarks/radar.afl at 1-minute periodicity and last-bar range:

```powershell
.\.venv\Scripts\python.exe Benchmarks/load_sender.py --symbols-file validation/universe/selected-symbols.txt --symbols 500 --seconds 600 --relay ws://127.0.0.1:18102
```

Synthetic volume increases within the actual UTC candle minute and resets at
its boundary. Intervals of 60 seconds or longer no longer divide by zero, and
no extra cycle is emitted after the requested duration.

### Repeatable Python-only checks

The following owns and stops its sender/relay processes, refuses the production
default port 10101 and any occupied port, and creates fresh per-stage directories.
It does not run AmiBroker, ingest through the DLL, or measure RADAR.
Do not attach native clients to these collector runs.

```powershell
.\.venv\Scripts\python.exe Benchmarks/validate_transport.py --mode live --symbols validation/universe/selected-symbols.txt --output validation/live --seconds 150 --port 18101
.\.venv\Scripts\python.exe Benchmarks/validate_transport.py --mode synthetic --symbols validation/universe/selected-symbols.txt --output validation/synthetic --seconds 150 --port 18102
.\.venv\Scripts\python.exe -m Benchmarks.audit_saved_live --input validation/live --symbols validation/universe/selected-symbols.txt --output validation/rest-audit
```

The live run compares captured closed OHLCV with REST and requests one day's
backfill for the first selected symbol at each size. The audit conservatively
excludes each symbol's last captured minute, preserves raw REST responses, checks
every interior minute, and verifies contiguous backfill timestamps. It is not
a 500-symbol full-history/backfill capacity test. CPU is process-tree CPU time
delta, with one logical core equal to 100%; RSS includes the Windows venv wrapper.
These exclude collector and AmiBroker CPU. A zero CPU delta is not proof of
zero work. Short runs do not establish long-duration memory stability.

### Windows ownership and supervisor recovery (test feed only)

`Benchmarks/supervise_test_feed.py` owns the isolated port-18101 relay and
sender in a Windows Job Object. If the supervisor exits unexpectedly, Windows
terminates its child processes too, avoiding an orphan relay that blocks restart.
A named mutex refuses duplicate supervisors; an occupied port is never taken over.
The existing test runtime STOP file prevents startup and causes an orderly stop.
The supervisor never starts or stops AmiBroker.

`Benchmarks/install_test_watchdog.ps1` registers **WSRTD PR3 Test Supervisor
Watchdog** for the current user's interactive logon, with a one-minute repeating
trigger, restart-on-failure, and no execution time limit. It runs independently
of the Codex terminal. It is user-logon recovery, not pre-logon boot service
coverage. It does not recover a still-running but hung supervisor. Keep the
configured Python environment and source checkout available.

Example installation, after connecting the test database to port 18101:

```powershell
.\Benchmarks\install_test_watchdog.ps1 -Root C:\path\to\WSRTD -Runtime D:\WSRTD_TEST\runtime -Python C:\path\to\WSRTD\.venv\Scripts\pythonw.exe
```

The runtime must already contain `selected-symbols.txt`. The installer refuses
an existing task or supervisor installation file rather than overwriting it.
Read the task and source bindings before intentionally replacing an installation.
To stop recovery, create the runtime STOP file before stopping the task.
To uninstall after stopping, remove only the named test task; production's
WSRTD R2.1 Recovery Watchdog is a separate task.

The 2026-10-11 forced-supervisor-exit check recovered automatically in 15.125
seconds with no orphan children and the same AmiBroker receiver. All 500 candle
symbols were observed in the first 90 seconds; complete quote fields appeared
for 471 during that initial window. Treat warm-up coverage separately from
process-recovery success. A later 83.609-second passive capture observed all 500
live symbols and complete quote sets in the same sender generation.

### Passive actual UTC-rollover acceptance

`Benchmarks/observe_rollover.py` reads the test relay without sending commands.
Run it within three minutes before an explicit UTC midnight. It records all
500 symbols before and after the boundary, collects the newly closed daily
history, checks both candle timestamps and receive times (each no more than 90 seconds
old, rejecting future timestamps) and stable sender/native identity,
and compares BTCUSDT, ETHUSDT and XRPUSDT daily OHLCV with public REST responses.
It observes at least five minutes after midnight and stops by fifteen minutes
afterward plus bounded REST requests. Missing coverage, disconnects, changed
process identity, late startup or incomplete REST comparisons cannot pass.

Use a fresh output directory. The artifacts are relay evidence; they do not
prove native storage of every daily bar or replace a native export comparison.
An actual scheduled boundary crossing remains pending until its result exists.

Sources: [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
and [Task Scheduler settings](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtasksettingsset).
