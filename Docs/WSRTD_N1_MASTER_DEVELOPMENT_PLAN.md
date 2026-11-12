# WSRTD N1 — Master Development and Acceptance Plan

**Revision:** R4 (2026-11-12; R14 blocked and R15 proposed)  
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
2. **Local successor evidence not included in that archive:** R9–R14 were reported with local artifacts/dispositions in their respective D:\WSRTD_N1_DATA_PLUGIN_FORMING_R9 through R14 folders. R14_FINAL_DISPOSITION.json and R14_INDEPENDENT_FINAL_REVIEW.json were supplied and inspected in the review conversation. These are not independent on-machine verification of every local receipt, executable artifact or manifest entry, nor GitHub archive publication of R9–R14 source.
3. **R15:** Proposed successor for post-open hard-link and mapped-SHM lifetime protection, real capture manifest/pre-network admission, and remaining physical custody/restart audit. No R15 execution or PASS is asserted in this plan.
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
| R15 — proposed | Prove OS-enforced alias prevention or clearly bounded fail-closed design, including mapped SHM; integrate actual capture admission (tests20/24) and physical-write audit (23), separately account for symlink test09 | Not executed; no Phase A authority |

The original R9 mandatory matrix contains 24 cases. Earlier component PASS results do **not** qualify the fully integrated database/VFS cases. R10's integrated 24-case matrix remained unqualified. Symbolic-link substitution was blocked by WinError 1314; lack of privilege is not a passing test.

## 4. Immediate engineering gate — R15 hardlink/SHM lifetime and admission closure

R14 is **BLOCKED** after independent review of the exact final R14 source. There were 20 scoped execution successes, **not 20 fully integrated qualified PASS cases**. The reported R14 DLL SHA256 is `d8b14d3dd8dd3812686802e254e5b702626c457f13286e1892785c4f9e1a4bc2`. R13 and its reviewed scoped results remain unchanged.

**R14-REVIEW-01 (P1 OPEN):** Pre-existing hard-linked WAL in a predecessor build exposed writes through an outside alias; the final R14 candidate rejects pre-existing links. A competing process can nonetheless create a hard link **after** database/WAL/SHM open. Per-I/O link-count checks detect some subsequent writes, but do not close check-to-write races or the memory-mapped SHM update window. Do not treat a link-count check, path canonicalization or file-ID comparison alone as a complete physical custody guarantee.

**R14-REVIEW-02 (P1 BLOCKED_PRIVILEGE):** Symbolic-link test 09 failed creation with WinError 1314. No privilege elevation or Developer Mode/security alteration is authorized. Preserve an explicit blocked verdict until a qualifying independently authorized disposable fixture/environment is available and actually exercised.

**R14-REVIEW-03 (P1 OPEN):** Mandatory tests 20 (capture authorization manifest identity mismatch) and 24 (failure before network initialization) did not exercise the **actual** capture entrypoint and refusal path. Offline integrated admission must prove no socket, network request, or production side effect occurs on denial.

**R14-REVIEW-04 (P1 OPEN):** Test 23 must prove the complete main DB/WAL/SHM mapped-write and auxiliary physical-custody lifecycle, including closed-sidecar substitution and safe restart identity, not only sampled pathname opens.

**R15 engineering priority:** First determine and independently test whether an OS-enforced design within the approved trusted-adapter threat model can prevent post-open hard-link alias creation throughout writable/mapped lifetimes. Explicitly verify the Windows file/share/access/ACL and filesystem semantics; do not assume a specific flag or ACL blocks hard-link creation. If the required enforcement is unavailable without changing machine privileges, source architecture, or filesystem scope, record a precise BLOCKED design decision instead of stacking additional time-of-check/time-of-use checks. Evaluate an alternative storage boundary only as an explicitly scoped engineering option; no deployment or host-security change is implied.

