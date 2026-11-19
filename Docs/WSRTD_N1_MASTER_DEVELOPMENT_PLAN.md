# WSRTD N1 — Master Development and Acceptance Plan

**Revision:** R11 (2026-11-19; R20 blocked on three proof obligations, R21 proposed)  
**Document state:** Proposed for review; NOT an implementation, test approval, production release, or operator execution authorization  
**Repository:** dreadmastah/Rtd_Ws_AB_plugin  
**Scope:** Independently owned N1 native AmiBroker data-plugin line and its genuine Binance USD-M USDT-perpetual data pipeline  
**Controlling scaling requirement:** Two-symbol end-to-end acceptance, then direct full-universe qualification. No intermediate 13/100/500-symbol acceptance milestones.

> This document is a roadmap. Historical evidence retains its original scope. Passing source tests, component tests, or a small pilot does not establish production readiness.

## 1. Goal and boundaries

Deliver an independently owned Windows x64 AmiBroker real-time market-data solution capable of displaying, retaining, and updating genuine trade-based Binance USD-M USDT-perpetual one-minute OHLCV for **all currently eligible contracts**. The system must correctly handle forming and finalized bars, durable historical data, source provenance, automatic native chart refresh, symbol/watchlist registration, recovery, and supervised operation.

The protected running WSRTD legacy feed, ports 10101 and 18101, existing AmiBroker processes, installed DLLs, trading controls, and the production N1 database at D:\Amibroker_myDATA\N1 are outside offline test authority. Do not modify them without a later exact and separate authorization. Do not use a VM. Operator verification instructions should be in Windows CMD.

The N1 native owned-plugin development line is distinct from the separate legacy 500-symbol WSRTD PR #3 work and from the CAT trading/execution program. Their tests and approvals are not interchangeable.

## 2. Evidence hierarchy, custody, and status

1. **Independently verified archive:** Branch archive/wsrtd-n1-data-plugin-r1-r8 at commit fdbf6a29190dbe86d98cfbac8082a7403fee1b53. Archive contains 421 files, including 416 inventoried artifacts; all 404 available original R2–R8 manifest entries were verified at archive creation. R1 had no original manifest. Public-archive exclusions are documented in wsrtd_n1/data_plugin_forming/ARCHIVE_INVENTORY.json. The archive is historical and must remain unchanged.
2. **Local successor evidence not included in that archive:** R9–R20 were reported with local artifacts/dispositions in their respective D:\WSRTD_N1_DATA_PLUGIN_FORMING_R9 through R20 folders. R20_FINAL_DISPOSITION.json, R20_INDEPENDENT_FINAL_REVIEW.json and R20_RECOMMENDED_PROTOCOL.md were supplied and inspected in the review conversation. The user reports 17 R20 artifact hashes verified and R13–R19 preserved; this GitHub docs-only update does not independently hash or publish the complete operator-local source, DLLs or milestone ZIP files.
3. **Option 4:** The operator selected **trusted cooperating processes**, recorded in Docs/WSRTD_N1_OPTION4_TRUSTED_PROCESS_THREAT_MODEL_DECISION.md. Historical R15 hostile hard-link exposure remains failed. R17 independently closed bounded donor-WAL recovery within its scope. R18 measured authority synchronization as a dominant cost; R19 diagnosed two flushes per WAL xWrite but rejected unsafe coalescing. R20 identified a credible *internal* commit-only settlement boundary in pinned SQLite 3.54.1 but did **not** qualify the protocol: three P1 design proofs remain. R21 is proposed as static/offline proof closure, not permission to build, stress or use live data.
4. **Future results:** Incorporate only exact completed receipts, source/dll hashes, independent review verdicts, and applicable operator approvals. Do not rewrite historical dispositions.

**Current governing readiness:** STORAGE_CUSTODY=BLOCKED; PHASE_A_AUTHORIZATION=NOT_GRANTED; GENUINE_BINANCE_RECEIPT=NOT_EXECUTED; ACTUAL_AMIBROKER_CHART_ACCEPTANCE=NOT_EXECUTED; PRODUCTION_READY=false.

## 3. Development milestone ledger

