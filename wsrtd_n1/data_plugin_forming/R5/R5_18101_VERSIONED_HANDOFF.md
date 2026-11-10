# Versioned handoff and exact replacement boundary

The existing PR3 supervisor recognizes Broker by executable path and an established connection to 18101, then can restart the legacy fixed 500-symbol sender on receiver changes. Its fixed startup, discovery/preload/retry behavior is unsuitable for a one-symbol budget. R5 does not patch, connect to or replace it.

The isolated ControlledSession requires an explicit BTCUSDT-only contract and hash, live exact process attestations, persistent budget, explicit start and no automatic restart. Zero REST ceilings prevent REST dispatch. `src/handoff.py` rechecks receiver pipeline session/universe/symbol bindings on every event and rejects unsubscribed symbols and duplicate JSON keys. R3 V3 preserves source event metadata and finality through disposable durable storage.

Implemented path: real loopback WS -> admitted backend -> in-process V3 handoff/receiver -> disposable SQLite -> named pipe -> compiled R5 GetQuotesEx. A separate versioned relay process between sender and receiver is NOT implemented/qualified. Therefore the requested complete 18101 replacement boundary is BLOCKED, despite isolated handoff success.

Future integration must replace the legacy sender-start decision boundary with an explicitly authorized bounded controller, preserve V3 metadata end-to-end through a qualified relay, fence stale source/receiver generations and prove genuine custody. The running supervisor must not see a new qualifying receiver until its legacy launch behavior is safely fenced under separate authorization. No production execution command is supplied for an unqualified replacement.
