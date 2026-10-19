# WSRTD Compatible 3.06.26 R2 — clean-room x64 candidate

This is an independent clean-room compatibility build, not the private/official WSRTD binary.

## R2 retention design

Per symbol, the DLL retains two independent classes inside one AmiBroker time-sorted quotation array:

- **300 native EOD records** — identified by AmiBroker's EOD timestamp marker.
- **1,500 intraday records** — intended for Binance USD-M Futures 1-minute OHLCV.
- **1,800 total maximum records per symbol**.

The eviction rule is partitioned. A new 1-minute record can evict only the oldest intraday record; it cannot evict one of the 300 native EOD records. A new EOD record can evict only the oldest EOD record.

This supports the requested usage model:

- 300 completed Binance USD-M Futures daily OHLCV bars retained natively.
- 1,500 underlying 1-minute Futures bars retained, enough to derive the latest 24 hourly bars with rollover margin.
- The chart/AFL may show only the latest 60 one-minute bars; this does not reduce the underlying 1,500-bar cache.
- Current 1-minute, hourly, and daily bars remain live: 1-minute is supplied by Futures `kline_1m`, while AmiBroker compresses the current 1-minute series into hourly/current-day views.

## Registry settings

R2 uses these keys under `HKCU\SOFTWARE\TJP\WsRtD\<DatabaseName>`:

- `EODRetention=300`
- `IntradayRetention=1500`
- `QuoteLimit=1800` (derived total, written for compatibility/status reporting)

If the two new retention keys are absent, R2 defaults to 300 and 1500. The legacy `QuoteLimit` value does not override the partition sizes.

## State persistence

R2 uses a separate state filename: `WsRTD_<DBNAME>_30626R2.cleanroom.bin`. This intentionally avoids loading the earlier single-cache state format.

## Acceptance helpers

`GetExtraData()` additionally exposes:

- `CacheEOD`
- `CacheIntraday`
- `CacheTotal`
- `EODRetention`
- `IntradayRetention`

These can be used in AFL/Exploration to verify the live cache counts.

## Build

Run `build_x64.cmd` from an x64 Visual Studio Developer Command Prompt. The prebuilt DLL is unsigned and still requires runtime validation inside AmiBroker x64.

## ABI compatibility

The original 13 observed export names/ordinals remain unchanged, with the same three optional exports at ordinals 14–16. The reported protocol/plugin compatibility version remains 30626; the plugin display name includes `R2`.
