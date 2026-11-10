# BTCUSDT genuine pilot — NOT READY FOR EXECUTION

Proposed exact endpoint: wss://fstream.binance.com/market/ws/btcusdt@kline_1m
Symbol BTCUSDT, interval 1m, REST 0, WS connections 1, URL stream subscriptions 1, reconnects 0, disposable database only. UTC start/end and duration remain UNBOUND. No current process identity is carried forward as future authority.

Shortest remaining path:
1. Implement/qualify the external DNS/address/TLS transport against the documented policy. R7 deliberately dispatches only localhost; a local TLS success is not external production readiness. Resolve bounded DNS cancellation limitations and outbound control-frame rate enforcement before approval.
2. Bind actual permitted producer/controller/relay/receiver/writer identities, final hashes and physical disposable database. Local observed TCP peer custody is not operator authorization or atomic protection against all OS races.
3. Supply authoritative listing-to-cutoff historical coverage and provenance admission. Existing bootstrap R2 recorded suffix and synthetic coverage cannot establish full-prefix completeness. Reuse parser/planner tests; do not reacquire everything blindly, but missing genuine coverage still needs separate acquisition authority.
4. Qualify the host lifecycle/source selection and preserve 10101/18101. Do not attach a new receiver to the existing 18101 supervisor: it can start the legacy 500-symbol sender. A versioned separately authorized handoff must fence that decision first, or an independently qualified test-owned path must remain disconnected from 18101.
5. After technical gates and review pass, bind one finite UTC window, byte/frame ceilings, all hashes, source generation, cleanup and exact host/network permissions. Genuine network, DLL installation, source change and historical admission are separate approvals.

Abort for wrong peer/generation, unexpected endpoint/request/reconnect, budget/deadline failure, stale data, finality conflict or storage failure. Close only authorized test-owned sockets/processes; no fallback to legacy sender and no automatic reconnect. Preserve original DLLs and historical records. R7 itself remains fixture-only and may not be installed as a genuine feed.
