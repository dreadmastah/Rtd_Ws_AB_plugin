# WSRTD Clean-Room R2

This subtree contains the independent clean-room WSRTD-compatible R2 work developed for AmiBroker x64 and Binance USD-M USDT perpetual Futures.

It is intentionally isolated from the original upstream project files. It does not claim to be an official/private WSRTD build.

## Runtime model

Per active symbol:

- 300 completed native Futures EOD bars
- 1,500 retained Futures 1-minute bars
- 1,800 total bounded quote records
- latest 60 one-minute bars intended for direct use/display
- latest 24 hourly bars derived by AmiBroker from retained 1-minute data
- current 1-minute, hourly, and daily bars update from the live Futures feed

EOD and intraday retention are independently bounded so minute traffic cannot evict the 300 EOD records.

## Bootstrap universe

BTCUSDT, SOLUSDT, BNBUSDT, XRPUSDT, DOGEUSDT, ADAUSDT, TRXUSDT, AVAXUSDT, LINKUSDT, 1000SHIBUSDT, DOTUSDT, ETHUSDT.

TONUSDT is intentionally excluded.

## Data source

OHLCV uses Binance USD-M Futures contract klines, not Spot klines.

- 1-minute: Futures `kline_1m`
- EOD: Futures `1d` REST klines
- bid/ask: Futures `bookTicker`
- mark/index/funding: Futures mark-price stream
- open interest: Futures REST open-interest endpoint

## AmiBroker database settings

- Base time interval: 1 minute
- Local data storage: enabled
- Allow mixed EOD/Intraday: enabled
- 24-hour trading display
- Suggested number of bars to load: 2000

## R2 registry retention

- `EODRetention=300`
- `IntradayRetention=1500`
- `QuoteLimit=1800`

## Artifact identities

Prebuilt DLL SHA-256:
`19952cef822ba2a470e52caa4d4edfeb82933bc9886411d6e85126d95fcf0379`

Source package SHA-256:
`258707ee7bcc699d8a33315abda76d403ab8e3edb983a2b20646f621a1b0b589`

Runtime stack package SHA-256:
`f05a5357ace133bc0c915fb6e6e37c8386fe78c262352ed51473a5a84dd62697`

The repository stores the reviewable source/runtime files. Binary build artifacts are intentionally not committed here.

## Runtime status

The clean-room DLL has passed static PE/export/retention validation and has been exercised on AmiBroker with live Binance USD-M data, including 300-bar EOD delivery and 1-minute backfill/live updates.