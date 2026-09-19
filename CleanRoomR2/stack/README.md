# WSRTD Binance USD-M Futures stack — R2.1 Automatic Recovery

R2.1 keeps the R2 DLL retention contract and adds a hands-off runtime recovery layer for Windows/AmiBroker interruptions.

## Retention contract (unchanged from R2)

Per symbol:

- 300 completed native Binance USD-M Futures EOD bars
- 1,500 retained completed Binance USD-M Futures 1-minute bars
- 1,800 total bounded DLL records
- latest 60 one-minute bars intended for direct display/use
- latest 24 hourly bars derived by AmiBroker from the retained 1-minute series

The R2 DLL remains `WsRTD_Compat_3.06.26_R2_x64.dll`; R2.1 changes the runtime stack, not the DLL ABI.

## Automatic recovery behavior

1. **Temporary internet/Binance WebSocket outage**
   - market/public WebSockets reconnect automatically;
   - each symbol keeps a persistent `last_completed_1m_open_ms` watermark;
   - a completed live candle is not allowed to jump the watermark over a missing range;
   - Binance Futures REST repairs exactly the missing completed 1-minute range;
   - repair clamps to the newest 1,500 bars if the outage exceeds the bounded DLL retention horizon.

2. **AmiBroker/plugin receiver restart**
   - the relay reports receiver-count transitions to the sender;
   - when receiver count goes from 0 to 1, R2.1 automatically rehydrates the latest 1,500 completed 1-minute bars and latest 300 completed EOD bars for every active symbol;
   - history is not intentionally emitted while no AmiBroker receiver is attached.

3. **PC sleep/wake**
   - live sockets reconnect;
   - a 60-second recovery audit compares persisted watermarks with the current completed Futures minute;
   - any missing bounded range is repaired automatically.

4. **PC reboot/logon or launcher death**
   - `install_recovery_autostart.cmd WSRTD` installs an HKCU logon startup command plus a five-minute Task Scheduler watchdog;
   - the watchdog uses `stack_launcher.py --ensure-running` and is a no-op when the relay/server are already healthy;
   - stale PID state is discarded before replacement startup;
   - AmiBroker is automatically started by default and kept running while the stack is active.

5. **Daily rollover**
   - the recovery audit detects when the completed-EOD watermark is older than yesterday UTC;
   - the latest 300 completed Binance Futures daily bars are refreshed automatically;
   - today's developing daily candle continues to come from AmiBroker compression of live 1-minute data.

## Persistent recovery state

Default:

`runtime/recovery_state.json`

Per symbol it stores at least:

- `last_completed_1m_open_ms`
- `last_completed_eod_date`
- `updated_utc`

Writes are atomic using a temporary file followed by `os.replace`. A stale watermark causes overlapping REST recovery, which is safe because the R2 DLL merges/deduplicates by timestamp.

## Bootstrap universe

BTCUSDT, SOLUSDT, BNBUSDT, XRPUSDT, DOGEUSDT, ADAUSDT, TRXUSDT, AVAXUSDT, LINKUSDT, 1000SHIBUSDT, DOTUSDT, ETHUSDT.

All OHLCV is Binance USD-M **USDT perpetual Futures** data. Spot klines are not used.

## AmiBroker settings

- Data source: WSRTD Compatible 3.06.26 R2 (Clean-room)
- Local data storage: enabled
- Number of bars to load: 2000
- Base time interval: 1 minute
- Show 24 hours trading / no weekend filtering for crypto
- Allow mixed EOD/Intraday: enabled

Registry retention:

- `EODRetention=300`
- `IntradayRetention=1500`
- `QuoteLimit=1800`

## Install and run

First-time environment:

```cmd
install_wsrtd_stack.cmd
```

Manual launch:

```cmd
launch_wsrtd_stack.cmd WSRTD
```

Install automatic logon/watchdog recovery:

```cmd
install_recovery_autostart.cmd WSRTD
```

Verify:

```cmd
status_recovery_autostart.cmd
```

Remove:

```cmd
uninstall_recovery_autostart.cmd
```

## Recovery evidence

Look in `logs\server_supervisor.log` for:

- `automatic recovery start mode=FULL`
- `sent automatic full intraday recovery symbol=... bars=1500`
- `sent automatic EOD recovery symbol=... bars=300`
- `live 1m gap detected symbol=...`
- `sent automatic gap repair symbol=... bars=N`
- `automatic recovery complete ...`

## Bounded guarantee

R2.1 reconstructs the **current bounded cache target** automatically when Binance public REST is reachable and AmiBroker reconnects. If an outage exceeds 1,500 minutes, bars older than the 1,500-record DLL horizon are intentionally not restored to the DLL; the newest 1,500 minutes and newest 300 completed EOD bars are restored automatically.
