# CAT-M11 D8 Recovery Procedures Runbook — R1

Project namespace: WSRTD_R2_CRYPTO_AUTO_TRADER_ONLY  
Workflow: PHASE_1_BINANCE_CRYPTO_USDT_PERPETUAL  
Disposition: frozen proposed documentation; M11-D8 remains NOT_PROVEN until separately authorized preservation, exact materialization and independent validation.  
Canonical future target: Docs/CAT_M11_D8_RECOVERY_PROCEDURES_RUNBOOK.md.

## Policy authority and capability boundary

P1. The operator's CAT-M11 D8 preparation contract dated 2026-09-25 defines the recovery principles, 18 classes and sixteen-field procedure contract. It authorizes preparation only, not operational actions.
P2. Core/AUTHORIZATION.md and Core/README.md bind the current scaffold to simulation-only operation with order routing disabled. Its simulationOrderId is not an exchange client-order identifier. No order/cancel/flatten capability is supplied by this runbook.
P3. Core/README.md describes durable idempotency reservations, strict replay, cumulative-fill checks, immutable terminal-state handling, and explicit reconciliation of UNKNOWN_RECONCILE_REQUIRED. Source recovery alone does not resolve unknown orders. Local authoritative simulation snapshots prove only simulation state.
P4. Core/ACCOUNT_RISK.md and Core/stack/README.md require fresh reconciled inputs, preserve risk state, and restrict optional account access to separately enabled read-only capabilities. Read-only access is not order-routing authority.
P5. CleanRoomR2/stack/README.md describes existing bounded cache repair, receiver rehydration, identity publication, maintenance intent and scope-bound supervision. Its operational descriptions do not authorize changes in this preparation task. Exact current ownership adjudication takes precedence over any shorthand description of stale PID cleanup.
P6. Docs/CAT_M11_D7_INCIDENT_RESPONSE_RUNBOOK.md is the immutable incident-response authority: 32560 bytes, SHA256 7d4a004fb164e9ddeacece36f6820017c34324c33b6abac209c48ac77950cbbd. Its external closure adjudication records M11-D7=PASS. Its historical proposed-content wording is not rewritten by D8.

D7 answers what to do when an incident occurs; D8 answers how to recover to verified safe operation. Import D7's containment outcome and incident ID without replacing its incident classification/control semantics. D8 supplies ordered recovery gates, reconciliation decisions, class procedures, evidence and validation below rather than duplicating D7.

If a required capability, approved release/profile, policy, command binding or authority is unavailable, record UNAVAILABLE and stop that action. Do not improvise command syntax, implement a missing exchange adapter, convert simulation evidence to exchange truth, or emulate a trading emergency control by killing a data service. This is operational policy for separately authorized recovery, not a claim of live capability.

## Common governed execution contract

G0. Before recovery, record exact project/release, environment, workflow, database/port and affected scope, recovery_id, incident_id, operator authorization and concrete owner/verifier identities. Missing identities or ambiguous scope block progression. The accountable operator authorizes; the assigned owner carries out only the authorized steps; the qualified verifier checks evidence. Requests are not proof of effects.
G1. Contain first: keep new entries disabled, preserve verified protection and audit/journal history. If entry inhibition cannot be proven, record the limitation and escalate critically instead of claiming successful DISARM. Never blindly replay leftover signals/inbox state.
G2. Exit management is conditional, not blanket permission: require correct environment, authoritative exposure, qualified control path, governing risk policy and specific authorization. Do not casually cancel protective orders. If safe management cannot be established, record EXIT_PATH_UNPROVEN and urgently escalate. The current simulation-only build cannot execute exchange exits.
G3. Use authoritative orders, positions and recent fills whenever exchange state is relevant. Bind account/environment, source/profile, approved identifiers, observation interval, timestamps and completeness. Record freshness/sequence coherence and pagination/time-window coverage where the approved interface requires it. No single empty/stale/incomplete query proves absence. Public prices cannot prove account state.
G4. Preserve original durable events and idempotency reservations. No blind inbox replay, destructive reset, terminal-state rewrite, guessed fill, invented checkpoint or fabricated snapshot. Reconcile through the supported owning component. Offline journal tools must not write concurrently with the service; any necessary stop/offline repair needs separate authority. Retain the original failure and every correction with actor/time/evidence.
G5. Each repair/mutation, private query, process intervention or credential action requires separately scoped authority and a qualified supported capability. Do not infer permission from reading this document. Recovery failures are terminal for the current attempt: record/escalate and wait for a separately authorized corrective attempt; no automated retry loop is prescribed.
G6. Recovery never arms LIVE. Later arming needs independent proof of environment validity, active locked workflow, approved registry/universe, separate correct credential reference, live_enabled policy, all readiness gates, matched reconciliation, loaded authoritative risk limits and explicit accountable-operator arming. Current simulation-only mode remains orderRoutingEnabled=false. Listing future prerequisites does not implement or qualify them.

## Governed startup/restart sequence

The owner records each stage PASS, FAIL or NOT_APPLICABLE with evidence and rationale; never treats unavailable as pass. Stages are ordered validation gates, not executable commands. No exchange or host action is authorized by this document alone. Ownership/persistence assessment precedes any write; opening persistence at S07 means read-only inspection until S09 proves the writer.

| Stage | Required action and gate |
|---|---|
| S01 | Load only the approved application configuration by identity/reference; do not expose secret values. |
| S02 | Validate schema, required settings and approved configuration digest; conflict blocks. |
| S03 | Determine exact environment and execution profile; simulation is not Testnet or Live. |
| S04 | Load the active governed workflow by identifier/version. |
| S05 | Verify workflow validity, lock/approval and intended scope. |
| S06 | Load and validate deny/exclusion controls; do not broaden eligible instruments. |
| S07 | Inspect required local persistence availability and approved checkpoint read-only. |
| S08 | Validate required migrations/schema/sequence and partial-write state; do not automatically run migrations or reconstruct state. |
| S09 | Enforce canonical single-instance ownership, including scope, creation identity, locks/nonces and children; no writer or restart before this gate. |
| S10 | Validate required timing state and source timestamps against approved tolerance; any time-service adjustment requires separate authority. |
| S11 | Validate credential-reference availability and environment class only where applicable; no secret capture or implied private access. |
| S12 | Validate applicable account configuration through separately authorized capability. |
| S13 | Obtain/validate required instrument metadata with approved public or cached authority and freshness; no guessed constraints. |
| S14 | Validate approved registry/universe identity and exclusions. |
| S15 | Validate exact symbol mapping, quantity/price units and generation semantics. |
| S16 | Restore required market subscriptions through an already approved recovery path; otherwise request separate intervention authority. |
| S17 | Verify per-symbol quote freshness, stream advancement, completed-bar continuity and current receiver hydration. |
| S18 | Restore/verify private event continuity where applicable; public health is not account proof. |
| S19 | Query authoritative orders with approved identifiers and complete relevant scope. |
| S20 | Query authoritative positions for the bound account/environment. |
| S21 | Query recent fills spanning the uncertainty interval, including partial fills. |
| S22 | Reconcile local orders/journal, fills, positions, protection and risk; validate preserved risk limits, loss consumption and drawdown state; validate the intended execution/router profile without enabling routing. |
| S23 | Apply V1-V9; record READY_DISARMED only after all applicable gates pass and operator review is recorded. |

If any later repair invalidates an earlier gate, revalidate the affected dependencies under the authorized recovery attempt; never continue on stale evidence. A successful source reconnect alone does not resolve UNKNOWN state.

## Deterministic recovery lifecycle

FAILED_OR_DEGRADED -> CONTAINED -> STATE_CAPTURED -> AUTHORITATIVE_STATE_QUERIED -> RECONCILIATION -> REPAIR_OR_RESTORE -> VALIDATION -> READY_DISARMED.

A later EXPLICIT_OPERATOR_REARM is a separate authorized transition outside recovery, conditional on G6. RECOVERY_SUCCESS never implies AUTOMATIC_ARM_LIVE.

| Transition | Guard and evidence |
|---|---|
| FAILED_OR_DEGRADED to CONTAINED | Bound incident/scope/owner and observed entry-inhibition outcome; failed containment stays critical and blocks. |
| CONTAINED to STATE_CAPTURED | Original events and safe metadata preserved; no secret capture or destructive cleanup. |
| STATE_CAPTURED to AUTHORITATIVE_STATE_QUERIED | Correct account/environment/identifiers and coherent complete applicable snapshots, or explicit E1/E2 exception. |
| AUTHORITATIVE_STATE_QUERIED to RECONCILIATION | Source authority/currentness proven; unavailable authoritative state blocks. |
| RECONCILIATION to REPAIR_OR_RESTORE | Mismatches classified and approved repair plan/authority bound; no invented state. |
| REPAIR_OR_RESTORE to VALIDATION | Supported repair results acknowledged; repeat explicit affected reconciliation after repair, not merely connectivity. |
| VALIDATION to READY_DISARMED | V1-V9 all applicable checks pass; unresolved_items empty; recorded verifier/operator review; entries remain blocked. |

