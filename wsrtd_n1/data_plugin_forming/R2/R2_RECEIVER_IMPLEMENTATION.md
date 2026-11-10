# Isolated receiver

transport.py converts complete supplied events; no Binance client. SHA256 HMAC authenticates a prebound 32-byte fixture secret and 32-character session; it does not certify Binance custody. Canonical JSON and duplicate-key rejection; 16KiB event bound; decimal strings retained; fixed identity roster; stale/future/replay/cumulative regressions rejected. At most1024 symbols and4 outstanding buckets/symbol. Pending finals backpressure instead of silent eviction. A new session requires a new Receiver instance; no event-controlled rotation.

load_history() reads only disposable SQLite under this output root, schema2/application_id1465074229 and exact context. Missing/changed prior history rejected. SQLite row dominates matching forming data; conflicts fail closed. A live final remains LIVE_FINALIZED_PENDING_STORAGE until an independently supplied matching SQLite row reconciles it. The receiver does not persist finals or provisional data. Durable writer integration remains unimplemented.

fixture_pipe.py publishes bounded little-endian snapshots in a private named pipe rejecting remote clients. Plugin validates exact server PID plus held creation-identity process handle, session and database physical key. Default Windows ACL is not a substitute for producer trust; this is an offline fixture bridge. tests/run_tests.py also passes a V2 authenticated frame through an isolated socket pair. No production18101 connection or full WebSocket deployment adapter exists.

Freshness, missing finals and invalid events exposed by Receiver.status(); those per-symbol diagnostic states are not yet completely exposed through ADK. Native GetPluginStatus stays red/OFFLINE ONLY and never claims live freshness. These are explicit remaining integration gaps.
