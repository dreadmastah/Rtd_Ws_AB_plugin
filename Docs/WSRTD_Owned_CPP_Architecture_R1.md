# WSRTD Owned C++ AmiBroker Plugin — Architecture Reference R1

> Architecture target-state and verified status as of 2026-10-29. **Not a production-release approval.**

**Architecture outline and implementation reference \| Revision R1 \| 29 October 2026**

Repository target: dreadmastah/Rtd_Ws_AB_plugin • Platform: Windows 10 x64 / AmiBroker 7.20.0.7200

Purpose. Define the intended architecture, boundaries, data contracts, current evidence, outstanding native acceptance, and milestone roadmap for the independently owned WSRTD C++ real-time data plugin. This is an engineering reference and an accurate source for a future GitHub README. It is not a production-release or installation approval.

# 1. Executive architecture

The owned plugin is intended to replace dependence on the legacy closed-source R2 data-plugin implementation. The x64 C++ DLL is database-bound and reads verified quotation data from database-scoped SQLite storage. Separate components handle Binance USD-M eligibility discovery, genuine candle ingestion, native symbol/watchlist synchronization, health reporting, and controlled supervision. Registry membership, watchlist membership, subscriptions, and genuinely fresh native candles must remain distinct measurable states.

Binance USD-M exchangeInfo + completed 1m OHLCV

-\> discovery/normalization/validation (producer; planned native acceptance)

-\> database-scoped SQLite registry + completed bars + reconciliation journal

-\> owned C++ AmiBroker ADK DLL (Configure/Notify/GetQuotes/GetQuotesEx)

-\> disposable or production AmiBroker database (separate authorization)

-\> managed watchlist bridge / UI refresh (native binding unresolved)

-\> status reporting: source health, coverage, freshness and errors

Critical boundary: AmiBroker watchlist mutation is not established as a direct ADK function. A supported, database-identified in-host bridge or other proven writer must implement it; the DLL alone must not claim the watchlist has synchronized.

# 2. Functional components and ownership

| **Component**            | **Responsibility**                                               | **Current evidence**                                                      |
|--------------------------|------------------------------------------------------------------|---------------------------------------------------------------------------|
| C++ x64 ADK DLL          | Host ABI, database binding, quote retrieval, lifecycle           | N1 DLL loaded and selectable in actual AmiBroker; quotations not verified |
| Database-bound SQLite    | Context, symbol registry, genuine bars, reconciliation state     | N1 17/17 grouped offline checks passed; in-host data path unverified      |
| Data ingestion / feed    | Binance 1m completed bars, REST catch-up, rate limits, reconnect | Producer/streaming integration pending native validation                  |
| Eligibility reconciler   | Filter USD-M USDT PERPETUAL TRADING, additions/inactivation      | 7 universe checks passed offline; online cadence planned                  |
| Managed watchlist bridge | Register symbols, create/update BINANCE_USDM_ACTIVE, refresh     | Offline model passed; in-host two-symbol test READY, not executed         |
| Status and diagnostics   | Real-time status, discovery/coverage/freshness, alarms           | Status candidate 10 offline tests passed; installed version differs       |
| Supervisor and safety    | Isolation, owner identity, controlled rollovers, bounded failure | Separate legacy S4F offline work; owned live control not accepted         |

# 3. Scope and universe policy

- Exchange: Binance USD-M futures. Eligibility requires contractType=PERPETUAL, quoteAsset=USDT and status=TRADING on the same successfully validated exchangeInfo snapshot.

- Exclude spot, USDC, COIN-M, dated/quarterly futures, prelaunch and non-TRADING contracts. Treat SETTLING as currently inactive rather than automatically permanently delisted.

- At startup and 00:00 UTC reconcile the verified universe; optional hourly reconciliation is a proposed policy until tested and approved. Exchange metadata failure must not erase last-known-good membership.

- Newly listed contracts must register even with 0, 10, 50 or 199 available genuine bars; sparse history is not an eligibility failure.

- When a contract becomes inactive, cease live subscriptions and remove only its managed-active-watchlist membership. Preserve AmiBroker symbol identity and native historical OHLCV.

- No fixed 500-symbol database or watchlist identity ceiling. 497, 500 and \>500 simultaneous streaming must be measured, not asserted.

# 4. Quotation and persistence contract

- Base market-data event: genuine, exchange-sourced completed 1-minute OHLCV; timestamped in UTC with deterministic minute-open/close semantics. Do not publish incomplete forming minutes as final.

- Validate symbol membership, chronological ordering, OHLC consistency, volume semantics, duplicate/revision policy and source provenance before marking a bar accepted.

