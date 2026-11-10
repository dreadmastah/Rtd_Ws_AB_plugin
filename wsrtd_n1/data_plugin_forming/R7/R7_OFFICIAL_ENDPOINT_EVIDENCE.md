# Official endpoint evidence — reviewed 2026-11-10

Sources: [USD-M Connect](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Connect) and [routing migration](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Important-WebSocket-Change-Notice), both showing October 30, 2026 modification dates.

The Connect page identifies fstream.binance.com, routed /public, /market and /private URLs, lowercase stream names and raw /ws/<streamName> access. It documents 24-hour connections, server pings, 10 incoming messages/second and 1024 streams/connection. These are exchange limits, not permission to use them.

The migration page maps klines to /market and gives the <symbol>@kline_<interval> format. It states the April 23, 2026 migration deadline and warns that unrouted connections no longer deliver market/private streams. Therefore the exact proposed raw BTCUSDT minute endpoint is wss://fstream.binance.com/market/ws/btcusdt@kline_1m. It is USD-M, not dstream COIN-M or spot.

The R7 allowlist accepts only that exact URL; explicit alternate ports, queries, credentials, fragments, other symbols and routes are rejected. Its URL stream consumes one subscription before connect; no JSON SUBSCRIBE is allowed. All dispatch remains test-owned localhost TLS. External address routing and genuine authority remain BLOCKED. Documentation retrieval is recorded separately from zero Binance trading/market-data REST and WS requests.

Existing sender inspection: evidence/LEGACY_SENDER_ROUTES.json binds the deployed release source. Its defaults already use /public/stream and /market/stream; no claim that this source is unrouted is warranted. The separate legacy automatic 500-symbol launch policy remains unsuitable for a BTC-only pilot.
