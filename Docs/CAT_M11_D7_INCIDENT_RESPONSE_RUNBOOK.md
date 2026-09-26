# CAT-M11 D7 Incident Response Runbook — R1

Project namespace: WSRTD_R2_CRYPTO_AUTO_TRADER_ONLY  
Workflow: PHASE_1_BINANCE_CRYPTO_USDT_PERPETUAL  
Status: proposed governed procedure; D7 remains NOT_PROVEN until materialization and independent validation.  
Scope: incident response only. This document is not authorization to execute controls, access accounts, deploy, enable LIVE or place orders.

## Policy basis and capability boundary

P1: Operator-governed D7 preparation contract, 2026-09-25, sections 4–12: startup, crash recovery, control vocabulary, security and live arming requirements. These are policy requirements, not claims of implemented capabilities.
P2: Repository Core/AUTHORIZATION.md and Core/README.md: current scaffold is simulation-only with routing disabled. Core/ACCOUNT_RISK.md and Core/stack/README.md: private read-only access is disabled by default, no order/cancel API, stale/unreconciled inputs fail closed, recovery of a source alone does not resolve unknown order state.
P3: CleanRoomR2/stack/README.md: single-instance ownership, redirector pairs, maintenance/watchdog semantics and data recovery. WSRTD data-service stop is not a trading emergency-control substitute.
P4: Authoritative CAT-M11 contract rebind R4 (2026-09-25): D7 is INCIDENT_PROCEDURES; D8 is RECOVERY_PROCEDURES; eight deliverables and five acceptance items remain NOT_PROVEN. R3_FINAL_ADJUDICATION=PASS_EXACT and HISTORICAL_1006_STATUS=CLEARED_BY_R3 are preserved historical dispositions; no repeat test is instructed.

Where a named control is not implemented/qualified, mark UNAVAILABLE, block entry authorization, and escalate to the accountable operator. Do not invent command syntax or emulate trading controls by killing a data process. Missing safe-continuation policy means remain blocked; it is not permission to improvise.

## Roles, common containment and evidence rules

The detecting component opens an incident; the duty operator owns containment and escalation. The accountable operator assigns a concrete incident owner and qualified verifier by recorded identity before recovery authorization. If unavailable, keep entries blocked and escalate; silence is not approval.
All IR-01–IR-15 incidents inherit C1–C8 below as normative requirements. The incident-specific section adds detection, severity, control, evidence, reconciliation and recovery conditions; all twelve closure questions are thereby answered for every class.

C1 Immediate state: block new entries, revoke any entry-arming authorization through a proven authorized capability; record UNKNOWN/UNAVAILABLE if the control cannot be enforced. Do not falsely claim a successful DISARM.
C2 Exit policy: no blanket permission to route exits. Existing independently verified protection must not be cancelled casually. Exit-only management is permitted only when authoritative exposure, correct environment, qualified control path, risk policy and operator authorization all prove it safe. Otherwise record EXIT_PATH_UNPROVEN and escalate critically. Current simulation-only build cannot issue exchange exits.
C3 Controls: select the least disruptive policy-permitted containment with recorded authority, available capability and acknowledgement. A requested action is not proof it succeeded.
C4 Evidence: record UTC and monotonic/correlation identifiers where available; preserve original events, references and hashes. Redact secrets before capture. Do not copy keys/tokens/passwords, private environment dumps, screenshots of secrets or credential-bearing archives. Missing evidence is NOT_PROVEN, never a fabricated snapshot.
C5 Reconcile: required for affected state; if orders/exposure could exist, reconcile authoritative orders, positions, fills, protection, risk and durable local journal. Private queries require separate access authorization and approved capability, not this runbook.
C6 Recovery: resolve incident-specific conditions below and hand off operational recovery to D8/approved existing procedure. Recovery is not a destructive reset. Validation returns to READY_DISARMED only; incomplete or failed validation keeps entries blocked.
C7 Re-arm: solely the explicit accountable operator, after verifier evidence, may authorize a separately governed mode transition. LIVE requires environment=LIVE, valid active and locked workflow, valid registry, separate valid live credential reference, live_enabled=true, all readiness gates, matched reconciliation, loaded risk limits and explicit operator arming. Readiness or automatic recovery never auto-arms LIVE. D7 cannot establish A2/A3 or other acceptance proof.
C8 Record: each incident stores detection, severity rationale, containment/exit decision, requested and observed action results, evidence, reconciliation, recovery/verification decision, authority identity and disposition. Close only after recorded safety disposition; a closure does not imply re-arming.

