# WSRTD N1 — Operator architecture selection: Option 4 (trusted cooperating processes)

**Decision date:** 2026-11-17  
**Decision status:** OPERATOR_SELECTED_FOR_CONTRACT_REVISION; TECHNICAL_ACCEPTANCE_PENDING  
**Selection source:** Operator's explicit instruction, “do option 4,” following the R15 architecture decision and R16 options.  
**Scope:** N1 data-plugin SQLite storage custody *threat model*, not installed production access, process creation, source switching, network, or system security settings.

## 1. Selection and preserved predecessor failure

The operator selects **Option 4: explicitly revise the no-external-alias threat model to trusted cooperating processes only**. This selects a narrower engineering contract; it does **not** fix the hard-link race or establish OS-enforced lifetime no-alias protection.

R15 independently demonstrated that a hard link introduced after validation but before checkpoint write exposed modified main-database bytes at an external alias. A later SQLite error did not prevent the write. Preserve that observation, its P1 finding, source/DLL identities and the BLOCKED_R15 disposition unchanged.

**The original protection claim, “no external alias can observe writes even against competing local processes,” is withdrawn from proposed future acceptance under Option 4; it remains demonstrably FALSE for the prior implementation.** Never mark this legacy requirement PASS.

## 2. Proposed replacement threat model and trust boundary

**In scope — trusted cooperating environment:**
- An operator-authorized producer/controller, custody adapter and SQLite VFS instance using the documented initialization, ownership and writer-epoch protocol.
- Explicitly authorized reader processes (including a future separately authorized AmiBroker native receiver) that do not create filesystem aliases or bypass the storage API.
- Accidental process interruption, crashes, stale-but-cooperating processes, controlled concurrent readers, misconfiguration, cleanup errors and bounded network/IO failures.
- Test-owned disposable files and same-process or cooperative cross-process lifecycles.

**Excluded adversarial behaviors — no lifetime security guarantee:**
- A malicious or noncooperating local process (including one using the *same Windows user token*) creating hard links, symbolic links, reparse redirections or manipulating owned database/WAL/SHM files.
- Another process directly writing SQLite files or bypassing the approved custody adapter, writer fencing, or VFS.
- Privileged filesystem/ACL/volume tampering, kernel manipulation, and arbitrary external handle-value reuse.
- Guaranteeing that file writes or mapped SHM changes are invisible through adversarial external hard-link aliases.

These exclusions are **accepted risks of selecting Option 4**, not repaired defects. They do not authorize file tampering or unsafe operation.

**Assumption that must be independently established at every activation:** All processes with relevant file-system access to the selected disposable storage location are either cooperating under this protocol or explicitly acknowledged as a residual risk. Do not claim that an unmodified Windows account/ACL enforces this assumption. The operator must be told if same-user untrusted processes can access the chosen storage.

## 3. Minimum operational safeguards retained

- Single authorized writer with durable epoch, startup identity checks and stale-writer rejection.
- Exact source/DLL, authorized process, physical database, WAL/SHM and root identity checks for accidental replacement and reopen/restart.
- Transactional finalized-candle, provenance receipt and watermark consistency; SQLite WAL/FULL durability and crash recovery.
- Process quarantine on unexpected tracked-handle closure and fail-closed behavior for missing authority or ambiguous identity.
- No code path may deliberately create external hard-link, symbolic-link or reparse aliases of owned SQLite files.
- Restrict ordinary writer/reader paths to configured, operator-approved locations through the cooperating adapter.
- Audible/inspectable residual risk disclosure, backup/rollback and cleanup; no implication that these are hostile-process isolation guarantees.
- Real capture-controller integration: mandatory old cases 20/24 were offline entrypoint-only PASS_SCOPED in R15, not true end-to-end integration.
- Complete trusted-operation physical write audit and sidecar/restart lifecycle testing. A technical failure not caused by an explicitly excluded adversary still blocks acceptance.

## 4. Mandatory-case migration policy

Keep original R9–R15 evidence and all **24 original case IDs** unchanged and visible. Do not delete or rewrite test histories.

For each historical case, create a matrix:
1. Original requirement and existing result.
2. Applicability under the approved Option 4 trusted-cooperation assumption.
3. Exact new scoped acceptance criterion.
4. Required executed evidence and independent-review decision.
5. Unresolved limitation or excluded adversarial mechanism.

A test that exclusively models an excluded hostile operation may be labeled `OUT_OF_SCOPE_OPTION4_CONTRACT` **only after** the reviewer confirms the mapping and the documentation explicitly states that the earlier case was not technically passed. Never reclassify existing failures or blocked tests as PASS.

In particular:
- **09:** Historical symbolic-link creation remains BLOCKED_PRIVILEGE (WinError 1314). Document whether adversarial substitution is excluded and whether *cooperative accidental* reparse/traversal rejection still needs a separate test; never mark test 09 PASS by inference.
- **20/24:** Real capture authorization and pre-network rejection still required through the actual controller, even with trusted processes.
- **23:** Prove all cooperative storage writes, memory mappings and restart/sidecar operations are properly bound; explicitly **exclude** the hard-link external-alias guarantee. Do not describe this as proving the old physical write-custody invariant.
- **Hard-link checkpoint race:** Preserve FAIL_ACTUAL_CHECKPOINT_RACE as historical adversarial evidence and mark excluded from *new* claimed guarantees only after the contract revision review.

## 5. Gated implementation sequence

1. Independent technical/security review of this selected replacement contract and precise case-by-case mapping, including same-user bypass risk.
2. A separate **offline-only** Codex R16 implementation/qualification task under Option 4. Verify the original R15 sources, no production changes, and avoid another attempt to repair hostile-process lifetime aliases with link-count polling.
3. Integrate the actual trusted capture-controller refusal path and full offline VFS/SHM/sidecar, crash/restart and single-writer qualification to the revised requirements.
4. Produce exact source/test hashes and reviewer verdict. Status is `BLOCKED_OPTION4_TRUSTED_CUSTODY_QUALIFICATION` until the revised technical gate is actually passed.
5. Even on successful scoped technical qualification, Phase A requires independent source provenance, a time/endpoint/budget-limited HELD snapshot, explicit operator execution approval, and protections for the existing 10101/18101 feed. Phase B, later all-eligible scaling and production remain separately gated.

## 6. Explicit authorization boundaries

**Authorized here:** Record Option 4 selection; propose and review contract revision; prepare and execute *offline disposable tests* with existing permissions subject to the existing no-production-mutation boundaries.

**Not authorized:** Account/token/ACL/security changes, symlink privileges or Developer Mode changes, a new volume/service/driver, live Binance requests, enabling Phase A, changing or restarting AmiBroker, installing DLLs, touching protected 10101/18101 services, modifying production databases, changing scheduled tasks, or modifying live trading.

```text
ARCHITECTURE_SELECTED=OPTION_4_TRUSTED_COOPERATING_PROCESSES
OPTION4_CONTRACT_REVIEW=REQUIRED
HISTORICAL_R15_HARDLINK_RACE=FAIL_PRESERVED
OS_ENFORCED_NO_EXTERNAL_ALIAS=NOT_CLAIMED
OVERALL_N1_STORAGE_CUSTODY=BLOCKED_PENDING_REVISED_SCOPE_QUALIFICATION
PHASE_A_LIVE_AUTHORIZATION=NOT_GRANTED
GENUINE_BINANCE_RECEIPT=NOT_EXECUTED
ACTUAL_AMIBROKER_CHART_ACCEPTANCE=NOT_EXECUTED
PRODUCTION_MUTATIONS=0
```
