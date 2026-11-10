# R5 real socket backend

`src/network.py` implements literal IPv4 loopback HTTP/1.1 and WebSocket framing with explicit TLS trust and hostname validation. Real sockets are exercised, not mocked method calls. Only ephemeral ports are admitted; 10101 and 18101 are forbidden. DNS, inherited proxies, redirects, hidden retries, compression, fragmented WebSocket messages and automatic reconnect are disabled. This is a qualified isolated backend subset, not a completed production Binance client.

`src/admission.py` commits SQLite aggregate debits before dispatch. REST count/weight, connection attempts, subscriptions, explicit reconnects, frames, bytes and expiration are persistent. Failed attempts remain charged. Reconnect status is derived from persisted WS attempt history. HTTP klines are capped at 499 per page. HTTP headers are capped at 8192 bytes, bodies at 65536, events at 16384. Inbound PING and outbound masked PONG consume frame/byte budget; control-frame loops are bounded.

Each socket operation has an at-most-one-second configured I/O deadline bounded by remaining admission time. This is not a proven strict whole-call wall-time guarantee: durable ledger work and scheduling precede or surround socket operations. Independent testing observed 1.609 seconds against a 1.5-second assertion. Failure evidence remains preserved. Cancellation closes owned sockets; it does not control any protected process.

TLS tests use disposable self-signed localhost credentials: trusted success, wrong-host rejection and valid unrelated-CA chain rejection. These do not qualify Binance DNS, endpoint routing or real certificates. Production protocol documentation/endpoint authority remains a required gate; no external request was made.