## Deterministic severity model

Choose highest applicable severity. Unknown execution, unprotected position, credential/environment hazard or integrity loss overrides all lower classifications to SEV-1. Otherwise use the class default; do not downgrade until evidence and operator approval are recorded.

| Level | Entry criteria | New-entry policy | Exit-management policy | Notification | Reconciliation | Re-arming |
|---|---|---|---|---|---|---|
| SEV-1 CRITICAL | uncertain execution, unprotected position, security or integrity loss | blocked, latched pending review | C2 only; urgent escalation if unproven | immediate accountable-operator notification; record acknowledgement | full affected exposure/risk/ownership as applicable; no waiver for unknown state | prohibited until C6/C7 and explicit operator approval |
| SEV-2 MAJOR | known bounded operational failure, state not yet unsafe but readiness broken | blocked | C2 only | prompt operator notification; record acknowledgement before recovery | affected state and all possible execution effects | only after C6/C7 |
| SEV-3 DEGRADED | market-only degradation with proven no unsafe exposure | blocked for affected scope; global block if isolation unproven | C2 only | notify operator on detection; record scope | data integrity plus proof of no execution impact, otherwise escalate | only after C6/C7 |
| SEV-4 INFORMATIONAL | observed event with evidence no readiness/control/exposure impact; not an unresolved IR incident | preserve existing authorization; never creates permission | no new authority | auditable log, operator review | record justified not-applicable if no state impact | no arming transition from informational event |

No numerical paging SLA or risk threshold is invented. Operator acknowledgement and evidence are mandatory transition gates.

## Control semantics (policy vocabulary, not executable commands)

All controls below are unavailable for exchange action in the current simulation-only build. A future qualified implementation must be bound to an approved release/profile before use.

| Action | Purpose | When allowed | When required | Must not imply |
|---|---|---|---|---|
| DISARM | revoke authorization for new entries | proven control, authorized scope | readiness/integrity/execution incident containment | orders cancelled, positions flat, protection disabled, or all processes stopped |
| SOFT_STOP | stop accepting new strategy entries while retaining policy-approved management of existing exposure | known reconciled exposure and qualified management path | only when incident policy/operator selects orderly stop | flatten, universal cancellation or exit safety without proof |
| CANCEL_ENTRY_ORDERS | cancel identified pending entry orders | confirmed identities and authorized cancellation path | only when approved containment requires preventing those pending entries | closing positions or removing protective exits |
| CANCEL_ALL_ORDERS | request cancellation of all orders in explicitly authorized scope | operator understands protective-order removal and has a safe exposure plan | only exact approved policy; never a default response | flat positions or safe unprotected residuals; may remove protection |
| PANIC_FLATTEN | request emergency reduction/closure to the policy-defined flat target | correct environment, authoritative exposure, qualified control, exact operator/configured policy | only when that policy requires it; not automatically for every incident | atomic fill, guaranteed success, cancellation completeness or permission to trade |
| EMERGENCY_HALT | prohibit further unsafe automated activity and require human containment | approved halt semantics and known protection consequences | critical condition whose approved policy requires halt | necessarily cancelling, flattening or killing every process |

Documentation of PANIC_FLATTEN does NOT prove CAT-M11 A4 PANIC_FLATTEN_TESTED. No acceptance-test claim is made. If an implementation's semantics differ from this policy vocabulary, mark conflict and block that control pending governance resolution.

## Incident classes

### IR-01 — PUBLIC_MARKET_DATA_STALE_OR_DISCONNECTED