On a failed/unknown guard record RECOVERY_BLOCKED with the failed stage and remain contained. Preserve evidence and escalate; no automatic re-attempt. Already-valid classes may record REPAIR_NOT_REQUIRED and proceed to validation after matched reconciliation; this is not permission to skip validation.

E1: For a proven market-only incident with no exchange/order/exposure impact, exchange-query and execution reconciliation can be NOT_APPLICABLE only with an evidenced no-exposure/no-impact rationale and verifier approval. Data identity, freshness and continuity reconciliation remain mandatory. Unknown exposure never qualifies.
E2: For a strictly isolated simulation context with evidence of no exchange submission, approved authoritative simulation snapshots/journal may replace exchange queries, explicitly labelled SIMULATION_ONLY. They cannot justify live readiness or exchange absence.
E3: If authoritative sources cannot be reached until an approved non-execution source repair occurs, record the blocked query; perform only separately authorized connectivity/reader repair while contained, then return to AUTHORITATIVE_STATE_QUERIED. Do not rewrite order/risk state or declare reconciliation complete beforehand.
E4: An active governing hard stop or unreleased emergency halt ends in RISK_BLOCKED_DISARMED/HALTED_DISARMED, not READY_DISARMED. Restored observability alone is not safe return to service.

## Ambiguous-order decision table

Never issue a blind retry if delivery is uncertain. Preserve the original request, approved exchange identifiers, idempotency identity, timestamps and journal; simulationOrderId is not an exchange order ID. Determine authoritative disposition first.

| Outcome | Required disposition |
|---|---|
| ORDER_CONFIRMED_PRESENT | Bind the found order to the original intent, reconcile status/fills/residual/protection; do not resubmit it. |
| ORDER_CONFIRMED_ABSENT | Require complete, current authoritative coverage under the approved identifier/history model and resolved local reservations. Absence is not permission to resubmit; any new/retry intent needs separately approved policy, duplicate prevention, risk/readiness and operator authority. No automatic behavior is specified. |
| ORDER_TERMINAL | Reconcile final fills, quantities, cancellations/rejections and risk/protection effects; preserve terminal immutability. Contradictions escalate. |
| ORDER_PARTIALLY_FILLED | Apply RCV-07/08 to actual cumulative fill, residual and protection; never submit the original full quantity as a guessed replacement. |
| ORDER_STATE_AMBIGUOUS | Keep new entries blocked and UNKNOWN_RECONCILE_REQUIRED; preserve evidence and escalate. No retry or inbox replay. |

## Partial-fill and protection decision table

Reconcile order cumulative fill, actual position and pending residual separately using approved units/precision. Missing, wrong-sized, stale and uncertain protection are not verified protection. Concurrent fills require refreshed quantity/coverage evidence; never increase cumulative fills by guessing or clear a terminal contradiction.

| Policy action | Conditions and observed success required |
|---|---|
| RESTORE_OR_VERIFY_PROTECTION | Qualified authorized control and current authoritative exposure; validate correct protective identity, side/quantity/coverage per governing policy and actual acknowledgement/state. Request success alone is insufficient. |
| EXIT_ONLY_MANAGEMENT | G2 fully proven; only explicitly scoped safe management, with authoritative post-action reconciliation. No universal exit permission. |
| OPERATOR_ESCALATION | Required for unprotected/unknown exposure or unavailable safe control; record urgency, owner and acknowledgement/unresolved notification. |
| PANIC_FLATTEN | Only when the exact existing policy and operator authorization select it with qualified available controls; verify actual residual exposure/fills/orders. Never automatic merely because recovery failed. No PANIC_FLATTEN_TESTED claim is made. |
| EMERGENCY_HALT | Only under qualified halt semantics and explicit policy/authority, preserving understood protection consequences. Halt does not prove cancellations, protection or flatness. |

## Recovery class procedures

Every field below is normative. G0-G6, S01-S23, the lifecycle/exception guards and V1-V9 are incorporated explicitly; class-specific steps refine them without granting new execution authority.

### RCV-01 — NORMAL_APPLICATION_RESTART_RECOVERY

- TRIGGER_STATE: Planned restart of an application with known last safe state.
- ENTRY_PRECONDITIONS: Approved maintenance scope, known owner, durable checkpoint and outstanding-work inventory. G0-G6 apply; missing capability/authority blocks action.
- REQUIRED_SAFE_STATE: CONTAINED_DISARMED; record UNAVAILABLE if effective containment cannot be proven and escalate. Preserve existing verified protection.
- NEW_ENTRY_POLICY: Blocked for affected scope; block globally if isolation cannot be proven. Recovery never grants new-entry authority.
- EXIT_MANAGEMENT_POLICY: G2 only: independently proven authorized exit/protection management; otherwise EXIT_PATH_UNPROVEN and critical operator escalation. Current simulation build cannot issue exchange exits.
- AUTHORITATIVE_STATE_SOURCE: Release/configuration identities, canonical ownership, durable journal and applicable authoritative account snapshots.
- EVIDENCE_TO_CAPTURE: R0 recovery record with before/after state, timestamped/digested references to the authoritative sources above, action authority/results, unresolved facts and related D7 incident. No secrets.
- RECOVERY_STEPS: 1. Bind the exact database/port and release to the maintenance authorization. 2. Capture pending work and preserve journal/reservations. 3. Under separate execution authority use the approved owning supervisor lifecycle, never a parallel launcher. 4. Complete S01-S23 and reconciliation before readiness.
- RECONCILIATION_REQUIRED: Yes for every affected order, position, fill, protection, local journal and risk state. Only the explicit E1/E2 exceptions permit documented non-applicability; never for unknown exposure.
- VALIDATION_REQUIRED: Class success criteria plus V1-V9, correct identities and evidence freshness/coherence; named verifier records each PASS/FAIL/NOT_APPLICABLE with reason.
- FAIL_CLOSED_CONDITION: Any unavailable authority/capability, unknown exposure, failed required check, stale/ambiguous authoritative state, unsafe exit path or unresolved contradiction blocks progression; retain evidence and escalate, no automatic retry.
- SUCCESS_CRITERIA: No lost pending work; ownership unique; required sources current and journal replay consistent.
- POST_RECOVERY_STATE: READY_DISARMED only after V1-V9; otherwise remain CONTAINED_DISARMED/RECOVERY_BLOCKED and escalate.
- OPERATOR_ACTION_REQUIRED: Accountable operator binds scope and concrete incident/recovery owner; authorizes each mutating or private-access action separately; qualified verifier records validation; operator reviews final report.
- REARMING_ALLOWED: No as part of this procedure. A later explicit operator transition requires all separately qualified live-readiness gates (G6); current simulation-only routing remains disabled.
- RELATED_D7_INCIDENT_CLASS: IR-03, IR-15

### RCV-02 — POST_CRASH_PROCESS_RECOVERY

- TRIGGER_STATE: Unexpected process/host exit or incomplete startup.
- ENTRY_PRECONDITIONS: Crash identity and previous owner evidence retained; unknown exposure classified critical. G0-G6 apply; missing capability/authority blocks action.
- REQUIRED_SAFE_STATE: CONTAINED_DISARMED; record UNAVAILABLE if effective containment cannot be proven and escalate. Preserve existing verified protection.
- NEW_ENTRY_POLICY: Blocked for affected scope; block globally if isolation cannot be proven. Recovery never grants new-entry authority.
- EXIT_MANAGEMENT_POLICY: G2 only: independently proven authorized exit/protection management; otherwise EXIT_PATH_UNPROVEN and critical operator escalation. Current simulation build cannot issue exchange exits.
- AUTHORITATIVE_STATE_SOURCE: Boot/process creation identity, launcher cohort evidence, durable journal and relevant orders/fills.
- EVIDENCE_TO_CAPTURE: R0 recovery record with before/after state, timestamped/digested references to the authoritative sources above, action authority/results, unresolved facts and related D7 incident. No secrets.
- RECOVERY_STEPS: 1. Capture crash/boot and partial-startup records without clearing them. 2. Apply RCV-16 to adjudicate ownership. 3. Inventory incomplete signals and reservations; determine whether each was submitted using RCV-06. 4. Restore through a separately approved supervisor path only after ownership resolves. 5. Reconcile partial fills, protection and quantities, then run S01-S23.
- RECONCILIATION_REQUIRED: Yes for every affected order, position, fill, protection, local journal and risk state. Only the explicit E1/E2 exceptions permit documented non-applicability; never for unknown exposure.
- VALIDATION_REQUIRED: Class success criteria plus V1-V9, correct identities and evidence freshness/coherence; named verifier records each PASS/FAIL/NOT_APPLICABLE with reason.
- FAIL_CLOSED_CONDITION: Any unavailable authority/capability, unknown exposure, failed required check, stale/ambiguous authoritative state, unsafe exit path or unresolved contradiction blocks progression; retain evidence and escalate, no automatic retry.
- SUCCESS_CRITERIA: No unknown owner or submission; duplicate guard rebuilt and every incomplete intent has an evidenced disposition.
- POST_RECOVERY_STATE: READY_DISARMED only after V1-V9; otherwise remain CONTAINED_DISARMED/RECOVERY_BLOCKED and escalate.
- OPERATOR_ACTION_REQUIRED: Accountable operator binds scope and concrete incident/recovery owner; authorizes each mutating or private-access action separately; qualified verifier records validation; operator reviews final report.
- REARMING_ALLOWED: No as part of this procedure. A later explicit operator transition requires all separately qualified live-readiness gates (G6); current simulation-only routing remains disabled.
- RELATED_D7_INCIDENT_CLASS: IR-03, IR-15