| Milestone | Recorded scope / outcome | Outstanding qualification |
| --- | --- | --- |
| R1 | Diagnostic/source-assessment milestone; no original manifest | Not a release or native-live proof |
| R2–R6 | Native/transport/storage contracts, test fixtures and evidence preserved in archive | Historical scopes only; no inferred genuine live acceptance |
| R7 | Compiled native interface: isolated peer, V3 relay, forming-bar updates/finalization and durable-path test work | Genuine market-data and actual AmiBroker chart acceptance unproven |
| R8 | Scoped TLS/WebSocket external-dispatch work; 25 local fault/admission cases reported passed | Directory writer custody failed; execution refused; no genuine capture |
| R9 | Original directory-rename defect corrected; competing-process filesystem and HELD tests passed in scoped cases | SQLite main/WAL/SHM lifecycle custody and reparse-race/failure integration blocked |
| R10 | Actual reparse mutation exercised; 5 ordinary WAL/FULL crash baselines reported passed | No qualified integrated SQLite VFS; final small correction needed independent review |
| R11 | Distinct native SQLite DLL and Python adapter built; WAL/FULL writes, reads, checkpoint reached | Second custody session failed with root custody winerror=0; root release, reopen, crash recovery, fencing, 24-case matrix and final review incomplete |
| R12 | Repeated-session defect corrected; 11 author-reported transaction/readback cases, 12 lifecycle cycles and four crash-recovery cases; active-resource root release returned SQLITE_BUSY=5; R11 integrity and test-bound hashes reported verified | BLOCKED_R12: checkpoint/release crash, pending-open/partial-cleanup races, restart identity/stale-writer authority, full integrated 24-case matrix and symlink qualification incomplete. Independent review REVIEW_PENDING (usage limit). DLL SHA256 006503f7c68471c13cbeebf164352614e46a130cf2a8b5b58030a5e672eea50a |
| R13 | Independently reviewed scoped PASS for pending-open/release A–J, six synchronized crash stages, durable writer epochs, stale-writer rejection, atomic immutable-history updates; 11 transaction, 12 lifecycle, 4 inherited crash regressions passed. R12 reported unchanged; 64 entries reported manifest-verified | PASS_R13_CRASH_RELEASE_AND_WRITER_FENCING_CLOSURE, trusted-adapter/controlled-fault scope only. Overall storage custody BLOCKED: integrated 24-case matrix and symlink unqualified; arbitrary hostile handle reuse/direct VFS bypass excluded. DLL SHA256 3cf5967bd8f8c4cd2caa49661c121745af61a109f6dc1c58df7bbfdb5c24c4a4 |
| R14 | Reported 20 scoped integrated-case execution successes; final DLL changed to reject pre-existing hardlinks, while post-open hardlink creation was actually observed; no live/production actions | BLOCKED_R14_INTEGRATED_SQLITE_CUSTODY_24_CASE_CLOSURE. Four P1 findings: hardlink check-to-write and mapped SHM race (R14-REVIEW-01), symlink WinError 1314 (02), absent actual capture-manifest and pre-network admission tests20/24 (03), unproven full physical-write audit and sidecar/restart identity (04). DLL SHA256 d8b14d3dd8dd3812686802e254e5b702626c457f13286e1892785c4f9e1a4bc2 |
| R15 | Independent actual native checkpoint race demonstrated an external hard-link alias observes changed main-database bytes despite later SQLite error 10; 14 capture-validator and three CLI cases plus custody-release tests passed offline only; R13/R14 reported unchanged, manifest verified | BLOCKED_R15_HARDLINK_SHM_AND_CAPTURE_ADMISSION_CLOSURE; P1 actual alias escape, SHM and sidecar lifecycle unqualified, capture-controller integration absent, symlink test09 BLOCKED_PRIVILEGE. Existing R14 DLL retained as experimental predecessor (SHA256 d8b14d3dd8dd3812686802e254e5b702626c457f13286e1892785c4f9e1a4bc2) |
| R16 | Option 4 trusted-cooperating-process actual offline controller/adapter work; independent 19 capture CLI, 2 constructor cleanup, 13 adapter, scoped regressions. Reported 60-file manifest verified; native DLL unchanged R14 | BLOCKED_R16_OPTION4_TRUSTED_PROCESS_QUALIFICATION: valid donor WAL or WAL+SHM substituted while stopped was accepted and exposed DONOR history with main-file identity unchanged; tests 11/23 FAIL, independent P1 R16_ACCIDENTAL_WAL_RESTART open. Original R15 hostile-alias FAIL preserved; historical symlink 09 BLOCKED_PRIVILEGE |
| R17 | Genuine integrated native DLL & Python-adapter offline recovery work: previously authorized DB/WAL lifecycle rejects donor WAL before SQLite open; legitimate OWNER crash recovery, clean sidecar recreation, epoch fencing and controller refusal accepted by independent review. Reported 99-file manifest verified; R13–R16 unchanged | PASS_R17_DURABLE_SIDECAR_RECOVERY_IDENTITY_CLOSURE scoped offline only; candidate artifacts/r17_sqlite.dll SHA256 25eb711e3834b21f85ab7bc09bcdb35824816a8bc74091081b95996899279957. K/L/K_WRITE ambiguous transitions BLOCKED_PRESERVED; no power-loss proof or full-history performance acceptance; Option4 overall BLOCKED; historical symlink 09 BLOCKED_PRIVILEGE |
| R18 | Bounded offline telemetry-only native test, 2/13/100/522/1024 synthetic symbols over 2–4 minutes; reported 105-file manifest verified and predecessor R13–R17 unchanged. 522×2 minutes took 68.63 s, 1,024×2 took 97.64 s; telemetry shows authority flush 445 calls/44.90 s at 522 and 669 calls/63.37 s at 1,024; WAL hashing only ~0.058/0.113 s, respectively. Counters overlap; no optimization adopted | BLOCKED_R18_SCALABLE_AUTHORITY_AND_RECOVERY_QUALIFICATION: full-history/long-run and forming-event sequence unqualified; unexecuted post-WAL-flush/pre-ACTIVE and delete-intent/pre-completion crash boundaries; separate-process receiver and actual power loss unverified; K/L/K_WRITE BLOCKED_PRESERVED. Telemetry DLL SHA256 1ea77380a996d0445882f47672f503d5aaff01b641093ecfcf172e64cf5da715 |
| R19 | Independent diagnosis confirmed two authority flushes per WAL xWrite plus lifecycle pairs (141 flushes on both baseline and diagnostic candidate). Tested post-WAL-flush/pre-ACTIVE and pre-delete SHM/WAL intent hooks, retained eager authority and native regressions. Diagnostic DLL SHA256 ecbdbfdf3c9af8ac7b4deb8599c07f67fb30ef2d76e577e19a80702bab0694da; reported 113-file manifest and R13–R18 preservation | BLOCKED_R19_DURABLE_AUTHORITY_FLUSH_OPTIMIZATION: coalescing rejected, no speedup and no release. Bundled SQLite FULL WAL may write sector-padding tail after xSync; walUnlockExclusive does not propagate VFS unlock errors, EndWriteTransaction returns OK and exclusive mode can bypass locks. No proven durable acknowledged-commit/error-propagation boundary |
| R20 | Read-only source/design review against pinned SQLite 3.54.1 and unchanged R19 VFS/Python source. Candidate B: commit-only internal walFrames batching with eager noncommit spills; candidate insertion after successful walIndexAppend and checked WAL-tail/truncate handling, before shared header publication. Reported 17 R20 artifact hash verification; prior 113-file R19 manifest independently checked; no R20 build or runtime test | BLOCKED_R20_PERSISTENCE_PROTOCOL_DESIGN; three P1 obligations: R20-I01 prior acknowledged OWNER recovery through interrupted later batch; R20-I02 complete error propagation/cleanup and early-return/SEH bridge; R20-I03 durable-but-unacknowledged outcomes without assuming physical rollback. Reviewer accepted truthful blocked analysis but did not approve protocol. No performance improvement or implementation |
| R21 — proposed | Independent proof closure for acknowledged-history recovery, first-error lifetime propagation, and uncertain durable commit outcomes. Build exact state machine and checked SQLite return-path obligations; design-only unless separately authorized | NOT_EXECUTED; keep R19 eager baseline, Option4 BLOCKED, Phase A NOT_GRANTED |