- Detection: Quote age/freshness or public stream fails its configured readiness threshold; abnormal close including 1006.
- Severity: SEV-3; SEV-2 if active exposure depends on stale prices.
- Immediate safety state / new entries: C1; blocked. Exit permission: C2, never unconditional.
- Permitted/required control: DISARM; SOFT_STOP only if independently available and safe. Do not substitute cached prices for current prices.
- Evidence capture: Per-symbol freshness, affected group, quote timestamp, process identity and redacted disconnect logs. C4 applies.
- State to reconcile: Market identity, completed-bar watermarks and freshness; orders/positions/protection if exposure exists.
- Recovery prerequisites: Current per-symbol data validated against configured readiness, no unresolved exposure uncertainty. R3 remains qualified historical PASS_EXACT; a new incident does not revoke it or mandate a reprobe. C6 applies.
- Re-arming prerequisites: C7, independently validated; no automatic re-arm.
- Transition authority: accountable operator with recorded verifier findings; automatic actions are containment only.
- Incident record: C8 and the schema below; include this class, severity basis, control availability, safety outcome and unresolved facts.

### IR-02 — PRIVATE_USER_DATA_STREAM_STALE_OR_DISCONNECTED

- Detection: Private-stream heartbeat/session/account events missing or stale per approved design.
- Severity: SEV-1 when execution/account state uncertain; otherwise SEV-2.
- Immediate safety state / new entries: C1; blocked. Exit permission: C2, never unconditional.
- Permitted/required control: DISARM; escalate uncertain state. No assumed private-stream capability in this simulation-only checkout.
- Evidence capture: Last safe event sequence, session status without tokens, last reconciled snapshot age. C4 applies.
- State to reconcile: Orders, positions, fills, account risk and protection against authoritative exchange state via a separately authorized capability.
- Recovery prerequisites: Authoritative snapshots and event continuity restored and reconciled; do not treat public data health as account-state proof. C6 applies.
- Re-arming prerequisites: C7, independently validated; no automatic re-arm.
- Transition authority: accountable operator with recorded verifier findings; automatic actions are containment only.
- Incident record: C8 and the schema below; include this class, severity basis, control availability, safety outcome and unresolved facts.

### IR-03 — LOCAL_PROCESS_OR_SERVICE_FAILURE

- Detection: Expected launcher/server/relay/identity service missing, exit or failed ownership identity.
- Severity: SEV-2; SEV-1 if exposure/protection uncertain.
- Immediate safety state / new entries: C1; blocked. Exit permission: C2, never unconditional.
- Permitted/required control: DISARM; preserve cohort identity. No ad hoc process kill, relaunch or deletion of PID state.
- Evidence capture: Executable path, creation time, parent/child relationship, listener, mutex/ownership receipt and exit logs. C4 applies.
- State to reconcile: Canonical ownership; data readiness; journal and account/exposure if applicable.
- Recovery prerequisites: Ownership adjudication and separately approved recovery complete; healthy identity and readiness independently verified. C6 applies.
- Re-arming prerequisites: C7, independently validated; no automatic re-arm.
- Transition authority: accountable operator with recorded verifier findings; automatic actions are containment only.
- Incident record: C8 and the schema below; include this class, severity basis, control availability, safety outcome and unresolved facts.

### IR-04 — DUPLICATE_INSTANCE_OR_PROCESS_IDENTITY_CONFLICT

- Detection: Multiple canonical owners, mutex conflict, stale PID reused or identity mismatch.
- Severity: SEV-1.
- Immediate safety state / new entries: C1; blocked. Exit permission: C2, never unconditional.
- Permitted/required control: DISARM and operator escalation; never terminate by bare PID or adopt unknown children.
- Evidence capture: PID plus creation time, executable, command identity, database/port scope and launcher records. C4 applies.
- State to reconcile: Single-instance ownership and any possible duplicate signal/order effects.
- Recovery prerequisites: Exactly one proven owner; unknown cohort adjudicated under approved lifecycle procedure. A venv redirector/base-interpreter pair alone is not a duplicate. C6 applies.
- Re-arming prerequisites: C7, independently validated; no automatic re-arm.
- Transition authority: accountable operator with recorded verifier findings; automatic actions are containment only.
- Incident record: C8 and the schema below; include this class, severity basis, control availability, safety outcome and unresolved facts.

### IR-05 — LOCAL_VS_EXCHANGE_STATE_DRIFT

