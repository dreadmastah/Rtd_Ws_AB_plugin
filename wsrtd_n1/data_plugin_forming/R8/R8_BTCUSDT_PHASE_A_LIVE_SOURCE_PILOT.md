# Phase A — BLOCKED until writer custody correction and exact authorization

Proposed scope: BTCUSDT 1m, wss://fstream.binance.com/market/ws/btcusdt@kline_1m, REST0, WS1, subscription1, reconnect0, disposable raw receipts only. No AmiBroker or 18101 attachment. Full-prefix production admission is expressly not claimed.

Technical blocker: actual directory rename test failed despite held handles. Qualify Windows handle-relative creation/access or another OS-enforced exclusive output mechanism, including reparse/child-directory replacement and exact writer ownership. Review the correction; keep the CLI closed until then.

Future two-stage control (NOT authority to execute now): prepare the capture process in HELD_NO_NETWORK state, read its exact PID/creation/image, bind all source/dependency hashes and a new output directory's physical parent, then obtain explicit operator approval of the complete manifest and canonical SHA256. UTC start/end, duration (contract maximum120s), approved IPs, frame/byte ceilings remain UNBOUND. Starting the held process itself is a separately scoped future action. Do not hash a self-generated manifest and call it operator approval.

After that approval, the held process accepts the exact manifest path/digest and explicit execute flag through stdin. The current entry point refuses live execution because writer custody is unqualified. A separately reviewed correction is required before an executable command can be issued.

Abort on source/hash/process/parent mismatch, unexpected DNS, TLS failure, redirect, reconnect, budget/time exhaustion, malformed data, stale event or file failure. Close only owned socket and resolver; preserve receipts, consumed budget and failure evidence. No retry/reconnection. Raw payloads retain pending-qualification provenance. Later review must validate event timestamp, OHLCV and finality; a timeout without a final does not prove exchange malfunction.