### RCV-03 — PUBLIC_MARKET_DATA_RECOVERY

- TRIGGER_STATE: Disconnect, abnormal close, lost subscription or stale quote/freshness.
- ENTRY_PRECONDITIONS: Bound symbol/group/universe and configured freshness policy; incident containment effective. G0-G6 apply; missing capability/authority blocks action.
- REQUIRED_SAFE_STATE: CONTAINED_DISARMED; record UNAVAILABLE if effective containment cannot be proven and escalate. Preserve existing verified protection.
- NEW_ENTRY_POLICY: Blocked for affected scope; block globally if isolation cannot be proven. Recovery never grants new-entry authority.
- EXIT_MANAGEMENT_POLICY: G2 only: independently proven authorized exit/protection management; otherwise EXIT_PATH_UNPROVEN and critical operator escalation. Current simulation build cannot issue exchange exits.
- AUTHORITATIVE_STATE_SOURCE: Per-symbol market status, identity manifest, stream timestamps, completed-bar watermarks and receiver hydration evidence.
- EVIDENCE_TO_CAPTURE: R0 recovery record with before/after state, timestamped/digested references to the authoritative sources above, action authority/results, unresolved facts and related D7 incident. No secrets.
- RECOVERY_STEPS: 1. Determine affected symbol/group, not merely global socket health. 2. Observe the existing approved reconnect/subscription recovery without launching competing probes. 3. Verify subscriptions, advancing quote times and completed-bar continuity; bounded cache repair is distinct from quote freshness. 4. Verify receiver hydration and universe/data-generation identity. 5. Any manual service intervention needs separate scoped authority.
- RECONCILIATION_REQUIRED: Yes for every affected order, position, fill, protection, local journal and risk state. Only the explicit E1/E2 exceptions permit documented non-applicability; never for unknown exposure.
- VALIDATION_REQUIRED: Class success criteria plus V1-V9, correct identities and evidence freshness/coherence; named verifier records each PASS/FAIL/NOT_APPLICABLE with reason.
- FAIL_CLOSED_CONDITION: Any unavailable authority/capability, unknown exposure, failed required check, stale/ambiguous authoritative state, unsafe exit path or unresolved contradiction blocks progression; retain evidence and escalate, no automatic retry.
- SUCCESS_CRITERIA: Each affected symbol meets configured freshness and identity, current-process hydration and bounded history requirements; no unresolved execution impact.
- POST_RECOVERY_STATE: READY_DISARMED only after V1-V9; otherwise remain CONTAINED_DISARMED/RECOVERY_BLOCKED and escalate.
- OPERATOR_ACTION_REQUIRED: Accountable operator binds scope and concrete incident/recovery owner; authorizes each mutating or private-access action separately; qualified verifier records validation; operator reviews final report.
- REARMING_ALLOWED: No as part of this procedure. A later explicit operator transition requires all separately qualified live-readiness gates (G6); current simulation-only routing remains disabled.
- RELATED_D7_INCIDENT_CLASS: IR-01

### RCV-04 — PRIVATE_USER_DATA_STREAM_RECOVERY

- TRIGGER_STATE: Missing/stale private events, invalid session or event continuity gap.
- ENTRY_PRECONDITIONS: Correct environment and separately authorized read-only account capability; secrets excluded from evidence. G0-G6 apply; missing capability/authority blocks action.
- REQUIRED_SAFE_STATE: CONTAINED_DISARMED; record UNAVAILABLE if effective containment cannot be proven and escalate. Preserve existing verified protection.
- NEW_ENTRY_POLICY: Blocked for affected scope; block globally if isolation cannot be proven. Recovery never grants new-entry authority.
- EXIT_MANAGEMENT_POLICY: G2 only: independently proven authorized exit/protection management; otherwise EXIT_PATH_UNPROVEN and critical operator escalation. Current simulation build cannot issue exchange exits.
- AUTHORITATIVE_STATE_SOURCE: Approved exchange-authoritative account/orders/positions/fills with event sequence/timing; never public price data as account authority.
- EVIDENCE_TO_CAPTURE: R0 recovery record with before/after state, timestamped/digested references to the authoritative sources above, action authority/results, unresolved facts and related D7 incident. No secrets.
- RECOVERY_STEPS: 1. Record last valid event sequence and redacted session status. 2. Restore the approved session only with separate authority and qualified capability. 3. Query authoritative snapshots covering the event gap and reconcile journal, fills, risk and protection. 4. Verify snapshot/event handoff has no unresolved gap or duplicate. 5. Keep UNKNOWN until explicit reconciliation evidence is applied.
- RECONCILIATION_REQUIRED: Yes for every affected order, position, fill, protection, local journal and risk state. Only the explicit E1/E2 exceptions permit documented non-applicability; never for unknown exposure.
- VALIDATION_REQUIRED: Class success criteria plus V1-V9, correct identities and evidence freshness/coherence; named verifier records each PASS/FAIL/NOT_APPLICABLE with reason.
- FAIL_CLOSED_CONDITION: Any unavailable authority/capability, unknown exposure, failed required check, stale/ambiguous authoritative state, unsafe exit path or unresolved contradiction blocks progression; retain evidence and escalate, no automatic retry.
- SUCCESS_CRITERIA: Event continuity and snapshot correspondence proven; no unresolved state and current account sources.
- POST_RECOVERY_STATE: READY_DISARMED only after V1-V9; otherwise remain CONTAINED_DISARMED/RECOVERY_BLOCKED and escalate.
- OPERATOR_ACTION_REQUIRED: Accountable operator binds scope and concrete incident/recovery owner; authorizes each mutating or private-access action separately; qualified verifier records validation; operator reviews final report.
- REARMING_ALLOWED: No as part of this procedure. A later explicit operator transition requires all separately qualified live-readiness gates (G6); current simulation-only routing remains disabled.
- RELATED_D7_INCIDENT_CLASS: IR-02

### RCV-05 — LOCAL_VS_EXCHANGE_STATE_RECONCILIATION

- TRIGGER_STATE: Local order/fill/position/protection or risk mismatch.
- ENTRY_PRECONDITIONS: Approved identifier mapping and coherent authoritative observation window; owned journal writer. G0-G6 apply; missing capability/authority blocks action.
- REQUIRED_SAFE_STATE: CONTAINED_DISARMED; record UNAVAILABLE if effective containment cannot be proven and escalate. Preserve existing verified protection.
- NEW_ENTRY_POLICY: Blocked for affected scope; block globally if isolation cannot be proven. Recovery never grants new-entry authority.
- EXIT_MANAGEMENT_POLICY: G2 only: independently proven authorized exit/protection management; otherwise EXIT_PATH_UNPROVEN and critical operator escalation. Current simulation build cannot issue exchange exits.
- AUTHORITATIVE_STATE_SOURCE: Authoritative open orders, positions, recent fills, protection and account/risk inputs plus local journal.
- EVIDENCE_TO_CAPTURE: R0 recovery record with before/after state, timestamped/digested references to the authoritative sources above, action authority/results, unresolved facts and related D7 incident. No secrets.
- RECOVERY_STEPS: 1. Bind environment/account and identifiers before comparing. 2. Compare order status, cumulative fills, quantities, pending/reserved exposure, protection and risk. 3. Classify missing/conflicting/terminal records without manufacturing state. 4. Apply only supported, authorized explicit reconciliation through the owning component. 5. Requery/revalidate and retain before/after evidence.
- RECONCILIATION_REQUIRED: Yes for every affected order, position, fill, protection, local journal and risk state. Only the explicit E1/E2 exceptions permit documented non-applicability; never for unknown exposure.
- VALIDATION_REQUIRED: Class success criteria plus V1-V9, correct identities and evidence freshness/coherence; named verifier records each PASS/FAIL/NOT_APPLICABLE with reason.
- FAIL_CLOSED_CONDITION: Any unavailable authority/capability, unknown exposure, failed required check, stale/ambiguous authoritative state, unsafe exit path or unresolved contradiction blocks progression; retain evidence and escalate, no automatic retry.
- SUCCESS_CRITERIA: Every relevant object matched or explicitly resolved with authoritative evidence; no unknown, terminal contradiction or unmatched quantity.
- POST_RECOVERY_STATE: READY_DISARMED only after V1-V9; otherwise remain CONTAINED_DISARMED/RECOVERY_BLOCKED and escalate.
- OPERATOR_ACTION_REQUIRED: Accountable operator binds scope and concrete incident/recovery owner; authorizes each mutating or private-access action separately; qualified verifier records validation; operator reviews final report.
- REARMING_ALLOWED: No as part of this procedure. A later explicit operator transition requires all separately qualified live-readiness gates (G6); current simulation-only routing remains disabled.
- RELATED_D7_INCIDENT_CLASS: IR-05