- Detection: Order/position/fill/protection mismatch or UNKNOWN_RECONCILE_REQUIRED.
- Severity: SEV-1.
- Immediate safety state / new entries: C1; blocked. Exit permission: C2, never unconditional.
- Permitted/required control: DISARM; CANCEL_ENTRY_ORDERS only with validated identities and separately authorized routing.
- Evidence capture: Local journal and independently obtained authoritative order/position/fill snapshots with timestamps. C4 applies.
- State to reconcile: All orders, positions, fills, quantities, reservations, protection and risk.
- Recovery prerequisites: Explicit reconciliation evidence matches; source recovery alone must not clear UNKNOWN state. C6 applies.
- Re-arming prerequisites: C7, independently validated; no automatic re-arm.
- Transition authority: accountable operator with recorded verifier findings; automatic actions are containment only.
- Incident record: C8 and the schema below; include this class, severity basis, control availability, safety outcome and unresolved facts.

### IR-06 — AMBIGUOUS_ORDER_SUBMISSION_OR_RESPONSE

- Detection: Timeout, missing response, unknown acknowledgement or conflicting idempotency state.
- Severity: SEV-1.
- Immediate safety state / new entries: C1; blocked. Exit permission: C2, never unconditional.
- Permitted/required control: DISARM. Query authoritative exchange state before any retry; never blindly resubmit.
- Evidence capture: Client/idempotency identifiers, request digest without secrets, send/response timestamps and durable journal. C4 applies.
- State to reconcile: Whether order exists; fills/cancels/rejects and resulting position/protection.
- Recovery prerequisites: Resolved authoritative disposition and duplicate-prevention evidence; retries require the approved policy and separate authorization. C6 applies.
- Re-arming prerequisites: C7, independently validated; no automatic re-arm.
- Transition authority: accountable operator with recorded verifier findings; automatic actions are containment only.
- Incident record: C8 and the schema below; include this class, severity basis, control availability, safety outcome and unresolved facts.

### IR-07 — PARTIAL_FILL_OR_PROTECTION_FAILURE

- Detection: Fill quantity differs from intended state; protection missing, rejected or wrong-sized.
- Severity: SEV-1 if unprotected; otherwise SEV-2.
- Immediate safety state / new entries: C1; blocked. Exit permission: C2, never unconditional.
- Permitted/required control: DISARM; escalate unprotected residual to IR-13. No guessed full-size replacement.
- Evidence capture: Fill quantities, residual orders, protective-order state and risk snapshot. C4 applies.
- State to reconcile: Executed/residual quantity, fees, position size, protection coverage and reservations.
- Recovery prerequisites: Partial fills accounted for and protection restored/verified under configured policy, with no duplicate residual order. C6 applies.
- Re-arming prerequisites: C7, independently validated; no automatic re-arm.
- Transition authority: accountable operator with recorded verifier findings; automatic actions are containment only.
- Incident record: C8 and the schema below; include this class, severity basis, control availability, safety outcome and unresolved facts.

### IR-08 — RISK_HARD_STOP

- Detection: Daily-loss limit reached OR drawdown limit reached; record the distinct trigger and configured limit reference.
- Severity: SEV-1.
- Immediate safety state / new entries: C1; blocked. Exit permission: C2, never unconditional.
- Permitted/required control: DISARM; maintain latched entry prohibition. Do not reset loss baseline or raise limits to clear the incident.
- Evidence capture: Daily-loss state separately from drawdown/peak state, period, currency, configured threshold and trigger event. C4 applies.
- State to reconcile: PnL/fills, consumed loss, capital/peak state and exposure; no inferred reset.
- Recovery prerequisites: Authorized risk-policy reset conditions and reconciled state proven. D5/D6 remain separate, not closed by this procedure. C6 applies.
- Re-arming prerequisites: C7, independently validated; no automatic re-arm.
- Transition authority: accountable operator with recorded verifier findings; automatic actions are containment only.
- Incident record: C8 and the schema below; include this class, severity basis, control availability, safety outcome and unresolved facts.

### IR-09 — CREDENTIAL_OR_ENVIRONMENT_MISMATCH

