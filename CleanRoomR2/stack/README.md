# WSRTD Binance USD-M Futures stack — R2 retention build

This bundle is the companion runtime stack for `WsRTD_Compat_3.06.26_R2_x64.dll`.
It uses **Binance USD-M USDT perpetual Futures data only** for OHLCV. Spot klines are not used.

## Bootstrap universe (12)

BTCUSDT, SOLUSDT, BNBUSDT, XRPUSDT, DOGEUSDT, ADAUSDT, TRXUSDT, AVAXUSDT, LINKUSDT, 1000SHIBUSDT, DOTUSDT, ETHUSDT.

`TONUSDT` is intentionally absent from this bootstrap file.

## R2 retention contract

Per symbol inside the DLL:

- Native completed EOD retention: **300 bars**
- Underlying 1-minute retention: **1,500 bars**
- Derived total cache ceiling: **1,800 records/symbol**
- User-visible 1-minute target: latest **60** bars
- Hourly target: latest **24** bars, derived by AmiBroker from the retained Futures 1-minute bars

The EOD and intraday quotas are independently evicted. Continuous 1-minute updates cannot push the 300 EOD bars out of the cache.

## Live data source

The server uses Binance USD-M Futures public data:

- `kline_1m` -> realtime Futures OHLCV
- `ticker` -> day/open/high/low/volume/previous-close fields
- `bookTicker` -> Futures bid/ask and sizes
- `markPrice` -> mark/index/funding metadata
- REST `openInterest` -> open-interest metadata

The current hourly bar and current daily bar are intended to be compressed by AmiBroker from the current Futures 1-minute stream. Historical completed daily bars come from Binance Futures `1d` klines.

## Backfill horizons

`config.json` separates intraday and EOD horizons:

- `full_backfill_days = 2`
- `max_backfill_days = 2`
- `eod_backfill_days = 301`

The EOD request uses 301 calendar days so the server can deliver **300 completed daily bars** while excluding today's unfinished UTC daily candle.

`bfauto` is clamped to the intraday maximum horizon to avoid downloading minute history that the bounded 1,500-record cache would discard.

## AmiBroker database settings

Use:

- Base time interval: **1-minute**
- Local data storage: enabled
- Allow mixed EOD/Intraday: enabled
- 24-hour trading display for crypto
- Suggested number of bars to load: **2000**

Do not change the database base interval to hourly. Higher intervals should be compressed from the retained 1-minute Futures data.

## Registry written by the launcher

For database `WSRTD`, the launcher writes under:

`HKCU\SOFTWARE\TJP\WsRtD\WSRTD`

Key retention settings:

- `EODRetention = 300`
- `IntradayRetention = 1500`
- `QuoteLimit = 1800`

## First-time install

From CMD in this folder:

```cmd
install_wsrtd_stack.cmd
```

Then launch for an AmiBroker database named `WSRTD`:

```cmd
launch_wsrtd_stack.cmd WSRTD
```

## Runtime status

The R2 DLL was cross-compiled as Windows x64 and statically validated for PE/exports/retention policy. Live AmiBroker testing has confirmed relay connectivity, realtime quote updates, 300-bar EOD delivery, and 1-minute backfill delivery on the user's test setup.