### RCV-06 — AMBIGUOUS_ORDER_SUBMISSION_RECOVERY

- TRIGGER_STATE: Uncertain delivery/acknowledgement, timeout or conflicting request disposition.
- ENTRY_PRECONDITIONS: Original request/idempotency identifiers and journal preserved; no retry issued. G0-G6 apply; missing capability/authority blocks action.
- REQUIRED_SAFE_STATE: CONTAINED_DISARMED; record UNAVAILABLE if effective containment cannot be proven and escalate. Preserve existing verified protection.
- NEW_ENTRY_POLICY: Blocked for affected scope; block globally if isolation cannot be proven. Recovery never grants new-entry authority.
- EXIT_MANAGEMENT_POLICY: G2 only: independently proven authorized exit/protection management; otherwise EXIT_PATH_UNPROVEN and critical operator escalation. Current simulation build cannot issue exchange exits.
- AUTHORITATIVE_STATE_SOURCE: Approved exchange order identifiers and authoritative order/fill/position history; simulationOrderId is not an exchange client-order ID.
- EVIDENCE_TO_CAPTURE: R0 recovery record with before/after state, timestamped/digested references to the authoritative sources above, action authority/results, unresolved facts and related D7 incident. No secrets.
- RECOVERY_STEPS: 1. Freeze replay of the affected intent. 2. Query authoritative state with the approved identifier/time scope. 3. Follow the five-outcome decision table below. 4. Reconcile any fill and protection effects. 5. Record the resolved disposition or remain blocked; do not synthesize an exchange identifier or automatically resubmit.
- RECONCILIATION_REQUIRED: Yes for every affected order, position, fill, protection, local journal and risk state. Only the explicit E1/E2 exceptions permit documented non-applicability; never for unknown exposure.
- VALIDATION_REQUIRED: Class success criteria plus V1-V9, correct identities and evidence freshness/coherence; named verifier records each PASS/FAIL/NOT_APPLICABLE with reason.
- FAIL_CLOSED_CONDITION: Any unavailable authority/capability, unknown exposure, failed required check, stale/ambiguous authoritative state, unsafe exit path or unresolved contradiction blocks progression; retain evidence and escalate, no automatic retry.
- SUCCESS_CRITERIA: Authoritative disposition resolved and recorded with duplicate guard intact; ambiguous or incomplete lookup is not success.
- POST_RECOVERY_STATE: READY_DISARMED only after V1-V9; otherwise remain CONTAINED_DISARMED/RECOVERY_BLOCKED and escalate.
- OPERATOR_ACTION_REQUIRED: Accountable operator binds scope and concrete incident/recovery owner; authorizes each mutating or private-access action separately; qualified verifier records validation; operator reviews final report.
- REARMING_ALLOWED: No as part of this procedure. A later explicit operator transition requires all separately qualified live-readiness gates (G6); current simulation-only routing remains disabled.
- RELATED_D7_INCIDENT_CLASS: IR-06, IR-15

### RCV-07 — PARTIAL_FILL_RECOVERY

- TRIGGER_STATE: Partially filled order, residual mismatch or local position-quantity mismatch.
- ENTRY_PRECONDITIONS: Trusted order/fill identifiers; protective coverage status assessed before repair. G0-G6 apply; missing capability/authority blocks action.
- REQUIRED_SAFE_STATE: CONTAINED_DISARMED; record UNAVAILABLE if effective containment cannot be proven and escalate. Preserve existing verified protection.
- NEW_ENTRY_POLICY: Blocked for affected scope; block globally if isolation cannot be proven. Recovery never grants new-entry authority.
- EXIT_MANAGEMENT_POLICY: G2 only: independently proven authorized exit/protection management; otherwise EXIT_PATH_UNPROVEN and critical operator escalation. Current simulation build cannot issue exchange exits.
- AUTHORITATIVE_STATE_SOURCE: Cumulative authoritative fills, residual open order, actual position, protection and risk reservations.
- EVIDENCE_TO_CAPTURE: R0 recovery record with before/after state, timestamped/digested references to the authoritative sources above, action authority/results, unresolved facts and related D7 incident. No secrets.
- RECOVERY_STEPS: 1. Reconcile cumulative fills and remaining quantity using approved units/precision. 2. Detect duplicate events, decreasing cumulative fills, overfills and contradictory terminal records. 3. Update local state only through the supported owner; preserve prior records. 4. Validate residual orders and protection sized to actual exposure through RCV-08. 5. Reconcile fees/risk/reservations; never submit a guessed full-size replacement.
- RECONCILIATION_REQUIRED: Yes for every affected order, position, fill, protection, local journal and risk state. Only the explicit E1/E2 exceptions permit documented non-applicability; never for unknown exposure.
- VALIDATION_REQUIRED: Class success criteria plus V1-V9, correct identities and evidence freshness/coherence; named verifier records each PASS/FAIL/NOT_APPLICABLE with reason.
- FAIL_CLOSED_CONDITION: Any unavailable authority/capability, unknown exposure, failed required check, stale/ambiguous authoritative state, unsafe exit path or unresolved contradiction blocks progression; retain evidence and escalate, no automatic retry.
- SUCCESS_CRITERIA: Filled plus residual accounting is consistent, position quantity proven and required protection valid; no duplicated residual order.
- POST_RECOVERY_STATE: READY_DISARMED only after V1-V9; otherwise remain CONTAINED_DISARMED/RECOVERY_BLOCKED and escalate.
- OPERATOR_ACTION_REQUIRED: Accountable operator binds scope and concrete incident/recovery owner; authorizes each mutating or private-access action separately; qualified verifier records validation; operator reviews final report.
- REARMING_ALLOWED: No as part of this procedure. A later explicit operator transition requires all separately qualified live-readiness gates (G6); current simulation-only routing remains disabled.
- RELATED_D7_INCIDENT_CLASS: IR-07

### RCV-08 — POSITION_PROTECTION_RECOVERY

- TRIGGER_STATE: Missing, wrong-sized, stale or uncertain stop/protection.
- ENTRY_PRECONDITIONS: Actual position/quantity and environment proven; qualified authorized protection path or escalation. G0-G6 apply; missing capability/authority blocks action.
- REQUIRED_SAFE_STATE: CONTAINED_DISARMED; record UNAVAILABLE if effective containment cannot be proven and escalate. Preserve existing verified protection.
- NEW_ENTRY_POLICY: Blocked for affected scope; block globally if isolation cannot be proven. Recovery never grants new-entry authority.
- EXIT_MANAGEMENT_POLICY: G2 only: independently proven authorized exit/protection management; otherwise EXIT_PATH_UNPROVEN and critical operator escalation. Current simulation build cannot issue exchange exits.
- AUTHORITATIVE_STATE_SOURCE: Authoritative position and protective-order state plus approved risk/protection policy.
- EVIDENCE_TO_CAPTURE: R0 recovery record with before/after state, timestamped/digested references to the authoritative sources above, action authority/results, unresolved facts and related D7 incident. No secrets.
- RECOVERY_STEPS: 1. Classify protection as verified, missing, wrong quantity, stale or unknown. 2. Use the protection decision table; stale/unknown is not protected. 3. Under separate exact authority restore or verify protection against current actual exposure. 4. Observe acknowledgements and resulting authoritative protection, not merely submitted requests. 5. Reconcile concurrent fills and revalidate coverage.
- RECONCILIATION_REQUIRED: Yes for every affected order, position, fill, protection, local journal and risk state. Only the explicit E1/E2 exceptions permit documented non-applicability; never for unknown exposure.
- VALIDATION_REQUIRED: Class success criteria plus V1-V9, correct identities and evidence freshness/coherence; named verifier records each PASS/FAIL/NOT_APPLICABLE with reason.
- FAIL_CLOSED_CONDITION: Any unavailable authority/capability, unknown exposure, failed required check, stale/ambiguous authoritative state, unsafe exit path or unresolved contradiction blocks progression; retain evidence and escalate, no automatic retry.
- SUCCESS_CRITERIA: Required protection is authoritative/current/correctly sized, or a separately authorized flat state is confirmed and reconciled.
- POST_RECOVERY_STATE: READY_DISARMED only after V1-V9; otherwise remain CONTAINED_DISARMED/RECOVERY_BLOCKED and escalate.
- OPERATOR_ACTION_REQUIRED: Accountable operator binds scope and concrete incident/recovery owner; authorizes each mutating or private-access action separately; qualified verifier records validation; operator reviews final report.
- REARMING_ALLOWED: No as part of this procedure. A later explicit operator transition requires all separately qualified live-readiness gates (G6); current simulation-only routing remains disabled.
- RELATED_D7_INCIDENT_CLASS: IR-07, IR-13

### RCV-09 — LOCAL_DATABASE_OR_PERSISTENCE_RECOVERY