- Detection: Wrong environment/key class, missing credential, unexpected permission or secret exposure.
- Severity: SEV-1.
- Immediate safety state / new entries: C1; blocked. Exit permission: C2, never unconditional.
- Permitted/required control: DISARM; quarantine execution authorization. Do not test suspected keys or copy secrets into evidence.
- Evidence capture: Only environment, credential reference identifier and permission class; record exposure location without its contents. C4 applies.
- State to reconcile: Environment/workflow/configuration and any potentially unauthorized activity via separately authorized security review.
- Recovery prerequisites: Credential containment/rotation if separately authorized, environment isolation and readiness proven; never log secret values. C6 applies.
- Re-arming prerequisites: C7, independently validated; no automatic re-arm.
- Transition authority: accountable operator with recorded verifier findings; automatic actions are containment only.
- Incident record: C8 and the schema below; include this class, severity basis, control availability, safety outcome and unresolved facts.

### IR-10 — WORKFLOW_OR_UNIVERSE_INTEGRITY_FAILURE

- Detection: Invalid workflow/registry hash, unknown/excluded instrument, universe/generation mismatch.
- Severity: SEV-1.
- Immediate safety state / new entries: C1; blocked. Exit permission: C2, never unconditional.
- Permitted/required control: DISARM; reject affected intents; do not broaden universe or bypass identity checks.
- Evidence capture: Workflow/version/digest, registry/version/digest, symbol and validation reason. C4 applies.
- State to reconcile: Approved workflow/universe, instrument constraints, intent identities and existing exposure.
- Recovery prerequisites: Locked approved identity restored and all relevant gates verified; no implicit approval of excluded instruments. C6 applies.
- Re-arming prerequisites: C7, independently validated; no automatic re-arm.
- Transition authority: accountable operator with recorded verifier findings; automatic actions are containment only.
- Incident record: C8 and the schema below; include this class, severity basis, control availability, safety outcome and unresolved facts.

### IR-11 — LOCAL_DATABASE_OR_PERSISTENCE_FAILURE

- Detection: Missing/corrupt journal/state, failed durable write or inconsistent replay.
- Severity: SEV-1.
- Immediate safety state / new entries: C1; blocked. Exit permission: C2, never unconditional.
- Permitted/required control: DISARM; preserve originals; no unsafe reconstruction, truncation, deletion or inbox replay.
- Evidence capture: Read error, file metadata/hash, last verified checkpoint and storage failure, without databases containing secrets. C4 applies.
- State to reconcile: Idempotency reservations, submitted state, fills, exposure, risk and protection against authoritative state.
- Recovery prerequisites: Separate recovery procedure establishes trustworthy persistence and explicit reconciliation; unknown state remains blocked. C6 applies.
- Re-arming prerequisites: C7, independently validated; no automatic re-arm.
- Transition authority: accountable operator with recorded verifier findings; automatic actions are containment only.
- Incident record: C8 and the schema below; include this class, severity basis, control availability, safety outcome and unresolved facts.

### IR-12 — ORDER_ROUTER_OR_EXECUTION_PATH_FAILURE

- Detection: Router rejection, unavailable transport, profile mismatch or uncertain execution response.
- Severity: SEV-1.
- Immediate safety state / new entries: C1; blocked. Exit permission: C2, never unconditional.
- Permitted/required control: DISARM; classify ambiguous submission as IR-06. Do not switch endpoint/environment to work around failure.
- Evidence capture: Router/profile/version, request correlation, redacted error and acknowledgement evidence. C4 applies.
- State to reconcile: Orders, fills, positions, protection and duplicate guard.
- Recovery prerequisites: Approved router profile and safe execution capability independently qualified; this document does not enable routing. C6 applies.
- Re-arming prerequisites: C7, independently validated; no automatic re-arm.
- Transition authority: accountable operator with recorded verifier findings; automatic actions are containment only.
- Incident record: C8 and the schema below; include this class, severity basis, control availability, safety outcome and unresolved facts.

### IR-13 — UNPROTECTED_POSITION_CRITICAL_INCIDENT