The original R9 mandatory matrix contains 24 cases. Earlier component PASS results do **not** qualify the fully integrated database/VFS cases. R10's integrated 24-case matrix remained unqualified. Symbolic-link substitution was blocked by WinError 1314; lack of privilege is not a passing test.

## 4. Immediate engineering gate — R21 prior-history recovery, lifetime error and uncertain-commit proofs

**R20 design disposition:** `BLOCKED_R20_PERSISTENCE_PROTOCOL_DESIGN`. The independent static source review used **pinned SQLite 3.54.1** and R19 native/Python implementation. A credible **internal commit-only** batching site exists after successful `walIndexAppend` and complete checked WAL write/sync/tail/truncate work, but before publishing the shared WAL-index header (`sqlite3.c:71205` in the reviewed amalgamation). This does **not** constitute approval of a complete protocol. R20 reviewed 15 deliverables with reported verification of 17 artifact hashes, preserving R13–R19; no native code was built, no runtime tests were executed and no speedup was claimed.

**Independent P1 findings to close, not defer:**
- **R20-I01 — Prior acknowledged history:** A later transaction interrupted during a wider PENDING batch may quarantine the entire WAL even when it contains previously acknowledged OWNER commits. A new protocol must provide previously authenticated recoverable-prefix semantics or an independently justified explicit availability-contract decision. Merely preserving all bytes as `BLOCKED_PRESERVED` does not prove recovery of acknowledged history. Never derive prior trust solely from the current WAL image.
- **R20-I02 — Error propagation and lifecycle:** Specify an enforceable begin/settle/poison/close API, transaction/session lifetime ownership, sticky first-error propagation, early returns, C++ exceptions/SEH, close/finalize/rollback paths, and separately classify post-acknowledgment lifecycle errors. Source review identified ignored `walLimitSize`, close/delete/`sqlite3WalClose`, native sync/close, and Python finalize paths. Errors relevant to transaction success must not disappear behind a nominal OK.
- **R20-I03 — Durable yet unacknowledged commits:** Commit-marked WAL frames and even authority ACTIVE may persist before the caller receives success. Logical rollback cannot reverse durable physical WAL bytes. Define explicit recovery admission, idempotent transaction identity, receipt/watermark outcomes, caller-visible uncertainty, successor fencing and *no assumed rollback*.