- TRIGGER_STATE: Unavailable, missing, inconsistent, corrupt, stale, partially written or unwritable persistence.
- ENTRY_PRECONDITIONS: Preserved original evidence and approved recovery source; ownership and possible exchange effects established. G0-G6 apply; missing capability/authority blocks action.
- REQUIRED_SAFE_STATE: CONTAINED_DISARMED; record UNAVAILABLE if effective containment cannot be proven and escalate. Preserve existing verified protection.
- NEW_ENTRY_POLICY: Blocked for affected scope; block globally if isolation cannot be proven. Recovery never grants new-entry authority.
- EXIT_MANAGEMENT_POLICY: G2 only: independently proven authorized exit/protection management; otherwise EXIT_PATH_UNPROVEN and critical operator escalation. Current simulation build cannot issue exchange exits.
- AUTHORITATIVE_STATE_SOURCE: Validated durable checkpoints/journal sequences plus authoritative exchange state where relevant.
- EVIDENCE_TO_CAPTURE: R0 recovery record with before/after state, timestamped/digested references to the authoritative sources above, action authority/results, unresolved facts and related D7 incident. No secrets.
- RECOVERY_STEPS: 1. Capture non-secret metadata, error, checkpoint and failed-write evidence; do not truncate/rebuild blindly. 2. Bind approved restore source and migration/replay contract; if unavailable stop. 3. Ensure one authorized writer and a separately approved restore plan preserving originals. 4. Validate complete records, sequence, idempotency reservations and terminal immutability. 5. Reconcile the entire uncovered interval, risk and protection. 6. Prove required durability using approved non-live validation before readiness.
- RECONCILIATION_REQUIRED: Yes for every affected order, position, fill, protection, local journal and risk state. Only the explicit E1/E2 exceptions permit documented non-applicability; never for unknown exposure.
- VALIDATION_REQUIRED: Class success criteria plus V1-V9, correct identities and evidence freshness/coherence; named verifier records each PASS/FAIL/NOT_APPLICABLE with reason.
- FAIL_CLOSED_CONDITION: Any unavailable authority/capability, unknown exposure, failed required check, stale/ambiguous authoritative state, unsafe exit path or unresolved contradiction blocks progression; retain evidence and escalate, no automatic retry.
- SUCCESS_CRITERIA: Trustworthy persistence restored, durable recording proven and uncovered state resolved; missing authority or unwritable state blocks success.
- POST_RECOVERY_STATE: READY_DISARMED only after V1-V9; otherwise remain CONTAINED_DISARMED/RECOVERY_BLOCKED and escalate.
- OPERATOR_ACTION_REQUIRED: Accountable operator binds scope and concrete incident/recovery owner; authorizes each mutating or private-access action separately; qualified verifier records validation; operator reviews final report.
- REARMING_ALLOWED: No as part of this procedure. A later explicit operator transition requires all separately qualified live-readiness gates (G6); current simulation-only routing remains disabled.
- RELATED_D7_INCIDENT_CLASS: IR-11, IR-15

### RCV-10 — ORDER_ROUTER_OR_EXECUTION_PATH_RECOVERY

- TRIGGER_STATE: Router/profile/transport unavailable, rejected or uncertain execution path.
- ENTRY_PRECONDITIONS: Approved release/profile/environment; no endpoint switching workaround; ambiguity contained. G0-G6 apply; missing capability/authority blocks action.
- REQUIRED_SAFE_STATE: CONTAINED_DISARMED; record UNAVAILABLE if effective containment cannot be proven and escalate. Preserve existing verified protection.
- NEW_ENTRY_POLICY: Blocked for affected scope; block globally if isolation cannot be proven. Recovery never grants new-entry authority.
- EXIT_MANAGEMENT_POLICY: G2 only: independently proven authorized exit/protection management; otherwise EXIT_PATH_UNPROVEN and critical operator escalation. Current simulation build cannot issue exchange exits.
- AUTHORITATIVE_STATE_SOURCE: Router identity/status, durable request evidence and authoritative order/fill/position state.
- EVIDENCE_TO_CAPTURE: R0 recovery record with before/after state, timestamped/digested references to the authoritative sources above, action authority/results, unresolved facts and related D7 incident. No secrets.
- RECOVERY_STEPS: 1. Confirm profile and environment without enabling routing. 2. Send ambiguous effects to RCV-06. 3. Identify qualified repair under separate authorization; no improvised endpoint or mode change. 4. Validate supported acknowledgement, rejection, duplicate and reconciliation semantics without live orders. 5. Reconcile affected state and return disarmed; current scaffold remains routing-disabled.
- RECONCILIATION_REQUIRED: Yes for every affected order, position, fill, protection, local journal and risk state. Only the explicit E1/E2 exceptions permit documented non-applicability; never for unknown exposure.
- VALIDATION_REQUIRED: Class success criteria plus V1-V9, correct identities and evidence freshness/coherence; named verifier records each PASS/FAIL/NOT_APPLICABLE with reason.
- FAIL_CLOSED_CONDITION: Any unavailable authority/capability, unknown exposure, failed required check, stale/ambiguous authoritative state, unsafe exit path or unresolved contradiction blocks progression; retain evidence and escalate, no automatic retry.
- SUCCESS_CRITERIA: Qualified intended profile restored and affected state resolved; no inferred exchange-routing capability from transport health.
- POST_RECOVERY_STATE: READY_DISARMED only after V1-V9; otherwise remain CONTAINED_DISARMED/RECOVERY_BLOCKED and escalate.
- OPERATOR_ACTION_REQUIRED: Accountable operator binds scope and concrete incident/recovery owner; authorizes each mutating or private-access action separately; qualified verifier records validation; operator reviews final report.
- REARMING_ALLOWED: No as part of this procedure. A later explicit operator transition requires all separately qualified live-readiness gates (G6); current simulation-only routing remains disabled.
- RELATED_D7_INCIDENT_CLASS: IR-12

### RCV-11 — WORKFLOW_OR_UNIVERSE_INTEGRITY_RECOVERY

- TRIGGER_STATE: Workflow, exclusion, registry, universe/generation or symbol mapping mismatch.
- ENTRY_PRECONDITIONS: Approved locked workflow and registry references available; rejected intents preserved. G0-G6 apply; missing capability/authority blocks action.
- REQUIRED_SAFE_STATE: CONTAINED_DISARMED; record UNAVAILABLE if effective containment cannot be proven and escalate. Preserve existing verified protection.
- NEW_ENTRY_POLICY: Blocked for affected scope; block globally if isolation cannot be proven. Recovery never grants new-entry authority.
- EXIT_MANAGEMENT_POLICY: G2 only: independently proven authorized exit/protection management; otherwise EXIT_PATH_UNPROVEN and critical operator escalation. Current simulation build cannot issue exchange exits.
- AUTHORITATIVE_STATE_SOURCE: Governed workflow/deny controls, approved registry/universe digests, instrument metadata and symbol mapping.
- EVIDENCE_TO_CAPTURE: R0 recovery record with before/after state, timestamped/digested references to the authoritative sources above, action authority/results, unresolved facts and related D7 incident. No secrets.
- RECOVERY_STEPS: 1. Compare exact versions/hashes and instrument eligibility. 2. Quarantine affected intents without replay or expanding exclusions/universe. 3. Restore only approved identity/configuration under separate authorization. 4. Verify metadata, mappings, subscriptions and per-symbol generation. 5. Reconcile any existing exposure independently of whether new entries are excluded.
- RECONCILIATION_REQUIRED: Yes for every affected order, position, fill, protection, local journal and risk state. Only the explicit E1/E2 exceptions permit documented non-applicability; never for unknown exposure.
- VALIDATION_REQUIRED: Class success criteria plus V1-V9, correct identities and evidence freshness/coherence; named verifier records each PASS/FAIL/NOT_APPLICABLE with reason.
- FAIL_CLOSED_CONDITION: Any unavailable authority/capability, unknown exposure, failed required check, stale/ambiguous authoritative state, unsafe exit path or unresolved contradiction blocks progression; retain evidence and escalate, no automatic retry.
- SUCCESS_CRITERIA: All identity/mapping checks pass, deny controls retained, no broadened instrument authority or unresolved affected exposure.
- POST_RECOVERY_STATE: READY_DISARMED only after V1-V9; otherwise remain CONTAINED_DISARMED/RECOVERY_BLOCKED and escalate.
- OPERATOR_ACTION_REQUIRED: Accountable operator binds scope and concrete incident/recovery owner; authorizes each mutating or private-access action separately; qualified verifier records validation; operator reviews final report.
- REARMING_ALLOWED: No as part of this procedure. A later explicit operator transition requires all separately qualified live-readiness gates (G6); current simulation-only routing remains disabled.
- RELATED_D7_INCIDENT_CLASS: IR-10

### RCV-12 — CREDENTIAL_OR_ENVIRONMENT_MISMATCH_RECOVERY