- Detection: Known or suspected position lacks valid configured protection.
- Severity: SEV-1 highest priority.
- Immediate safety state / new entries: C1; blocked. Exit permission: C2, never unconditional.
- Permitted/required control: Immediate accountable-operator escalation and DISARM. Select protection restoration, reduction or PANIC_FLATTEN only under exact configured/operator policy and proven available controls; do not presume flatten always correct.
- Evidence capture: Position/quantity, missing protection, market/account freshness, available controls and decision rationale. C4 applies.
- State to reconcile: Actual exposure, pending entry/exit orders, partial fills and protection coverage.
- Recovery prerequisites: Verified protection or confirmed authorized flat state, complete reconciliation and independent risk review; uncertain execution capability requires escalation, not improvised commands. C6 applies.
- Re-arming prerequisites: C7, independently validated; no automatic re-arm.
- Transition authority: accountable operator with recorded verifier findings; automatic actions are containment only.
- Incident record: C8 and the schema below; include this class, severity basis, control availability, safety outcome and unresolved facts.

### IR-14 — OPERATOR_REQUESTED_EMERGENCY_STOP

- Detection: Authenticated operator requests immediate containment; record exact requested scope.
- Severity: SEV-1 unless an explicitly non-emergency request is classified separately.
- Immediate safety state / new entries: C1; blocked. Exit permission: C2, never unconditional.
- Permitted/required control: DISARM immediately where available. Distinguish SOFT_STOP, CANCEL_ENTRY_ORDERS, CANCEL_ALL_ORDERS, PANIC_FLATTEN and EMERGENCY_HALT per control table; never infer a more destructive action.
- Evidence capture: Operator identity, authority, requested scope, acknowledged control result and timestamps. C4 applies.
- State to reconcile: All affected orders/positions/fills/protection; stop request is not proof of cancellation or flatness.
- Recovery prerequisites: Requested safety outcome verified, incident reviewed and separately authorized recovery complete. C6 applies.
- Re-arming prerequisites: C7, independently validated; no automatic re-arm.
- Transition authority: accountable operator with recorded verifier findings; automatic actions are containment only.
- Incident record: C8 and the schema below; include this class, severity basis, control availability, safety outcome and unresolved facts.

### IR-15 — POST_CRASH_RECOVERY_INCIDENT

- Detection: Process/host crash or recovered incomplete journal/inbox state.
- Severity: SEV-1 until exposure/ownership known; then SEV-2.
- Immediate safety state / new entries: C1; blocked. Exit permission: C2, never unconditional.
- Permitted/required control: DISARM; preserve prior events; no automatic LIVE resumption and no blind leftover-inbox replay.
- Evidence capture: Crash/boot identity, previous journal/checkpoint, incomplete intents and owned-process cohort. C4 applies.
- State to reconcile: Whether orders were submitted by querying authoritative state before retries; partial fills, protection, quantities and risk.
- Recovery prerequisites: Recovery report covers incomplete signals, duplicate avoidance, partial fills, restored protection and reconciled quantities; hand off to D8, then return READY_DISARMED. C6 applies.
- Re-arming prerequisites: C7, independently validated; no automatic re-arm.
- Transition authority: accountable operator with recorded verifier findings; automatic actions are containment only.
- Incident record: C8 and the schema below; include this class, severity basis, control availability, safety outcome and unresolved facts.

## Incident lifecycle and transition guards

DETECTED -> SAFETY_CONTAINMENT -> EVIDENCE_CAPTURE -> RECONCILIATION -> RECOVERY -> VALIDATION -> READY_DISARMED -> OPERATOR_REARM.

Each arrow is a gate, not an automatic action. DETECTED requires incident ID/owner; containment records effective entry prohibition and exit decision; capture preserves non-secret evidence; reconciliation requires explicit matched state or a documented non-applicability rationale for a no-exposure incident. RECOVERY needs a separately authorized D8/approved procedure. VALIDATION needs verifier identity and passed checks. READY_DISARMED retains entry prohibition. OPERATOR_REARM requires C7 and an audited mode transition. Any failed/unknown prerequisite returns to containment; no loop retries an ambiguous order. No direct RECOVERY-to-armed-LIVE path exists.

Modes are DISABLED, SHADOW, PAPER, TESTNET and LIVE as policy vocabulary. Current implementation is simulation-only; this list does not implement the modes. Every future mode transition must record from/to, actor, time, release/profile and authorization. Do not infer LIVE from market data being called live.

## Deterministic incident-record schema