**R21 approach:** Extend only the source-backed **Candidate B** design (checked explicit internal walFrames commit-only settlement, eager noncommit-spill handling) with precise source anchors, crash/acknowledgment state graph, recovery-prefix and error-return proofs. Independently challenge each proof with tail padding, exclusive mode, checkpoint/reset/deletion, SHM, uncommitted spill, authority-log failure, transaction retry, controller cleanup and restart; maintain original R17 donor-WAL rejection and OWNER recovery. A proof relying on a public postcommit hook, ignored xUnlock error or an external receipt after COMMIT must be rejected.

If a valid immutable/authorized prefix or error bridge cannot be proven, return `BLOCKED_R21`, provide options requiring separate authorization, and **retain the R19 eager authority protocol**. This phase remains **read-only static/design only**, without a new DLL, SQLite source patch, runtime test, benchmark, stress run, operating-system security change, live feed or deployment. When/if all P1 obligations are independently proven, define a **separately authorized and budgeted** R22 disposable implementation/test plan, not an automatic implementation permission.

**Readiness guards remain:** `ORIGINAL_NO_EXTERNAL_ALIAS_GUARANTEE=FAILED_HISTORICAL`, `OPTION4_TRUSTED_PROCESS_CUSTODY=BLOCKED`, `TEST_09=BLOCKED_PRIVILEGE`, `AMBIGUOUS_TRANSITIONS=BLOCKED_PRESERVED`, `FULL_HISTORY_RESOURCE_QUALIFICATION=UNVERIFIED`, `HARDWARE_POWER_LOSS_DURABILITY=UNVERIFIED`, `PHASE_A_LIVE_AUTHORIZATION=NOT_GRANTED`. Genuine Binance acquisition, AmiBroker native receiver, production install/source switching and the final direct 2-symbol-to-ALL-eligible scaling remain separate acceptance gates. The incomplete R9–R20 local source/DLL/ZIP backup must not be reported COMPLETE from a docs-only update.

## 5. Phase A — first genuine Binance source receipt (separate approval)