- TRIGGER_STATE: Testnet/Live mismatch, wrong/missing credential set, invalid environment or suspected secret exposure.
- ENTRY_PRECONDITIONS: Execution authorization quarantined; accountable security/operator owner assigned. G0-G6 apply; missing capability/authority blocks action.
- REQUIRED_SAFE_STATE: CONTAINED_DISARMED; record UNAVAILABLE if effective containment cannot be proven and escalate. Preserve existing verified protection.
- NEW_ENTRY_POLICY: Blocked for affected scope; block globally if isolation cannot be proven. Recovery never grants new-entry authority.
- EXIT_MANAGEMENT_POLICY: G2 only: independently proven authorized exit/protection management; otherwise EXIT_PATH_UNPROVEN and critical operator escalation. Current simulation build cannot issue exchange exits.
- AUTHORITATIVE_STATE_SOURCE: Approved environment/profile and credential reference/permission metadata, never secret values.
- EVIDENCE_TO_CAPTURE: R0 recovery record with before/after state, timestamped/digested references to the authoritative sources above, action authority/results, unresolved facts and related D7 incident. No secrets.
- RECOVERY_STEPS: 1. Record mismatch category without reading/printing/copying/archiving secret values. 2. Verify intended environment and scoped credential references offline where possible. 3. Escalate suspected exposure; rotation/revocation requires its own authorization. 4. Use separately approved access validation only if required and available. 5. Reconcile potentially affected activity with authorized capability. 6. Keep Testnet and Live distinct and remain disarmed.
- RECONCILIATION_REQUIRED: Yes for every affected order, position, fill, protection, local journal and risk state. Only the explicit E1/E2 exceptions permit documented non-applicability; never for unknown exposure.
- VALIDATION_REQUIRED: Class success criteria plus V1-V9, correct identities and evidence freshness/coherence; named verifier records each PASS/FAIL/NOT_APPLICABLE with reason.
- FAIL_CLOSED_CONDITION: Any unavailable authority/capability, unknown exposure, failed required check, stale/ambiguous authoritative state, unsafe exit path or unresolved contradiction blocks progression; retain evidence and escalate, no automatic retry.
- SUCCESS_CRITERIA: Environment/credential references and permissions correctly isolated, exposure incident resolved and affected state reconciled.
- POST_RECOVERY_STATE: READY_DISARMED only after V1-V9; otherwise remain CONTAINED_DISARMED/RECOVERY_BLOCKED and escalate.
- OPERATOR_ACTION_REQUIRED: Accountable operator binds scope and concrete incident/recovery owner; authorizes each mutating or private-access action separately; qualified verifier records validation; operator reviews final report.
- REARMING_ALLOWED: No as part of this procedure. A later explicit operator transition requires all separately qualified live-readiness gates (G6); current simulation-only routing remains disabled.
- RELATED_D7_INCIDENT_CLASS: IR-09

### RCV-13 — RISK_HARD_STOP_RECOVERY

- TRIGGER_STATE: DAILY_LOSS_HARD_STOP or DRAWDOWN_HARD_STOP latched.
- ENTRY_PRECONDITIONS: Risk evidence and governing limit/period references preserved; accountable review authority. G0-G6 apply; missing capability/authority blocks action.
- REQUIRED_SAFE_STATE: CONTAINED_DISARMED; record UNAVAILABLE if effective containment cannot be proven and escalate. Preserve existing verified protection.
- NEW_ENTRY_POLICY: Blocked for affected scope; block globally if isolation cannot be proven. Recovery never grants new-entry authority.
- EXIT_MANAGEMENT_POLICY: G2 only: independently proven authorized exit/protection management; otherwise EXIT_PATH_UNPROVEN and critical operator escalation. Current simulation build cannot issue exchange exits.
- AUTHORITATIVE_STATE_SOURCE: Persisted daily-loss consumption, drawdown high-water/baseline state, authoritative fills/account risk and locked limits.
- EVIDENCE_TO_CAPTURE: R0 recovery record with before/after state, timestamped/digested references to the authoritative sources above, action authority/results, unresolved facts and related D7 incident. No secrets.
- RECOVERY_STEPS: 1. Record whether daily loss, drawdown or both triggered. 2. Preserve separate consumption/baseline/high-water evidence; no reset or limit increase merely to trade again. 3. Reconcile PnL/fills, quantities and exposure using governing policy. 4. Review authorized period/reset conditions without treating restart as a reset. 5. If stop remains applicable remain RISK_BLOCKED_DISARMED; otherwise require explicit policy/approval and validation before READY_DISARMED.
- RECONCILIATION_REQUIRED: Yes for every affected order, position, fill, protection, local journal and risk state. Only the explicit E1/E2 exceptions permit documented non-applicability; never for unknown exposure.
- VALIDATION_REQUIRED: Class success criteria plus V1-V9, correct identities and evidence freshness/coherence; named verifier records each PASS/FAIL/NOT_APPLICABLE with reason.
- FAIL_CLOSED_CONDITION: Any unavailable authority/capability, unknown exposure, failed required check, stale/ambiguous authoritative state, unsafe exit path or unresolved contradiction blocks progression; retain evidence and escalate, no automatic retry.
- SUCCESS_CRITERIA: Risk truth and limits validated; applicable hard stops remain enforced. Removal of a latch requires independently satisfied governing conditions, never this document alone.
- POST_RECOVERY_STATE: RISK_BLOCKED_DISARMED while a governing hard stop remains; READY_DISARMED only if independently authorized risk conditions are satisfied and V1-V9 pass. Never armed.
- OPERATOR_ACTION_REQUIRED: Accountable operator binds scope and concrete incident/recovery owner; authorizes each mutating or private-access action separately; qualified verifier records validation; operator reviews final report.
- REARMING_ALLOWED: No as part of this procedure. A later explicit operator transition requires all separately qualified live-readiness gates (G6); current simulation-only routing remains disabled.
- RELATED_D7_INCIDENT_CLASS: IR-08

### RCV-14 — UNPROTECTED_POSITION_RECOVERY

- TRIGGER_STATE: Known/suspected exposure lacks proven required protection.
- ENTRY_PRECONDITIONS: Critical escalation active; authoritative exposure sought; entry block maintained. G0-G6 apply; missing capability/authority blocks action.
- REQUIRED_SAFE_STATE: CONTAINED_DISARMED; record UNAVAILABLE if effective containment cannot be proven and escalate. Preserve existing verified protection.
- NEW_ENTRY_POLICY: Blocked for affected scope; block globally if isolation cannot be proven. Recovery never grants new-entry authority.
- EXIT_MANAGEMENT_POLICY: G2 only: independently proven authorized exit/protection management; otherwise EXIT_PATH_UNPROVEN and critical operator escalation. Current simulation build cannot issue exchange exits.
- AUTHORITATIVE_STATE_SOURCE: Current authoritative positions/fills/protective orders, market/account freshness and exact protection policy.
- EVIDENCE_TO_CAPTURE: R0 recovery record with before/after state, timestamped/digested references to the authoritative sources above, action authority/results, unresolved facts and related D7 incident. No secrets.
- RECOVERY_STEPS: 1. Notify accountable operator immediately and record acknowledgement or unresolved escalation. 2. Determine actual exposure and valid protective coverage. 3. Apply the protection decision table; select restoration, exit-only management, flatten or halt only under exact policy/authority and qualified controls. 4. Verify actual effects and partial fills; a requested flatten is not proof of flatness. 5. Reconcile risk and all pending orders/protection before validation.
- RECONCILIATION_REQUIRED: Yes for every affected order, position, fill, protection, local journal and risk state. Only the explicit E1/E2 exceptions permit documented non-applicability; never for unknown exposure.
- VALIDATION_REQUIRED: Class success criteria plus V1-V9, correct identities and evidence freshness/coherence; named verifier records each PASS/FAIL/NOT_APPLICABLE with reason.
- FAIL_CLOSED_CONDITION: Any unavailable authority/capability, unknown exposure, failed required check, stale/ambiguous authoritative state, unsafe exit path or unresolved contradiction blocks progression; retain evidence and escalate, no automatic retry.
- SUCCESS_CRITERIA: Protection proven or authorized flatness confirmed with no residual/unknown exposure; unavailable safe exit capability stays critically escalated.
- POST_RECOVERY_STATE: READY_DISARMED only after V1-V9; otherwise remain CONTAINED_DISARMED/RECOVERY_BLOCKED and escalate.
- OPERATOR_ACTION_REQUIRED: Accountable operator binds scope and concrete incident/recovery owner; authorizes each mutating or private-access action separately; qualified verifier records validation; operator reviews final report.
- REARMING_ALLOWED: No as part of this procedure. A later explicit operator transition requires all separately qualified live-readiness gates (G6); current simulation-only routing remains disabled.
- RELATED_D7_INCIDENT_CLASS: IR-13, IR-07

### RCV-15 — EMERGENCY_HALT_RECOVERY