Next, integrate actual bounded capture-manifest/pre-network rejection tests 20/24 in **offline denial mode**, and construct a comprehensive physical-write/sidecar restart audit for test 23. Preserve all 24 original identifiers, R13 regressions, complete source/DLL hashes and independent reviewer judgments. Do not convert scoped component successes into integrated PASS.

**Phase A remains NOT_GRANTED** until all mandatory storage technical tests, independent reviews, capture provenance, bounded HELD snapshot and manifest, approved network budgets, and a separate explicit operator execution authorization are complete.

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

| Gate | Required outcome | Status on 2026-11-11 |
| --- | --- | --- |
| G0 — Archived lineage | Preserve R1–R8 and exact evidence | ARCHIVED; production proof absent |
| G1 — Storage/VFS custody | Root/session lifetime, hardlink/SHM alias prevention, capture admission, integrated matrix, review | R14 BLOCKED; four P1 findings; R15 proposed |
| G2 — Phase A preauthorization | Exact HELD manifest, custody, endpoint/budget and operator approval | NOT_GRANTED |
| G3 — Phase A | Genuine BTCUSDT isolated capture and independent receipts | NOT_EXECUTED |
| G4 — Phase B | Genuine BTCUSDT + ETHUSDT native AmiBroker end-to-end | NOT_EXECUTED |
| G5 — Direct full universe | TWO → ALL eligible; no 13/100/500 stage gates | NOT_AUTHORIZED |
| G6 — Production cutover | Long-run endurance, safety, backups, rollback and operator approval | NOT_AUTHORIZED |

Keep **technical completion**, **independent review**, **operator execution authorization**, and **production deployment** as four distinct decisions.

## 11. Required reporting and maintenance

For each new milestone, preserve exact TASK_ID, predecessor integrity, Git commit/source/DLL hashes, changed-file inventory, test matrix, independent review, Windows CMD verification, environment bindings and an explicit PASS/PARTIAL/BLOCKED disposition. State every unsupported or permission-limited test explicitly. Do not hide blockers by reducing the denominator or promoting component PASS to integrated PASS.

Maintain this master plan via reviewed documentation pull requests. Do not edit the frozen R1–R8 archive to retrofit newer results. Update the milestone ledger with R15 and later results only when exact evidence is available; note whether the underlying local packages were independently verified or subsequently archived on GitHub.

## 12. Source and review pointers

- Owned-plugin architecture: Docs/WSRTD_Owned_CPP_Architecture_R1.md.
- Earlier WSRTD handoff: Docs/WSRTD_PROJECT_CONTEXT_2026-10-13.md.
- Archived R1–R8 status: wsrtd_n1/data_plugin_forming/STATUS.md on branch archive/wsrtd-n1-data-plugin-r1-r8.
- Archived R8 Phase A proposal: wsrtd_n1/data_plugin_forming/R8/R8_BTCUSDT_PHASE_A_LIVE_SOURCE_PILOT.md (archive branch).
- Archived R8 Phase B proposal: wsrtd_n1/data_plugin_forming/R8/R8_BTCUSDT_PHASE_B_NATIVE_HOST_PILOT.md (archive branch).
- Local reported successor dispositions: D:\WSRTD_N1_DATA_PLUGIN_FORMING_R9\R9_FINAL_DISPOSITION.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R10\R10_FINAL_DISPOSITION.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R11\R11_FINAL_DISPOSITION.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R12\R12_FINAL_DISPOSITION.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R12\R12_INDEPENDENT_FINAL_REVIEW.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R13\R13_FINAL_DISPOSITION.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R13\R13_INDEPENDENT_FINAL_REVIEW.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R14\R14_FINAL_DISPOSITION.json; D:\WSRTD_N1_DATA_PLUGIN_FORMING_R14\R14_INDEPENDENT_FINAL_REVIEW.json. These paths are operator-local evidence references, not files automatically present in GitHub.

**Non-negotiable operator decision:** After a successful two-symbol native pilot, attempt to qualify **all** eligible contracts directly; do not insert mandatory 13/100/500-symbol acceptance stages. Safety, capacity, independent review and explicit execution gates still apply.