**Purpose:** Prove that a strictly bounded, independently reviewed N1 producer can receive and validate genuine Binance trade-based one-minute kline data without connecting to AmiBroker or the installed 18101 feed.

The existing archived R8 proposal is **BTCUSDT-only**: one approved WebSocket stream, no REST, no reconnect, no AmiBroker attachment, and a finite execution window (the archived contract specifies a 120-second maximum). It is a proposed pilot, **not current authority to execute**.

Before even preparing a live execution:

- Qualify physical writer custody and actual native adapter/producer/receiver provenance.
- Bind the precise executable/source/dependency hashes, HELD process and physical-output identity, endpoint resolution, permitted IP addresses, frame/byte limits, request/connection limits, duration and exact UTC start/end.
- Independently validate the capture-only state machine and fail-closed admission. The approved HELD snapshot and canonical manifest digest must be expressly authorized by the operator; a self-created hash cannot approve itself.
- Check public-IP and protected 10101/18101 resource budgets. Never attach to the legacy 18101 listener or create a parallel uncontrolled full-market stream.
- Verify genuine exchange symbol, kline interval, event/open/close timestamps, OHLCV and forming/finalized status; retain raw evidence with appropriately qualified provenance.
- Abort safely on unexpected network, TLS, identity, data, write or budget conditions; stop only test-owned resources.

**Phase A PASS:** Genuine, traceable BTCUSDT source events and the required bounded source/admission evidence; no hidden claim that AmiBroker displayed the data. Any subsequent ETHUSDT source coverage requires its own qualified scope.

**Phase A remains NOT AUTHORIZED.**

## 6. Phase B — actual AmiBroker native two-symbol acceptance (separate approval)

**Purpose:** Prove genuine source-to-native-host data delivery using BTCUSDT and ETHUSDT (the two-symbol pilot). Start with the Phase-A-approved source path; extend to ETHUSDT only after the corresponding technical review and execution authority.

Required proof:

- The correct reviewed native DLL, adapter, receiver, source, AmiBroker process and **disposable** database are physically/session bound.
- An independently qualified, test-owned receiver/relay is used; **never** connect the pilot to legacy 18101.
- Correct initial history; forming-minute refreshes; same-minute finalized promotion; no duplications, false synthetic provenance, timestamp shifts or historical truncation.
- Quote Editor and charts show genuine correct OHLCV and UTC minute identity. Correlate source event, receipt, durable commit, native callback and chart refresh. Observe at least two finalized transitions under the scoped pilot.
- Weekly/daily mixed interval behavior, chart persistence, reconnect and host lifecycle are independently qualified when their particular acceptance gates are exercised.
- Preserve installed historical data and restore only explicitly authorized test-owned resources after the pilot.

No actual native DLL installation, Broker restart, source switch or production database change may be inferred from Phase A. Such actions require their own exact approval.

**Phase B PASS:** BOTH BTCUSDT and ETHUSDT pass the end-to-end genuine-native acceptance criteria. Phase B is not a 500+ streaming qualification.

## 7. Full-universe scaling qualification — revised mandatory sequence

### 7.1 Required sequence

**2 symbols (BTCUSDT + ETHUSDT) → ALL currently eligible symbols.**

After Phase B two-symbol end-to-end acceptance and before any broader execution, qualify and authorize a **direct full-universe experiment**. **There will be no required intermediate 13-symbol, 100-symbol or 500-symbol acceptance milestones.** Do not impose an arbitrary cap of 500 on eligible symbols.

This is a target acceptance sequence, **not** authority for an unsafe instantaneous subscription surge. Internal connection sharding, bounded initialization, controlled admission and rate-limit compliance are operational mechanisms, not additional acceptance milestones. If full-universe scope cannot be safely supported by the verified resource envelope, stop and return BLOCKED rather than silently certifying a reduced cohort.

### 7.2 Eligible universe and daily maintenance

Use fresh authoritative Binance USD-M exchange metadata; eligible means USDT-quoted, USDT-margined, contract type PERPETUAL, status TRADING. Exclude spot, COIN-M, USDC-quoted/margined, delivery/quarterly, prelaunch, inactive and unsupported contracts. Use exact source identifiers and independently reviewed aliases, if any; do not invent synthetic symbol identity.