- TRIGGER_STATE: Emergency halt or operator stop remains active.
- ENTRY_PRECONDITIONS: Original halt intent, scope and safety outcome recorded; no assumption halt flattened positions. G0-G6 apply; missing capability/authority blocks action.
- REQUIRED_SAFE_STATE: CONTAINED_DISARMED; record UNAVAILABLE if effective containment cannot be proven and escalate. Preserve existing verified protection.
- NEW_ENTRY_POLICY: Blocked for affected scope; block globally if isolation cannot be proven. Recovery never grants new-entry authority.
- EXIT_MANAGEMENT_POLICY: G2 only: independently proven authorized exit/protection management; otherwise EXIT_PATH_UNPROVEN and critical operator escalation. Current simulation build cannot issue exchange exits.
- AUTHORITATIVE_STATE_SOURCE: Authorized halt receipt, authoritative orders/positions/protection and local ownership/journal.
- EVIDENCE_TO_CAPTURE: R0 recovery record with before/after state, timestamped/digested references to the authoritative sources above, action authority/results, unresolved facts and related D7 incident. No secrets.
- RECOVERY_STEPS: 1. Confirm what the halt actually did and did not do. 2. Inventory outstanding orders/exposure and protection without cancelling it by default. 3. Resolve underlying D7 incident through relevant RCV classes. 4. Obtain explicit halt-release authorization only after verifier evidence and applicable policy gates. 5. Resume only to READY_DISARMED, never previous arming state.
- RECONCILIATION_REQUIRED: Yes for every affected order, position, fill, protection, local journal and risk state. Only the explicit E1/E2 exceptions permit documented non-applicability; never for unknown exposure.
- VALIDATION_REQUIRED: Class success criteria plus V1-V9, correct identities and evidence freshness/coherence; named verifier records each PASS/FAIL/NOT_APPLICABLE with reason.
- FAIL_CLOSED_CONDITION: Any unavailable authority/capability, unknown exposure, failed required check, stale/ambiguous authoritative state, unsafe exit path or unresolved contradiction blocks progression; retain evidence and escalate, no automatic retry.
- SUCCESS_CRITERIA: Underlying causes resolved and safety effects reconciled; halt release explicitly authorized with entries still disabled.
- POST_RECOVERY_STATE: READY_DISARMED only after V1-V9; otherwise remain CONTAINED_DISARMED/RECOVERY_BLOCKED and escalate.
- OPERATOR_ACTION_REQUIRED: Accountable operator binds scope and concrete incident/recovery owner; authorizes each mutating or private-access action separately; qualified verifier records validation; operator reviews final report.
- REARMING_ALLOWED: No as part of this procedure. A later explicit operator transition requires all separately qualified live-readiness gates (G6); current simulation-only routing remains disabled.
- RELATED_D7_INCIDENT_CLASS: IR-14

### RCV-16 — PROCESS_IDENTITY_OR_DUPLICATE_INSTANCE_RECOVERY

- TRIGGER_STATE: Multiple owners, stale/reused PID, uncertain launcher/cohort or lock mismatch.
- ENTRY_PRECONDITIONS: Read-only identity evidence obtained before any process action; maintenance intent preserved. G0-G6 apply; missing capability/authority blocks action.
- REQUIRED_SAFE_STATE: CONTAINED_DISARMED; record UNAVAILABLE if effective containment cannot be proven and escalate. Preserve existing verified protection.
- NEW_ENTRY_POLICY: Blocked for affected scope; block globally if isolation cannot be proven. Recovery never grants new-entry authority.
- EXIT_MANAGEMENT_POLICY: G2 only: independently proven authorized exit/protection management; otherwise EXIT_PATH_UNPROVEN and critical operator escalation. Current simulation build cannot issue exchange exits.
- AUTHORITATIVE_STATE_SOURCE: Canonical executable/command identity, PID plus creation time, launcher nonce/lock, parent-child relationships and database/port scope.
- EVIDENCE_TO_CAPTURE: R0 recovery record with before/after state, timestamped/digested references to the authoritative sources above, action authority/results, unresolved facts and related D7 incident. No secrets.
- RECOVERY_STEPS: 1. Bind exact service scope and inventory ownership records read-only. 2. Distinguish one venv redirector/base-interpreter pair from duplicate logical services. 3. Validate supervisor/relay/server/identity and dependencies, not bare PID existence. 4. If live ownership is ambiguous refuse takeover, PID cleanup and arbitrary kills. 5. Only separately authorized supported ownership adjudication may recover a proven orphan/stale cohort. 6. Verify exactly one owner and S01-S23 before readiness.
- RECONCILIATION_REQUIRED: Yes for every affected order, position, fill, protection, local journal and risk state. Only the explicit E1/E2 exceptions permit documented non-applicability; never for unknown exposure.
- VALIDATION_REQUIRED: Class success criteria plus V1-V9, correct identities and evidence freshness/coherence; named verifier records each PASS/FAIL/NOT_APPLICABLE with reason.
- FAIL_CLOSED_CONDITION: Any unavailable authority/capability, unknown exposure, failed required check, stale/ambiguous authoritative state, unsafe exit path or unresolved contradiction blocks progression; retain evidence and escalate, no automatic retry.
- SUCCESS_CRITERIA: One canonical proven owner; no unknown live cohort or conflicting listener; original audit and maintenance intent preserved.
- POST_RECOVERY_STATE: READY_DISARMED only after V1-V9; otherwise remain CONTAINED_DISARMED/RECOVERY_BLOCKED and escalate.
- OPERATOR_ACTION_REQUIRED: Accountable operator binds scope and concrete incident/recovery owner; authorizes each mutating or private-access action separately; qualified verifier records validation; operator reviews final report.
- REARMING_ALLOWED: No as part of this procedure. A later explicit operator transition requires all separately qualified live-readiness gates (G6); current simulation-only routing remains disabled.
- RELATED_D7_INCIDENT_CLASS: IR-04, IR-03

### RCV-17 — FAILED_RECONCILIATION_RECOVERY

- TRIGGER_STATE: Reconciliation missing, stale, mismatched, contradictory or failed.
- ENTRY_PRECONDITIONS: Unknown state latched; original failures and evidence preserved. G0-G6 apply; missing capability/authority blocks action.
- REQUIRED_SAFE_STATE: CONTAINED_DISARMED; record UNAVAILABLE if effective containment cannot be proven and escalate. Preserve existing verified protection.
- NEW_ENTRY_POLICY: Blocked for affected scope; block globally if isolation cannot be proven. Recovery never grants new-entry authority.
- EXIT_MANAGEMENT_POLICY: G2 only: independently proven authorized exit/protection management; otherwise EXIT_PATH_UNPROVEN and critical operator escalation. Current simulation build cannot issue exchange exits.
- AUTHORITATIVE_STATE_SOURCE: Approved authoritative orders/positions/fills/protection/risk and local durable journal.
- EVIDENCE_TO_CAPTURE: R0 recovery record with before/after state, timestamped/digested references to the authoritative sources above, action authority/results, unresolved facts and related D7 incident. No secrets.
- RECOVERY_STEPS: 1. Classify failure: source unavailable, stale, identity mismatch, quantity mismatch, sequence gap or terminal contradiction. 2. Repair the source/cause only under scoped authorization; source health alone does not clear UNKNOWN. 3. Acquire coherent authoritative evidence and apply explicit supported reconciliation through the owner. 4. Recheck every affected object. 5. Preserve terminal state; unresolved contradiction requires escalation, not rewriting it.
- RECONCILIATION_REQUIRED: Yes for every affected order, position, fill, protection, local journal and risk state. Only the explicit E1/E2 exceptions permit documented non-applicability; never for unknown exposure.
- VALIDATION_REQUIRED: Class success criteria plus V1-V9, correct identities and evidence freshness/coherence; named verifier records each PASS/FAIL/NOT_APPLICABLE with reason.
- FAIL_CLOSED_CONDITION: Any unavailable authority/capability, unknown exposure, failed required check, stale/ambiguous authoritative state, unsafe exit path or unresolved contradiction blocks progression; retain evidence and escalate, no automatic retry.
- SUCCESS_CRITERIA: Explicit reconciliation resolves all affected unknowns and passes quantity/sequence/risk/protection checks; no waiver based on elapsed time.
- POST_RECOVERY_STATE: READY_DISARMED only after V1-V9; otherwise remain CONTAINED_DISARMED/RECOVERY_BLOCKED and escalate.
- OPERATOR_ACTION_REQUIRED: Accountable operator binds scope and concrete incident/recovery owner; authorizes each mutating or private-access action separately; qualified verifier records validation; operator reviews final report.
- REARMING_ALLOWED: No as part of this procedure. A later explicit operator transition requires all separately qualified live-readiness gates (G6); current simulation-only routing remains disabled.
- RELATED_D7_INCIDENT_CLASS: IR-05, IR-06, IR-11

### RCV-18 — SAFE_RETURN_TO_READY_DISARMED