- Never invent, forward-fill or carry forward unavailable candles. Record missing UTC minutes explicitly and use authenticated genuine source data for backfill where supported.

- Protect immutable completed bars from unintended rollback/replacement. Daily and weekly compression must be validated in native AmiBroker; daily UTC rollover is a critical acceptance case.

- Target watchlisting history policy from the operator design: 250 daily and 250 weekly bars; forming intraday display from genuine last 24 hours of 1-minute data. This is an acceptance target, not a verified owned-DLL behavior.

- Quote-buffer return lengths of 0, 10, 50 and 199 bars must not destroy previously persisted native history; actual in-host retention and reopen/readback remain unverified.

# 5. Database binding and isolation

ADK Configure/Notify callbacks must provide a verified database context before SQLite queries or symbol registration. No unscoped registry fallback is permitted. Unknown paths, stale contexts, or cross-database operations fail closed. DB-scoped SQLite schema and code have offline qualification; actual callback ordering remains a native acceptance gate.

| **Context**                  | **Observed/current boundary**                                                                   |
|------------------------------|-------------------------------------------------------------------------------------------------|
| Disposable test database     | D:\Amibroker_myDATA\N1 — operator created; N1 data source selected; no proven completed candles |
| Legacy production database   | D:\WSRTD_PR3_Test_20261010 — protected existing OHLCV                                           |
| Installed owned DLL          | WSRTD_Owned_N1_DATABASE_BOUND.dll — hash ae7f6bc4…513af4179; mapped by AmiBroker                |
| Offline status candidate     | WSRTD_Owned_N1_STATUS_TEST.dll — hash 43b4d553…f84732; not installed by reported work           |
| Old R2 DLL and live services | Preserve; ports 18101 and 10101 not to be interfered with                                       |

An independent Windows test account alone was not a proven file-security boundary because N2 found broad Modify permissions. The operator chose direct same-PC testing; that is an accepted operational risk preference, not a security guarantee. Never conflate mere DLL presence with safe data-source use.

# 6. Native symbol and watchlist synchronization

Target managed watchlist: BINANCE_USDM_ACTIVE. Its members should equal the most recent successfully reconciled eligible universe after a confirmed update. A missing or failed metadata snapshot must leave last-known-good membership intact and flag stale discovery.

1.  Confirm exact full active database path and selected owned plugin from the current AmiBroker host; reject ambiguous external OLE instance binding.

2.  Acquire an exclusive, accountable writer for native registration and managed-watchlist updates; use supported AmiBroker interfaces only.

3.  Register absent symbols without deleting existing data; resolve watchlist identity by name, not an assumed numeric index.

4.  Compute add/remove delta, apply in a journaled idempotent sequence, independently confirm native membership, and acknowledge SQLite state only after verification.

5.  On status change, remove membership from BINANCE_USDM_ACTIVE only; retain symbol and all history. No direct active .TLS rewriting without verified supported ownership semantics.

6.  Dispatch documented refresh only after confirmed state update, with bounded coalescing and no uncontrolled UI refresh loops.

Latest result (29 Oct 2026): PASS_N1_INHOST_WATCHLIST_TEST_READY. Manual BTCUSDT/ETHUSDT procedure independently reviewed, but TWO_SYMBOL_NATIVE_WRITE_AUTHORIZED=false and no native mutation has occurred. External COM-to-PID / exclusive database-switch binding remains unresolved for automatic bridge. Do not label watchlist automation as live.

# 7. Real-time health and status

| **State**             | **Proposed meaning**                                                                                                                     |
|-----------------------|------------------------------------------------------------------------------------------------------------------------------------------|
| Green / healthy       | Database context valid, validated source available, accepted completed-minute data fresh and required symbol coverage satisfied.         |
| Yellow / initializing | Binding, discovery, reconciliation or backfill pending; data availability not yet proven.                                                |
| Red / error           | Unbound/mismatched SQLite, stale or unavailable feed, failed native registration, owner/transport error or required freshness violation. |

Status must expose distinct counters: eligible, registered, watchlisted, subscribed, relay-forwarded, natively received/available and actually fresh. Green must never mean merely “SQLite opened” or “socket connected.” The STATUS_TEST candidate has offline status tests, not accepted live status behavior.

# 8. Operational and security boundaries

- Use an independently managed, database-bound SQLite path and approved producer configuration; no automatic connection to protected ports 18101 or 10101 in testing.

- Protect existing historical data, especially EPICUSDT, MITOUSDT and PTBUSDT; operator waived an additional backup requirement, not permission to delete or overwrite history.

- No broad Python tree termination, live watchdog edits, arbitrary task control, production DLL replacement, or unapproved database switch.