At **00:00:00 UTC daily**, perform the intended eligibility reconciliation, then safely update the subscription and active-watchlist state. Evaluate additions, status changes, removals and reactivations; retain historical data for inactive/delisted identities. The daily time is the desired scheduled check, not evidence that it has already passed actual runtime acceptance.

Never assume a fixed eligible count (500, 522, 523 or 600). Report the current actual eligible count, metadata timestamp, subscriptions, acknowledgments, registered AmiBroker symbols and verified active-watchlist membership **separately**.

### 7.3 Full-universe acceptance criteria

Full-universe PASS requires all of the following within an approved, finite observation and recovery test scope:

- 100% eligible-identity accounting; every current eligible contract has validated admission/subscription state or a documented blocker; admission failures do not count as streaming success.
- Genuine trade-based forming and finalized 1-minute OHLCV per required symbol, with independent source/provenance and finalized-bar cross-checks.
- Explicit freshness, missing/duplicate/conflict counts, timestamp continuity, no fabricated bars and transactionally durable receipts/watermarks.
- Verified native AmiBroker quotation readback, chart refresh, registry and active-watchlist reconciliation for the entire qualified universe, not merely Python relay delivery.
- Bounded shard/connection rates, reconnects, REST repair, disk/CPU/RAM usage, queue depth, WAL growth and synchronization behavior; abort on violated limits.
- Supported late-listing short histories; historical bootstrap/recovery must remain bounded. Retain existing history and treat full-prefix coverage as a separately evidenced requirement, not an assumption from streaming.
- Tested restarts, source exceptions, feed interruption, daily UTC universe changes and successor writer takeover as applicable.
- Precise per-symbol failures and an honest overall disposition. Partial coverage is PARTIAL/BLOCKED, never full-universe PASS.

**No intermediate cohort PASS gates** are mandated by this plan. If resource evidence is inadequate for full-universe authorization, perform more *offline* capacity assessment rather than declaring a reduced live cohort accepted.

## 8. Historical data, native integration and chart invariants

- One-minute storage is the base record. Never overwrite, truncate or erase valid finalized history to optimize cache or achieve acceptance.
- Distinguish exchange-originated finalized history from forming state and fixture data. Only exchange-confirmed finalized candles may enter finalized immutable history.
- Carry explicit timestamp, symbol, source/receipt, storage and native-readback identities.
- Test historical gaps, rehydration, listing-to-cutoff coverage, REST backfills and rate limits under a separate approved scope. Full-prefix history cannot be claimed from a few observed live minutes.
- Support expected AmiBroker 1-minute, intraday, daily and weekly presentation while preserving host-specific correctness. Retained number-of-bars and quotation-cache settings are not proof of delivery capacity.
- Do not claim direct native watchlist modification until an actual supported in-host writer and independently verified membership are established.
- Producer freshness, durable store freshness, native quotation freshness and rendered chart freshness must remain distinct metrics.

## 9. Production readiness, cutover and endurance

Production activation is **after** successful Phase A, Phase B, direct full-universe qualification, long-run correctness, and separate exact deployment authority. No preceding PASS automatically permits a production DLL replacement.

Plan and independently review:

1. Application-consistent backup/restore and immutable historical records.
2. Exact candidate DLL/source manifest, target host/database identity, installation/removal authority and rollback procedure.
3. Coexistence and isolation from the protected legacy feed and any trading processes.
4. Controlled activation, single-writer protocol, safe crash/restart and no ambiguous dual active sources.
5. Continuous full-universe freshness, automatic UTC reconciliation, reconnect/repair, gap audit and resource-budget monitoring across real operating boundaries.
6. Native 1-minute/chart persistence, weekly/mixed intervals, watchlist consistency and correct dashboard status over a defined endurance window.
7. Explicit STOP/ROLLBACK criteria; no deployment before full authorization and independent sign-off.

## 10. Gate ledger for Codex and reviewers