- TRIGGER_STATE: All selected recovery procedures report candidate completion.
- ENTRY_PRECONDITIONS: Complete recovery record and verifier identity; no unresolved required check or active blocking risk/halt. G0-G6 apply; missing capability/authority blocks action.
- REQUIRED_SAFE_STATE: CONTAINED_DISARMED; record UNAVAILABLE if effective containment cannot be proven and escalate. Preserve existing verified protection.
- NEW_ENTRY_POLICY: Blocked for affected scope; block globally if isolation cannot be proven. Recovery never grants new-entry authority.
- EXIT_MANAGEMENT_POLICY: G2 only: independently proven authorized exit/protection management; otherwise EXIT_PATH_UNPROVEN and critical operator escalation. Current simulation build cannot issue exchange exits.
- AUTHORITATIVE_STATE_SOURCE: Collected validated evidence across configuration, workflow, ownership, data, account/order/protection/risk and approved profile.
- EVIDENCE_TO_CAPTURE: R0 recovery record with before/after state, timestamped/digested references to the authoritative sources above, action authority/results, unresolved facts and related D7 incident. No secrets.
- RECOVERY_STEPS: 1. Evaluate the return-to-service checklist without assuming skipped checks passed. 2. Require justified non-applicability for simulation/no-exposure exceptions. 3. Confirm effective entry prohibition and no automatic mode transition. 4. Record operator review, verifier decision and READY_DISARMED disposition. 5. Treat any later arming as a separately authorized transition, not a continuation of recovery.
- RECONCILIATION_REQUIRED: Yes for every affected order, position, fill, protection, local journal and risk state. Only the explicit E1/E2 exceptions permit documented non-applicability; never for unknown exposure.
- VALIDATION_REQUIRED: Class success criteria plus V1-V9, correct identities and evidence freshness/coherence; named verifier records each PASS/FAIL/NOT_APPLICABLE with reason.
- FAIL_CLOSED_CONDITION: Any unavailable authority/capability, unknown exposure, failed required check, stale/ambiguous authoritative state, unsafe exit path or unresolved contradiction blocks progression; retain evidence and escalate, no automatic retry.
- SUCCESS_CRITERIA: All applicable checks pass and unresolved_items empty; recorded safe operating state retains entry prohibition and routing-disabled simulation invariant.
- POST_RECOVERY_STATE: READY_DISARMED only after V1-V9; otherwise remain CONTAINED_DISARMED/RECOVERY_BLOCKED and escalate.
- OPERATOR_ACTION_REQUIRED: Accountable operator binds scope and concrete incident/recovery owner; authorizes each mutating or private-access action separately; qualified verifier records validation; operator reviews final report.
- REARMING_ALLOWED: No as part of this procedure. A later explicit operator transition requires all separately qualified live-readiness gates (G6); current simulation-only routing remains disabled.
- RELATED_D7_INCIDENT_CLASS: IR-01 through IR-15 as applicable


## Safe return-to-service validation

V1. Configuration and exact environment/profile are valid, active workflow locked and exclusions/registry/universe/symbol mappings correct.
V2. One proven canonical supervisor/service owner exists; dependencies and persistence are validated. A redirector/base-interpreter pair alone is not a duplicate. Bare PID existence is never identity proof.
V3. Required timing, per-symbol data freshness, subscription advancement, bounded completed-bar continuity, receiver hydration and identity are current under approved limits; do not invent thresholds.
V4. Applicable private/event and authoritative account/order/position/fill sources are current, coherent and complete for the affected uncertainty interval; record justified E1/E2 exceptions explicitly.
V5. All affected local/authoritative orders, fills, positions, journal, reservations and risk are explicitly reconciled, no unresolved UNKNOWN, sequence gap or terminal contradiction remains. Restoring source files alone does not clear UNKNOWN.
V6. Actual position quantity and required protection are verified; any authorized flatten has proven residual/flat disposition, not just a request receipt. No unknown/unprotected exposure can pass.
V7. Daily-loss consumption and drawdown/high-water state remain distinct and authoritative; no reset merely to resume, no raised limits. Applicable hard stops or unreleased halt prevent READY_DISARMED.
V8. Intended execution/router profile is qualified for its actual scope, current simulation routing remains disabled, entries are inhibited and no automatic mode transition is pending. Future capabilities are not presumed.
V9. Recovery evidence is complete, unresolved_items is empty, named verifier has recorded results and accountable operator has reviewed the safe disposition. Unknown/missing fields block their dependent transition.

Success records READY_DISARMED only. Explicit later operator re-arm remains separately governed by G6; documenting reconciliation and arming does not qualify A2 or A3.

## Deterministic recovery-record schema (R0)

Schema identifier: CAT_M11_D8_RECOVERY_RECORD_R1. UTF-8 JSON object; all fields below mandatory. Do not fabricate timestamps, actors, hashes or state. Unknown is null plus an unresolved_items reason, never an invented value. UTC timestamps use RFC3339 Z; completed_utc stays null until the attempt ends. Evidence references contain path, SHA256, captured_utc, authority/environment scope and redaction status, not secrets. Preserve original events and append corrections with actor/time rather than rewriting history.

| Required field | Type / validation |
|---|---|
| recovery_id | Unique operator-assigned nonempty string. |
| incident_id_if_applicable | String or null with documented non-applicability. |
| opened_utc | RFC3339 UTC timestamp. |
| completed_utc | Nullable UTC timestamp, never before opened_utc. |
| environment | SIMULATION_ONLY, TESTNET, LIVE or UNKNOWN; exact scope, no inference from live market data. |
| workflow_id | Approved identifier/version reference or null; missing blocks dependent actions. |
| recovery_class | RCV-01 through RCV-18. |
| trigger_state | Observed condition and evidence reference. |
| affected_components | Array of exact component/scope identities. |
| affected_symbols_if_any | Array; empty only if not applicable. |
| pre_recovery_state | Object with containment, ownership, exposure certainty, readiness and risk references. |
| authoritative_state_sources | Array of source/account/environment/profile/interval/completeness references. |
| orders_snapshot_reference | Evidence reference or justified null. |
| positions_snapshot_reference | Evidence reference or justified null. |
| fills_snapshot_reference | Evidence reference or justified null. |
| risk_state_reference | Evidence reference or justified null. |
| protection_state_reference | Evidence reference or justified null. |
| process_identity_reference | Evidence reference or justified null. |
| database_state_reference | Evidence reference or justified null. |
| actions_taken | Ordered array: action, actor, authority reference, before state, requested_utc, observed_utc, actual outcome and evidence. |
| reconciliation_required | Boolean when proven, otherwise null; false requires E1/E2 applicability rationale (E2 still requires simulation reconciliation). |
| reconciliation_result | NOT_STARTED, PENDING, MATCHED, MISMATCHED, FAILED, UNKNOWN or NOT_APPLICABLE_JUSTIFIED; retain scope details. |
| validation_results | Per S/V/class check: PASS, FAIL, NOT_APPLICABLE or UNKNOWN with verifier identity and evidence/rationale. |
| unresolved_items | Ordered array of missing/conflicting facts and owner; empty required for READY_DISARMED. |
| fail_closed_reason | Nonempty string on blocking failure; null only if not blocked. |
| post_recovery_state | CONTAINED_DISARMED, RECOVERY_BLOCKED, RISK_BLOCKED_DISARMED, HALTED_DISARMED or READY_DISARMED. |
| operator_review_required | true; record actual review separately, never infer completion. |
| rearm_permitted | false for this recovery record; later authorization belongs in a separate governed mode-transition record. |
| final_disposition | OPEN_CONTAINED, BLOCKED_ESCALATED, RESTORED_BUT_DISARMED_BLOCKED or COMPLETE_READY_DISARMED. |
| evidence_paths | Array of sanitized evidence references with digests. |
| owner_id / verifier_id / operator_id | Concrete recorded identities; missing blocks dependent gates. |
| authorization_reference / operator_review_reference | Exact authorization/review evidence references or null while pending. |
| transition_history | Ordered from/to/time/actor/evidence records, including justified exceptions. |

Reject missing fields, duplicate JSON keys, unknown class/disposition, inconsistent timestamps, unauthorized transition, READY_DISARMED with unresolved/failed checks, or rearm_permitted=true. Validate nullable references against applicability; null cannot count as a passed required check. Do not store secret values, environment dumps, key material or secret-bearing archives.

## Historical evidence and gate disposition

R3_FINAL_ADJUDICATION=PASS_EXACT  
HISTORICAL_1006_STATUS=CLEARED_BY_R3  
R3_REPROBE_REQUIRED=false

A new transport incident is handled on current evidence; routine recovery does not rerun R3 or reopen its historical classification. Prior startup convergence and the 180-second soak remain SUPPORTING_OPERATIONAL_EVIDENCE, not formal CAT-M11 gate proof; no rerun is instructed.

M11-D7=PASS is preserved without altering its file. M11-D8=NOT_PROVEN during preparation. D1-D6 and A1-A5 remain NOT_PROVEN, including live credential separation, preflight, interlocks, canary limits, daily-loss and drawdown gates, environment isolation, required reconciliation, explicit arming and panic-flatten acceptance. D8 documentation must not promote them. FORMAL_CAT_M11_GAPS_REMAINING=12; CAT_M11_LOCK_ELIGIBILITY=NOT_ELIGIBLE; CAT_M12_STARTED=false.

This proposed document contains no live qualification or authority to perform a recovery. Later exact installation requires a new pre-D8 SAFE_CODE_ONLY receipt preserving the inherited 193 source files plus D7, then separately authorized byte-for-byte materialization and independent D8 validation. No operational commands, private access, tests, runtime restarts or source changes are performed by preparation.