- Explicitly separate native acceptance authorization from any future production migration authorization. The legacy 15-minute maximum 18101 outage is a planning limit only, not current approval.

- Abort on context identity drift, ambiguous host or watchlist writer, invalid metadata, unexpected cross-database access, or unverified native bars.

# 9. Acceptance matrix: evidence versus claims

| **Milestone / test**                | **Result as of 29 Oct 2026**                         | **Not yet demonstrated**                              |
|-------------------------------------|------------------------------------------------------|-------------------------------------------------------|
| R5D owned baseline                  | AMD64 compiled; offline replay validated             | In-host native registry and production use            |
| N1 database-bound candidate         | 17/17 grouped offline checks; independently reviewed | Actual Configure/Notify ordering and retention        |
| N1 installed in AmiBroker           | File hash matched; module mapped; plugin selectable  | Real data or healthy feed                             |
| N1 status/universe candidate        | 10 status + 7 universe offline checks; sealed        | Actual green/red source health; native auto watchlist |
| Native bridge model                 | 7 offline checks; independently sealed               | Exclusive OLE host/PID and production transaction     |
| Latest two-symbol in-host procedure | PASS preparation/readiness review                    | Manual BTCUSDT/ETHUSDT native writes not executed     |
| Full dynamic \>500                  | Registry membership model exercised \>500            | Full-universe genuine concurrent streaming            |
| Live end-to-end                     | No accepted live producer result                     | Binance -\> SQLite -\> GetQuotes -\> native 1m chart  |

# 10. Delivery and verification roadmap

| **Gate**                        | **Required acceptance / exit evidence**                                                                                                  |
|---------------------------------|------------------------------------------------------------------------------------------------------------------------------------------|
| G1 — In-host watchlist smoke    | Separately approved manual two-symbol test in N1: BTC/ETH registration, managed watchlist, idempotence, remove-only and native readback. |
| G2 — Exclusive automatic bridge | Verified current-host identity and supported one-writer transaction; no ambiguous OLE binding; repeatable watchlist delta.               |
| G3 — Genuine 1m candles         | Bound SQLite path and approved producer; BTC/ETH three successive completed 1m bars; timestamp/OHLCV and native readback.                |
| G4 — Coverage expansion         | 13 -\> 497 -\> 500 -\> \>500; distinguish registered/watchlisted/subscribed/fresh. Identify capacity and backpressure.                   |
| G5 — Dynamic lifecycle          | Start/00:00 UTC metadata reconciliation, newly listed 0-bar symbol, inactive removal-only, stale snapshot and reconnect.                 |
| G6 — Durability/rollover        | Short-buffer 0/10/50/199, close/reopen, no historical eviction, daily/weekly correct UTC boundary.                                       |
| G7 — Operational release        | Independent native review, exact DLL/source SHA, rollback/containment, separate operator approval; protect R2 runtime.                   |

# 11. Repository packaging and governance

Canonical reference location: Docs/WSRTD_Owned_CPP_Plugin_Architecture_Reference_R1_2026-10-29.docx. Companion source for GitHub browsing: Docs/WSRTD_Owned_CPP_Architecture_R1.md. Treat this document as a project target-state/acceptance reference. Existing repository README and upstream historical plugin descriptions are not automatically evidence that the current owned C++ features are released.

Every future implementation PR should report: source commit, changed files, ABI/build identity, test evidence, exact DLL SHA-256, native acceptance status, scope of production mutation, and unresolved risk. README feature descriptions must use “implemented offline”, “native verified”, “planned”, or “blocked” rather than unqualified completion claims.

# 12. Reference identifiers

N1_DATABASE_BOUND_DLL_SHA256=ae7f6bc4e9ec61c3103b48d8ee43769173b44ed1619aa61ffbcc15b513af4179

N1_STATUS_TEST_DLL_SHA256=43b4d553bec590b236859593e851792184816d330332d9b80ccbf0db39f84732

N1_SEAL2_ZIP_SHA256=79a95c59c587c59e665c46410ae998ae2b2f31d67f608caff88f8297778be9ad

N1_NATIVE_BRIDGE_ZIP_SHA256=81e6a0f840d0b4839e858b84622a0b715765448ad4df3c09aa3912506960a737

N1_INHOST_READINESS_ZIP_SHA256=27ad2c86ae4978237d8a0487f75447bbb823e043c1486e1ddd9d794007628fb9

Evidence basis: user-supplied sealed receipts, operator Windows CMD output and AmiBroker screenshots in the WSRTD project conversation; current GitHub repository metadata/README inspection. Source-code-to-built-binary provenance for every future candidate must be verified at release time. This reference is dated and should be revised after each native milestone.