| Gate | Required outcome | Status on 2026-11-19 |
| --- | --- | --- |
| G0 — Archived lineage | Preserve R1–R8 and exact evidence | ARCHIVED; production proof absent |
| G1 — Storage/VFS custody | Option4 trusted recovery, authenticated prior-commit recovery, enforceable error propagation, uncertain-commit disposition and independent review | R20 BLOCKED (three P1 design gaps), R21 proof closure proposed; Option4 overall BLOCKED |
| G2 — Phase A preauthorization | Exact HELD manifest, custody, endpoint/budget and operator approval | NOT_GRANTED |
| G3 — Phase A | Genuine BTCUSDT isolated capture and independent receipts | NOT_EXECUTED |
| G4 — Phase B | Genuine BTCUSDT + ETHUSDT native AmiBroker end-to-end | NOT_EXECUTED |
| G5 — Direct full universe | TWO → ALL eligible; no 13/100/500 stage gates | NOT_AUTHORIZED |
| G6 — Production cutover | Long-run endurance, safety, backups, rollback and operator approval | NOT_AUTHORIZED |

Keep **technical completion**, **independent review**, **operator execution authorization**, and **production deployment** as four distinct decisions.

## 11. Required reporting and maintenance

For each new milestone, preserve exact TASK_ID, predecessor integrity, Git commit/source/DLL hashes, changed-file inventory, test matrix, independent review, Windows CMD verification, environment bindings and an explicit PASS/PARTIAL/BLOCKED disposition. State every unsupported or permission-limited test explicitly. Do not hide blockers by reducing the denominator or promoting component PASS to integrated PASS.

Maintain this master plan via reviewed documentation pull requests. Do not edit the frozen R1–R8 archive to retrofit newer results. Update the milestone ledger with R21 and later results only when exact evidence is available; note whether the underlying local packages were independently verified or subsequently archived on GitHub.

## 12. Source and review pointers

- Owned-plugin architecture: Docs/WSRTD_Owned_CPP_Architecture_R1.md.
- Earlier WSRTD handoff: Docs/WSRTD_PROJECT_CONTEXT_2026-10-13.md.
- Archived R1–R8 status: wsrtd_n1/data_plugin_forming/STATUS.md on branch archive/wsrtd-n1-data-plugin-r1-r8.
- Archived R8 Phase A proposal: wsrtd_n1/data_plugin_forming/R8/R8_BTCUSDT_PHASE_A_LIVE_SOURCE_PILOT.md (archive branch).
- Archived R8 Phase B proposal: wsrtd_n1/data_plugin_forming/R8/R8_BTCUSDT_PHASE_B_NATIVE_HOST_PILOT.md (archive branch).
- Local reported successor dispositions: D:\WSRTD_N1_DATA_PLUGIN_FORMING_R9\R9_FINAL_DISPOSITION.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R10\R10_FINAL_DISPOSITION.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R11\R11_FINAL_DISPOSITION.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R12\R12_FINAL_DISPOSITION.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R12\R12_INDEPENDENT_FINAL_REVIEW.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R13\R13_FINAL_DISPOSITION.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R13\R13_INDEPENDENT_FINAL_REVIEW.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R14\R14_FINAL_DISPOSITION.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R14\R14_INDEPENDENT_FINAL_REVIEW.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R15\R15_FINAL_DISPOSITION.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R15\R15_CUSTODY_ARCHITECTURE_DECISION.md; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R16\R16_FINAL_DISPOSITION.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R16\R16_INDEPENDENT_REVIEW.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R17\R17_FINAL_DISPOSITION.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R17\R17_INDEPENDENT_FINAL_REVIEW.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R17\R17_WINDOWS_CMD_VERIFICATION.md; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R18\R18_FINAL_DISPOSITION.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R18\R18_BASELINE_RESOURCE_PROFILE.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R18\R18_WINDOWS_CMD_VERIFICATION.md; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R19\R19_FINAL_DISPOSITION.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R19\R19_INDEPENDENT_FINAL_REVIEW.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R19\R19_OPTIMIZATION_DECISION.md; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R19\R19_WINDOWS_CMD_VERIFICATION.md; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R20\R20_FINAL_DISPOSITION.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R20\R20_INDEPENDENT_FINAL_REVIEW.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R20\R20_RECOMMENDED_PROTOCOL.md. These paths are operator-local evidence references, not files automatically present in GitHub.

**Non-negotiable operator decision:** After a successful two-symbol native pilot, attempt to qualify **all** eligible contracts directly; do not insert mandatory 13/100/500-symbol acceptance stages. Safety, capacity, independent review and explicit execution gates still apply.