UTF-8 JSON object, schema_id CAT_M11_D7_INCIDENT_RECORD_R1. Required fields below; unknown values are null with a reason in unknown_fields, never invented. UTC uses RFC3339 Z. IDs are operator-assigned unique strings; no assumed account identity. Arrays retain event order; evidence references contain path, SHA-256, captured_utc and redaction status. Booleans are true/false only when known, otherwise null with reason. closed_utc and rearm_utc remain null until the corresponding authorized event.

| Required field | Type / constraint |
|---|---|
| incident_id | unique nonempty string |
| opened_utc / closed_utc | UTC timestamp / nullable timestamp |
| environment | DISABLED, SHADOW, PAPER, TESTNET, LIVE or UNKNOWN; keep separate execution_environment=SIMULATION_ONLY where applicable |
| workflow_id | exact approved workflow identifier or null |
| severity | SEV-1, SEV-2, SEV-3, SEV-4 |
| incident_class | IR-01 through IR-15; related_classes array for overlap |
| affected_components / affected_symbols_if_any | arrays of exact identifiers; empty symbols when not applicable |
| detection_source | component plus observed event/reference |
| initial_state | object: readiness, arming, exposure certainty, configuration/profile references |
| operator_action / automatic_action | ordered arrays: action, actor/component, authority, request_utc, result_utc, observed_result, evidence reference |
| new_entries_blocked / exit_only_state | nullable booleans; exit_only_state=true only after C2 proven |
| reconciliation_required | nullable boolean; false requires explicit rationale |
| reconciliation_result | NOT_STARTED, NOT_APPLICABLE_JUSTIFIED, PENDING, MATCHED, MISMATCHED, FAILED, UNKNOWN |
| orders_snapshot_reference / positions_snapshot_reference / fills_snapshot_reference | evidence-reference objects or null with reason |
| risk_state_reference / process_identity_reference | evidence-reference objects or null with reason |
| evidence_paths | array of evidence-reference objects; no embedded secrets |
| root_cause_status | UNKNOWN, INVESTIGATING, CONFIRMED with supporting references |
| recovery_action | ordered action records and D8/approved procedure reference |
| rearm_authorized | boolean, default false; true requires C7 evidence and accountable operator identity |
| rearm_utc | nullable UTC timestamp |
| final_disposition | OPEN_CONTAINED, ESCALATED, READY_DISARMED, CLOSED_DISARMED, CLOSED_REARMED |
| owner_id / verifier_id / authorization_reference | concrete identities/references, null blocks corresponding transition |
| unknown_fields / transition_history | reason map / ordered from-to-time-actor-evidence records |

Reject missing required fields, unknown class/severity/disposition, closed time before opened time, rearm time without authorization, or a rearm claim without readiness/reconciliation/risk references. Reject secret-bearing content; reference a sanitized artifact instead. Preserve original incident events and append corrections with actor/time; do not overwrite the history to conceal uncertainty.

## Recovery handoff and gate limits

D7 states what to do upon an incident. D8 owns detailed recovery execution and verification. Handoff includes incident identity, effective safety state, ownership, outstanding/ambiguous orders, fills/protection, persistence integrity, risk, evidence and explicit allowed next action. Startup/recovery must validate configuration/environment, active locked workflow, single-instance lock, exchange time and credentials where separately applicable, account configuration, approved registry, freshness, private stream where implemented, authoritative orders/positions/fills, reconciliation, risk and router profile; only then READY_DISARMED. Incomplete signal handling requires determining prior submission before retry, preventing duplicates, accounting for partial fills, restoring protection, reconciling quantities, preserving events and a recovery report.

D1-D6 and D8 remain separate deliverables. A1-A5 remain separate acceptance items, including A4 panic-flatten testing. No canary value, risk limit, credential, mode capability or test PASS is established here. CAT-M11 remains not lock-eligible; no later milestone is started.

## Document disposition

This file is the exact proposed content for Docs/CAT_M11_D7_INCIDENT_RESPONSE_RUNBOOK.md relative to the active autotrader repository. No destination-specific byte substitution is required. Installation requires verified prepatch SAFE_CODE_ONLY receipt, separately authorized materialization, byte/hash readback and independent D7 validation. Until then M11-D7=NOT_PROVEN.
