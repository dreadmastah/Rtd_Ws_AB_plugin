# WSRTD Project Context and Acceptance Handoff — 2026-10-13

**Repository:** [dreadmastah/Rtd_Ws_AB_plugin](https://github.com/dreadmastah/Rtd_Ws_AB_plugin)  
**Upstream origin:** [ideepcoder/Rtd_Ws_AB_plugin](https://github.com/ideepcoder/Rtd_Ws_AB_plugin)  
**Upstream lifecycle/usage documentation:** [Docs/WSRTD Doc.md](https://github.com/ideepcoder/Rtd_Ws_AB_plugin/blob/main/Docs/WSRTD%20Doc.md)  
**In-flight scope:** [PR #3 — Binance 500-symbol extension](https://github.com/dreadmastah/Rtd_Ws_AB_plugin/pull/3)  
**As-of:** 2026-10-13 (Philippines time)  
**Project boundary:** WSRTD market-data/AmiBroker native acceptance only; **not** the separate CAT-M11 trading-readiness program.

> **Current release gate:** `LIVE_500_SYMBOL_FRESHNESS_ACCEPTANCE=FAIL_PREVIOUS_R6` and `NATIVE_500_SYMBOL_STORAGE_ACCEPTANCE=NOT_PROVEN`. Do **not** claim production readiness, merge PR #3, or infer native persistence from relay or Python-only results.

## Evidence classes and snapshot identity

- **Direct GitHub checks:** On this date PR #3 was **open, draft, unmerged**, head branch `feat/binance-500-kline`, commit `ea79ae6df50ed419564813d2402fed0c6d29df87`. The upstream WSRTD documentation was read; it identifies documentation version 1.3 / plugin 3.06.26. The PR branch [Docs/Binance-500.md](https://github.com/dreadmastah/Rtd_Ws_AB_plugin/blob/ea79ae6df50ed419564813d2402fed0c6d29df87/Docs/Binance-500.md) states that this checkout **does not contain the native DLL implementation**.
- **Operator-supplied Codex receipts:** Windows process IDs, tests, live observations, manifest hashes and file paths below are historical reported evidence; **local evidence packages were not independently opened or rehashed while writing this handoff**. Freshly verify them before authorization.
- **Upstream descriptions:** Exact upstream version lineage and the installed `WSRTD Compatible 3.06.26 R2` binary's persistence equivalence remain **NOT_PROVEN**. An exact copy of the currently loaded DLL and matching release/build manifests have been **requested from the operator, not yet reviewed**.

## Architecture and existing Windows environment

`Binance USD-M USDT perpetual public market data → Python sender → WebSocket relay → native WSRTD receiver DLL → AmiBroker 7.20 → locally stored OHLCV / RADAR`.

| Surface | As last reported |
|---|---|
| Host | Existing Windows 10 PC; no VM or additional Windows account desired |
| AmiBroker | 7.20.0.7200; PID `85728` at R6C-R5; **PID must be refreshed** |
| Original test database folder | `D:\WSRTD_PR3_Test_20261010` |
| Database basename | `WSRTD_PR3_Test_20261010` |
| Existing receiver endpoint | `127.0.0.1:18101`, active |
| Data source | GUI-displayed prefix: `WSRTD Compatible 3.06.26 R2 (Clean-room` (truncated) |
| Database Settings | Local data storage **enabled**; base interval **1 Minute**; number of bars **100000**; operator-attested by screenshot |
| Database activity | 500 native symbol files changed during the R6C-R3 read-only audit: **active database writers** |
| Planned isolated relay | `127.0.0.1:18103` if free; not started in R6B-R2/R6C |
| Intended universe | 500 selected USD-M USDT perpetuals; 5 WebSocket shards, up to 100 subscriptions each |
| Trading | Operator confirms **no automated trading currently running on this PC**; that does **not** mean the market-data feed is stopped |

**Protect the entire original database folder**, including its runtime assets, historical acceptance logs, data, and other contents. No automatic cleanup/rename/overwrite. No private exchange account API or order placement is in scope.

### Permanent user-required automatic recovery

The operator's architecture intentionally requires:

1. AmiBroker auto-reopens if closed.
2. AmiBroker plus feed auto-launch at Windows boot/startup or logon.
3. Restart/reboot recovery.
4. Internet disconnect/reconnect recovery.
5. WebSocket disconnect/reconnect and relevant missed-data repair.
6. Sleep/wake recovery.
7. The test supervisor stops the sender if the `18101` receiver disappears, and recreates the sender when the receiver returns.

**Preserve these controls.** Automatic relaunch is **intended** and must **not** be classified as a fault or permanently disabled. R6C-R4 identified launcher/logon and sender-supervisor mechanisms, but pre-logon boot, reboot, sleep/wake, and full native reconnect/backfill correctness remain **NOT_PROVEN** as functional acceptance. A temporary maintenance interlock would require separate explicit approval, bounded duration, and verified restoration; none was activated during R6C.

## PR #3: historical implementation, validation and regressions

### Warm-up, repairs, fairness and rate limiting

- Following the initial 500-symbol expansion and UTC rollover, daily samples were produced but **102 symbols** later exceeded the specified **90-second** live candle freshness limit. Delayed daily REST repair work contributed to minute-staleness symptoms; historical forensic root cause was not exhaustively established.
- **R2 offline diagnostics:** 80 tests and 60 offline experiments passed. Fixture p95 minute-repair delay: baseline ~192.29 seconds; weighted fairness ~40.84 seconds at the same reported 1,200 REST requests. These are offline fixture metrics, **not live PASS**.
- **R3 independent review:** F001 false pass for zero-volume corruption, F002 premature fake-clock advancement, F003 diagnostic exception interfering with delivery.
- **R4 remediation:** F001/F002/F003 corrected; 107 automated tests PASS, 60 experiments PASS; independent review PASS.
- **R5 weighted fairness:** 139 automated tests PASS, 75 offline experiments PASS; isolated implementation reviewed, without commit/push.
- **R6 isolated live acceptance:** **FAIL**, 107 measured REST initiation gaps less than 250 ms, minimum ~235 ms. Warm-up-only freshness: **295 fresh / 205 stale**, maximum age ~298.294 seconds. No qualifying steady-state result and no native AmiBroker OHLCV readback.
- **R6A REST pacing correction:** verified isolated corrected source; **162 tests PASS**, 75 fairness experiments PASS, independent review PASS; loopback 1,069 initiated requests, **zero gaps <250 ms**, minimum interval **250.6616 ms**, maximum REST concurrency 1. Still **not a new full live 500-symbol acceptance**.

### Same-PC native acceptance blockers

| Phase | Result | Consequence |
|---|---|---|
| **R6B-R2** | `BLOCKED_R6B_R2_AMIBROKER_CONFIGURATION_OR_GUI_GATE` | 162 tests PASS; existing AmiBroker receiver attached to `18101`; backup/database identity not proven; proposed `18103` not started |
| **R6C-R1** | `BLOCKED_R6C_OPERATOR_GUI_ACTION_REQUIRED` | GUI/COM attachment failed; no receiver or database transition |
| **R6C-R2** | `OPERATOR_ACTION_REQUIRED_R6C_BACKUP_R2` | Operator's database-settings screenshot identified original database; live-consistent backup not established |
| **R6C-R3** | `BLOCKED_R6C_BACKUP_DEPENDENCY_R3` | 500 native files changing; automatic relaunch and supervisor sender-continuity effects; 508 database files + 140 known dependencies; external formula dependencies incomplete |
| **R6C-R4-R2** | `BLOCKED_R6C_RECOVERY_BACKUP_CONTRACT_R4_R2` | Intentionally preserved automatic recovery; installed plugin checkpoint/flush and deterministic restore unresolved |
| **R6C-R5** | `BLOCKED_PLUGIN_FLUSH_OR_RESTORE_AUTHORITY_R6C_R5` | Exact installed-DLL flush/durable-checkpoint contract NOT_PROVEN; **12 GUI/dependency observations remain**; restore isolation and native readback before live backfill NOT_PROVEN |

No backup, shutdown, receiver transition, native DB switch, protected database/process mutation, commit or push was performed by R6B/R6C reports through sealed R5. Repeated 162/162 test PASS does not replace live freshness or native storage acceptance.

## Local evidence locations — operator-reported references

All `D:\` paths refer to the **operator's own Windows PC**, not this GitHub repository. Each reported manifest should be independently reverified locally before formal use.

| Package | Local root | Reported manifest SHA-256 |
|---|---|---|
| R6 live acceptance | `D:\WSRTD_PR3_Isolated_Acceptance_20261012_R6` | `3b48ae7d4b3c314b4c7a60e2e848fc80f309de0c74d26bd46f14183f28dc6738` |
| R6A isolated corrected sender | `D:\WSRTD_PR3_REST_Pacing_Remediation_20261012_R6A` | `20febc17c070d6550302999e184e21ac911e930386f8d0e9afa172112deda2b0` |
| R6B-R2 native preflight | `D:\WSRTD_PR3_Existing_PC_Native_20261013_R6B_R2\evidence` | `b33e0b74eea7163cbb0f37d93a4823ca4a12af0e332a2f0bad8cbe9993f974d4` |
| R6C-R1 GUI gate | `D:\WSRTD_PR3_Existing_PC_Receiver_Transition_20261013_R6C_R1\evidence` | `6eb5cbf02e3672d7200808f575a55dc60feb9df8e7a5e2221357f1bbaebedf57` |
| R6C-R2 GUI binding | `D:\WSRTD_PR3_R6C_GUI_Binding_Backup_Readiness_20261013_R2` | `e5109ce3d2a8bc03ece9d1b5f2ed3443a865f553facc9dfd0b8695533dd04885` |
| R6C-R3 cold backup readiness | `D:\WSRTD_PR3_R6C_Cold_Backup_Readiness_20261013_R3` | `52305b5d1ee3da92ef306b44bc4ce04284af32dc76b7fb926488ef3a3076ee4c` |
| R6C-R4-R2 recovery preservation | `D:\WSRTD_PR3_R6C_AutoRecovery_Preservation_20261013_R4_R2` | `f1635ba8f427316b352d2b03674f81e44b4926d8ce20e8baf8ef473c644f9a97` |
| R6C-R5 flush/restore authority | `D:\WSRTD_PR3_R6C_Plugin_Flush_GUI_Closure_20261013_R5` | `de319457929b9e415c03b1b0aff10627998bf34c5fad242d93c12e23a99b4aaa` |

R6C-R5 recommended operator requirements: `D:\WSRTD_PR3_R6C_Plugin_Flush_GUI_Closure_20261013_R5\08_OPERATOR_DECISION_REQUIREMENTS.md`; final receipt: `09_FINAL_R6C_R5_ADJUDICATION_RECEIPT.json`. **Read these authoritative local reports for the exact 12 unresolved GUI observations; this handoff does not invent or restate their unseen wording.**

## Upstream reference: ideepcoder, WSRTD Doc.md

Original upstream documentation: [ideepcoder Docs/WSRTD Doc.md](https://github.com/ideepcoder/Rtd_Ws_AB_plugin/blob/main/Docs/WSRTD%20Doc.md), snapshot blob SHA `8f6d68fb40420b17b2de8890643f493284b9a6a7`, document version **1.3**, described plugin **3.06.26**.

Material upstream documentation points:

- Installation requires **local data storage enabled** and a suitable base time interval (1 minute is documented).
- **Auto-save Plugin DB** persists certain plugin state (e.g. extra data, symbol map, fundamental data) across AmiBroker restarts; **Auto-save pending BF** pertains to pending backfill that otherwise may be discarded on shutdown. **Neither setting independently proves every native OHLCV bar has durably committed.**
- The plugin can hold incoming data in **its own temporary storage**. Upstream text warns that symbols never accessed by AmiBroker may **never be pushed** into the persistent local database; it recommends an Analysis exploration/batch to force access. Treat this as a crucial 500-symbol validation risk and verify actual native readback.
- Upstream plugin Connect / Shutdown commands address WebSocket connectivity; the plugin's temporary DB is not necessarily durable across closing AmiBroker or changing databases.
- WSRTD settings under Windows registry `TJP\WsRtD\<Database_name>` are keyed to the **database name**; identically named databases in different folders can share settings. Use a **unique test database basename**, not merely a different folder.
- The document describes state persistence, backfill and mixed EOD/intraday modes, but **does not by itself establish an application-consistent cold-backup/flush guarantee for this installed modified R2 DLL**.

**Next source-lineage requirement:** Obtain a byte-for-byte copy of the **currently installed DLL** (without replacing or unloading it), its original installed path, and any matching release ZIP/build manifest. Bind the binary SHA-256/version/build metadata against the actual upstream/fork source lineage. Do not assume version-string equality proves exact source equivalence. Upload only the DLL or non-secret build documentation; do **not** share license keys or credentials.

## Immediate next action and decision gates

1. **Source authority:** Investigate the exact installed DLL's provenance and applicable lifecycle/flush documentation. The PR #3 Python repo does not contain its native implementation. If exact source or release evidence does not exist, record `NOT_PROVEN` and request author/vendor clarification rather than inventing a guarantee.
2. **GUI dependency closure:** Read the sealed R6C-R5 `04_EXACT_GUI_OBSERVATION_MATRIX.json` and `08_OPERATOR_DECISION_REQUIREMENTS.md`; collect the **12 exact** observations in one bounded read-only operator session. Do not guess menu paths.
3. **Backup and restoration:** Separately prove consistent checkpoint, complete backup scope, isolated restoration/readback before live backfill, and reconnection/recovery. Stable hashes alone establish file integrity, **not** application consistency.
4. **Receiver/native smoke:** Only after distinct operator authorization and backup/rollback readiness, use a unique test DB + isolated `18103` relay for 13-symbol native OHLCV readback against Binance public REST; restore original `18101` behavior.
5. **500-symbol acceptance:** Subsequently rerun corrected R6A live pacing, full steady-state 500-symbol freshness, native membership/minute/daily/hourly OHLCV and zero-volume fidelity. Actual UTC-midnight rollover is a separate controlled acceptance gate.

**No new transition, shutdown, cold backup, recovery-control change, VM creation, production deployment, private trading API, order, commit to PR #3, or PR merge is authorized by this informational handoff.** This documentation-only repository commit, requested specifically to preserve project context, does not supersede runtime restrictions.

## Notes for subsequent Codex/ChatGPT sessions

- Rehydrate this file and the relevant **sealed** R6C-R5 receipt before preparing the next task. Preserve all prior PASS, FAIL, BLOCKED, and NOT_PROVEN classifications exactly.
- Keep **WSRTD PR #3** separate from the unrelated **CAT-M11** autotrader gates.
- Favor source-backed, bounded work and exact evidence paths; do not loop through generic preparations if installed DLL source remains unavailable.
- Use the original upstream document as **reference**, not proof of the modified R2 DLL behavior.
- Reverify current GitHub HEAD and live process/port identities before any mutation. The values here are an as-of handoff, not live state.
