# WSRTD engineering instructions

These instructions apply to every WSRTD development, debugging, review, test, remediation, build and deployment task. The operator must not have to restate existing architecture requirements. The task prompt defines the immediate objective; the approved architecture defines required product behavior.

## Mandatory preflight — before making changes

1. Identify the actual canonical Git checkout, branch, HEAD, working tree state, and effective AGENTS.md / AGENTS.override.md instructions. Preserve unrelated changes.
2. Read the canonical architecture: [Docs/WSRTD_Owned_CPP_Architecture_R1.md](Docs/WSRTD_Owned_CPP_Architecture_R1.md). The companion Word reference is Docs/WSRTD_Owned_CPP_Plugin_Architecture_Reference_R1_2026-10-29.docx. The verified R1 Markdown Git blob is e5987a6d2b2fac9c6bd20e6ddd93be4bdbe310b9. Use the latest explicitly approved revision; investigate any unexplained mismatch rather than silently accepting it.
3. Consult approved amendments/deviations, the latest architecture traceability matrix and acceptance evidence, and [PLANS.md](PLANS.md). Locate actual local records; do not invent paths or approval. A missing authority or material evidence is a blocker for the affected work. Read-only discovery may continue.
4. Report a concise preflight: task ID, repository path/HEAD, architecture path/revision/hash, applicable requirement IDs or section numbers, approved deviations, known conflicts, proposed change compatibility and planned tests. Read the relevant architecture each task, not merely a predecessor summary.
5. If a task conflicts with architecture, stop the conflicting change and request an explicit approved amendment. Do not weaken a requirement to make a milestone pass. Nested instructions may add constraints but must not silently override these obligations.

## Permanent product invariants

The following is a non-exhaustive checklist; derive all additional requirements from the actual controlling documents.

- Independently owned x64 C++ AmiBroker ADK plugin, verified database-bound SQLite and genuine Binance USD-M USDT perpetual OHLCV. No unscoped database fallback, fabricated bars, unsupported aliases or unintended historical replacement.
- Eligibility is determined by a validated exchange metadata snapshot, not by history completeness, registration, subscription or freshness. No fixed 500-symbol or other historical universe cap. Reconcile startup, 00:00 UTC and missed midnight; preserve last-known-good membership on metadata failure.
- Admit eligible zero/sparse-history listings. Maintain independent per-symbol listing boundaries and watermarks, never a shared history-origin startup gate. Keep complete-since-listing acquisition distinct from the latest 24-hour M1 chart preload and at least 250 Daily/Weekly bars where available.
- Add/remove subscriptions dynamically. Inactivation/delisting must not restart the whole producer, reconnect unrelated streams, reload AmiBroker or interrupt healthy forming/finalized candle delivery. Target only the affected symbol; contain unavoidable transport recovery to the smallest affected shard. Keep other symbols progressing during bounded repair.
- Register absent tickers automatically using supported, host/database-identified, idempotent native operations with exact existence checks and independent readback. Do not retain borrowed ADK pointers or manipulate proprietary files without proven supported ownership. No manual per-symbol workflow as a production dependency.
- Resolve managed watchlist BINANCE_USDM_ACTIVE by exact name. Verified membership represents the reconciled eligible universe, including sparse listings. On inactivation remove only managed membership and subscription; retain ticker and all historical OHLCV. Preserve unrelated watchlists. Do not claim completion before native readback.
- Separate forming and accepted completed candles, use UTC minute semantics, validate Daily and Monday-based Weekly compression, preserve history across short-buffer returns and reopen. The known partial Weekly overlap issue remains a production blocker unless expressly resolved.
- Bound queues, refresh, REST weights, retries, reconnection and repair; retain rate telemetry and HTTP 418/429 safety stops. Use exclusive accountable writer custody and epoch fencing. Do not convert bounded diagnostic test ceilings into permanent product limits.
- Native status: green only with valid database, verified source/owner and required fresh completed-minute native coverage; yellow for initialization/repair/reconciliation/verification; red for stale/unavailable/error. Preserve distinct eligible, configured scope, registered, watchlisted, subscribed, relay-forwarded (N/A for direct transport), native availability and fresh counters. Unknown stays unknown; stale/terminal evidence is not current health. Keep concise labels and approved detailed tooltip/diagnostics.
- Protect production databases, historical data, existing DLLs/services, protected ports 10101/18101, unrelated processes/tasks and trading controls. Test/installation/deployment/native mutation require their own applicable operator authorization; a development task is not a production release.

## Implementation and acceptance

Map changed behavior to architecture sections/requirement IDs and actual code/tests. Run relevant architecture regressions, especially zero-history admission, hot delisting with uninterrupted unaffected candle delivery, metadata failure preserving last-known-good, history preservation, stale green rejection, host identity invalidation, and ownership fencing. Distinguish simulated transport, offline classification, operator observation, machine evidence, genuine native acceptance and production qualification. Do not rerun accepted tests without a regression reason; do not claim tests were run when unavailable.

Before completion report architecture conformance, affected requirements, exact source/commit and changed files, applicable tests and limitations, new conflicts or unapproved drift, remaining native gates, and production mutations/readiness. Update relevant traceability rows and the roadmap without rewriting canonical requirements. For binaries record ABI/build identity and exact SHA-256. Print actual absolute artifact paths for local operator handoff. Preserve earlier evidence and report corrections explicitly.

## Detached or successor workspaces

Instructions are not automatically inherited by an unrelated directory. Before starting work there, establish a local AGENTS.md which identifies the verified canonical checkout by absolute path and requires reading its current AGENTS.md, architecture, deviations and traceability records. Inspect existing instructions before adding the reference; never overwrite unrelated instructions or create divergent architecture copies. Pin/record the approved architecture revision and hash for the task. Repeat discovery in a fresh Codex session from the workspace and confirm the applicable instructions are loaded. Stop implementation if the authority is unavailable or ambiguous.

Keep private local paths, credentials, live databases and operational evidence out of public commits. Follow [PLANS.md](PLANS.md) for sequence; the plan never supersedes architecture.
