# Core auto-trader scaffold - simulation only

This subtree is the first bounded attachment between the existing CleanRoomR2 WSRTD data path and the Architecture R3.1 trading-engine shape.

## Safety boundary

This code cannot submit an exchange order. It contains a disabled-by-default Binance USD-M read-only account reconciler for risk/position state, but no order, cancel, leverage, margin-mode, transfer, Testnet-routing, or production-routing operation. Credentials are read only from environment variables when read-only reconciliation is explicitly enabled. The terminal simulated path is `OrderRoutingDisabled`.

## Component map

- `common/` - bounded contracts shared by signal, data and execution simulation.
- `trade_plugin/` - `SignalIntentBuilder` scaffold for the future Trade.dll boundary.
- `wsrtd/` - adapter from observable R2 cache/freshness state to `DataStatus`.
- `execution/` - fail-closed intent validation, account risk gate, deterministic simulation sizing, instrument filters, durable journal, and disabled order manager.
- `account/` - read-only private-account and income-history boundaries plus stale/missing fail-closed risk, position and realized-PnL providers.
- `instrument/` - versioned symbol constraints provider for quantity step, min/max quantity and notional filters.
- `order_state/` - local authoritative simulation order-state snapshot source used for startup reconciliation tests/runtime simulation.
- `schemas/` - JSON Schema Draft 2020-12 contracts for the signal, status, risk, position, instrument, order, FSM and reconciliation messages.
- `tests/` - deterministic simulation-only checks.

## WSRTD R2 integration status

The R2 DLL ABI is left unchanged. A compatibility bridge now runs beside the existing WSRTD stack:

- `CleanRoomR2/stack/universe_identity.v1.json` is the tracked bootstrap-universe identity.
- `identity_bridge.py` verifies that manifest against the exact ordered `bootstrap_symbols.tls` SHA-256.
- It reads the already-persisted completed-1m recovery watermark for each symbol.
- It publishes `runtime/data_identity.v1.json` atomically.
- For this compatibility layer, `dataGeneration` is exactly the completed 1-minute open timestamp in milliseconds and is explicitly labelled `WSRTD_R2_COMPLETED_M1_OPEN_MS`.
- `SignalIntentBuilder.bind_data_identity()` copies the verified `universeId`, `universeVersion`, and `dataGeneration` into the intent.
- `IntentValidator` rejects universe-ID/version and generation mismatches.

If the manifest fails verification, a symbol has no completed-1m watermark, or the identity snapshot is unavailable, the adapter remains fail-closed with `IdentityUnavailable`.

This is a compatibility identity for the current R2 data path, not a claim that the existing DLL internally implements the later Architecture R3.1 publication-generation mechanism.

## Live WSRTD -> execution simulation path

The stack now publishes two local runtime layers:

- `runtime/market_status.v1.json` from the Binance/WSRTD server, containing socket/data freshness, receiver presence and whether the current process has completed the bounded 1500-M1 + 300-EOD full receiver hydration for each symbol.
- `runtime/autotrader_status/<SYMBOL>.json` from `identity_bridge.py`, combining market readiness with the verified universe identity and completed-1m data generation.

`LiveStatusProvider` reads the per-symbol flat status file. The execution pipe host uses this provider by default and fails closed when the file is missing, stale, malformed, not live/fresh, not hydrated, or has unavailable identity.

The runtime `cacheReady` flag is a compatibility readiness signal derived from an observed successful full bounded receiver hydration in the current WSRTD server process. It is not a direct DLL-memory cache inspection.

The live host now consumes a separate reconciled `AccountRiskSnapshot.v1` file plus optional per-symbol `PositionSnapshot.v1` files from the same read-only account reconciliation cycle. Missing, stale, malformed, or unreconciled account state fails closed before sizing. Scale-In and Scale-Out additionally require reconciled symbol position state; a flat, hedged, side-conflicting, missing, or stale position fails closed. The `--synthetic` mode still uses deterministic state strictly for transport tests. Order routing remains disabled.

## Durable execution journal and replay guard

The execution host now writes an append-only `ExecutionJournalEvent.v1` JSONL journal. Before a new idempotency key is accepted, an `IDEMPOTENCY_RESERVATION` record is flushed durably. The eventual simulation result is appended as a `SIMULATION_DECISION`.

On host startup the journal is replayed to rebuild the in-memory duplicate guard. A previously reserved key is rejected after restart as `DUPLICATE_REQUEST`. Malformed journal replay is a startup failure rather than silently discarding ambiguous state.

Windows appends each journal record through a write-only append descriptor and calls `_commit` before closing the descriptor. The journal path defaults to:

```text
Core/runtime/execution_journal.v1.jsonl
```

and can be changed with `--journal` or `ASTU_EXECUTION_JOURNAL`.

Windows live integration smoke:

```cmd
Core\tools\run_pipe_live_smoke.cmd
```

This launches the execution host in live-WSRTD-status mode, builds the signal identity from the same runtime DataStatus, sends it over the Named Pipe, and expects `ORDER_ROUTING_DISABLED`.

## Build and test

From an x64 Visual Studio Developer Command Prompt or another CMake C++20 environment:

```text
cmake -S Core -B build/core
cmake --build build/core --config Release
ctest --test-dir build/core -C Release --output-on-failure
```

Run the synthetic simulator:

```text
build/core/Release/astu_execution_sim.exe
```

The expected terminal message contains `SIMULATION_ONLY` and `order routing ... disabled`.

## Supervised simulation runtime

`Core/stack/autotrader_sim_launcher.py` now supervises the simulation execution host and optional read-only account reconciler. The default risk mode is `disabled`, which remains fail-closed. Fixture mode is available for CI/development, while `readonly` requires the explicit read-only environment gate and credentials.

This keeps the runtime operational shape separate from WSRTD while preserving the component boundary: WSRTD publishes market/data identity, AstuTrade emits SignalIntent, and the execution host owns validation/risk/simulation/journal state.

## Deterministic instrument filters and sizing

The strict simulation path now accepts `InstrumentConstraints.v1` and applies deterministic pre-order validation without creating an order.

The sizing rule for this simulation increment is explicit and reproducible:

1. start with 0.1% of reconciled `riskCapital` as the synthetic notional budget;
2. cap new-exposure budget by remaining `maxGrossNotional - grossNotional` headroom;
3. cap by an instrument `maxNotional` when one is supplied;
4. convert budget to raw quantity using the SignalIntent trigger price;
5. floor quantity to the instrument `quantityStep`;
6. reject zero quantity or violations of min/max quantity or min/max notional;
7. return both `simulatedQuantity` and `simulatedNotional`.

The price tick is carried and validated as instrument metadata but is not applied to `triggerPrice`, because `triggerPrice` is signal/reference data rather than a submitted limit-order price.

Missing, stale, malformed or symbol-mismatched instrument constraints fail closed as `INSTRUMENT_UNAVAILABLE`. Filter violations return `FILTER_REJECTED`, and non-executable sizing returns `SIZING_REJECTED`.

The existing execution transport can opt into an instrument provider; legacy transport tests remain on the prior synthetic sizing path until a public exchange-info publisher is wired to the runtime.

## Reconciled position-state semantics

The read-only Binance account reconciler now publishes one `PositionSnapshot.v1` per selected bootstrap symbol. The snapshot is derived from the same account response as `AccountRiskSnapshot.v1` and records `FLAT`, `LONG`, `SHORT`, `HEDGED`, or fail-closed `UNKNOWN` state.

For the current simulation semantics:

- `SCALE_IN` requires a reconciled, non-flat position on the same side as the SignalIntent.
- `SCALE_OUT` requires the same and caps simulated quantity at the reconciled absolute position quantity.
- hedged/ambiguous position state returns `POSITION_CONFLICT`;
- missing/stale/unreconciled position state returns `POSITION_UNAVAILABLE`;
- ordinary BUY/SELL signals retain the existing validation path and do not invent a position-side interpretation beyond the SignalIntent fields.

This deliberately avoids guessing broader BUY/SELL position semantics that are not yet locked into the compatibility contract.

## Simulation order intent and persistent FSM

The execution host now creates a deterministic simulation-only order identity for each accepted request/idempotency identity and returns it as `simulationOrderId`. The ID is stable across retry timing/data-generation changes when the request ID, idempotency key, signal identity, strategy, symbol, action and side remain the same.

The ID is explicitly a **simulation order ID**, not a production Binance client-order ID. It must not be treated as an exchange-submission credential or live-order identifier.

After successful sizing, the journal persists `SimulationOrderIntent.v1` with:

- simulation order ID;
- request/idempotency/signal identity;
- symbol, action and side;
- normalized simulated quantity;
- SignalIntent trigger/reference price;
- simulated notional;
- `simulationOnly=true`;
- `orderRoutingEnabled=false`;
- `exchangeSubmissionAttempted=false`.

The persistent order FSM uses the architecture state vocabulary:

`INTENT_RECEIVED -> VALIDATING -> RISK_APPROVED -> SIZING -> SUBMITTING -> ACKNOWLEDGED -> WORKING -> PARTIAL/FILLED/CANCELED/REJECTED`

plus `UNKNOWN_RECONCILE_REQUIRED`.

The current simulation runtime automatically advances only through:

`INTENT_RECEIVED -> VALIDATING -> RISK_APPROVED -> SIZING`

for an accepted simulation result. It deliberately stops at `SIZING` because order routing is disabled. No normal simulation path automatically enters `SUBMITTING`, `ACKNOWLEDGED`, or `WORKING`.

Validation/risk/filter failures can move to `REJECTED` through validated failure transitions. Every transition is durably journaled with a monotonically increasing per-order transition sequence, exact from/to states, and explicit no-exchange-submission flags.

At startup the journal reconstructs the latest state of every simulation order and validates transition sequence continuity and legal state transitions. A malformed, gapped, contradictory, or non-simulation transition fails startup closed instead of being silently ignored.

The Windows restart acceptance test additionally proves that:

- an accepted simulation remains reconstructed at `SIZING`;
- the normalized simulation order intent survives restart;
- the same idempotency key is rejected after restart as `DUPLICATE_REQUEST`;
- the deterministic `simulationOrderId` remains stable on that retry;
- no `SUBMITTING` transition or exchange-submission flag appears.

## Simulation reconciliation around UNKNOWN_RECONCILE_REQUIRED

The simulation journal now accepts explicit reconciliation evidence for a previously normalized simulation order. This is deliberately separate from exchange submission.

Supported simulation reconciliation event types are:

- `MARK_UNKNOWN` -> `UNKNOWN_RECONCILE_REQUIRED`
- `ACKNOWLEDGED` -> `ACKNOWLEDGED`
- `WORKING` -> `WORKING`
- `PARTIAL_FILL` -> `PARTIAL`
- `FILLED` -> `FILLED`
- `CANCELED` -> `CANCELED`
- `REJECTED` -> `REJECTED`

Each `SIMULATION_RECONCILIATION_EVENT` is a single durable state transition with both a per-order transition sequence and a reconciliation-event sequence. Replay verifies the from-state, target state, reconciliation type, order quantity, event sequence, transition sequence, simulation-only marker, and no-exchange-submission marker.

Fill reconciliation is cumulative and monotonic. A partial fill must be greater than zero and strictly below the normalized simulation order quantity. A filled event must reconcile exactly to the normalized order quantity. Decreasing fills, overfills, duplicate event IDs, invalid state jumps, and terminal-state mutation fail closed.

The running execution service now owns reconciliation journal mutation through a second simulation-only local Named Pipe:

`\\.\pipe\AstuExecutionReconcileSim.v1`

It uses the same bounded 64 KiB frame envelope, CRC32C validation, local Windows Named Pipe transport, and explicit request/response schemas as the Trade-to-Execution simulation path. `SimulationReconciliationRequest.v1` carries the event identity, simulation order ID, reconciliation type, cumulative fill and detail. `SimulationReconciliationResult.v1` returns accepted/rejected state, current cumulative fill and durable transition/reconciliation counts.

This removes concurrent external journal writing from the normal running-service workflow: reconciliation requests are applied inside `Execution.exe` against the same in-memory journal/FSM state protected by the journal mutex.

`astu_sim_reconcile` remains available only as an **offline recovery/test utility**. Stop the execution host before using that utility directly against its journal. The normal live simulation acceptance uses the reconciliation Named Pipe instead.

The live reconciliation acceptance follows this path while the execution host remains running:

`SIZING -> UNKNOWN_RECONCILE_REQUIRED -> ACKNOWLEDGED -> WORKING -> PARTIAL -> FILLED`

It rejects a post-`FILLED` cancel attempt, verifies the live `ExecutionStatus.v1` transition/reconciliation counters, restarts the execution host, and verifies reconstruction of the same final state. Both the live and offline acceptance paths assert that no `SUBMITTING` transition or exchange-submission attempt occurred.

## Authoritative simulated order-state startup reconciliation

The execution host can now opt into a file-backed authoritative simulation order-state source with `--order-snapshot-dir` (or `ASTU_ORDER_SNAPSHOT_DIR`). Each tracked normalized simulation order is compared at startup against `AuthoritativeSimulationOrderSnapshot.v1`.

Startup behavior is deliberately fail-closed:

- exact state + cumulative-fill agreement is counted as matched;
- missing, stale, malformed, non-ready, state-mismatched, or fill-mismatched snapshots for a non-terminal order move the journal state to `UNKNOWN_RECONCILE_REQUIRED`;
- an order already in `UNKNOWN_RECONCILE_REQUIRED` remains unresolved until explicit reconciliation evidence arrives through the reconciliation pipe;
- a terminal journal state that disagrees with the authoritative snapshot aborts startup rather than mutating the terminal state;
- rejected pre-order validation attempts are not treated as authoritative exchange/order-state objects because no normalized `SimulationOrderIntent.v1` exists for them.

The local simulation snapshot source is:

`Core/order_state/simulated_order_state_source.py`

It only publishes local JSON snapshots and contains no network, credential, signing, or order-submission behavior.

The Windows startup acceptance proves:

`SIZING + authoritative SIZING -> matched`

then:

`SIZING + authoritative WORKING -> UNKNOWN_RECONCILE_REQUIRED`

The order remains unresolved until `WORKING` evidence is supplied through `\\.\pipe\AstuExecutionReconcileSim.v1`. After restart with a matching WORKING snapshot, startup returns to a fully matched state. The test also verifies that no `SUBMITTING` transition or exchange-submission attempt appears.

`ExecutionStatus.v1` now exposes the startup snapshot provider plus tracked, matched, marked-unknown, and unresolved counts.

## Periodic in-process authoritative reconciliation

When an authoritative simulation order snapshot directory is configured, the execution host now runs a bounded periodic reconciliation sweep in-process. The interval defaults to 2000 ms and is configurable with `--order-reconcile-interval-ms` or `ASTU_ORDER_RECONCILE_INTERVAL_MS`.

Each sweep examines normalized non-terminal simulation orders only:

- exact journal state + cumulative-fill agreement is reported as matched;
- stale, missing, malformed or non-ready source state is surfaced through `runtimeOrderSourceUnavailable`;
- any non-terminal state/fill disagreement moves the order to `UNKNOWN_RECONCILE_REQUIRED`;
- an already-unknown order remains unresolved even if the source later becomes healthy;
- resolution still requires explicit reconciliation evidence through `\\.\pipe\AstuExecutionReconcileSim.v1`;
- terminal orders are skipped by the periodic sweep and are never rewritten.

`ExecutionStatus.v1` now reports whether runtime reconciliation is enabled, last sweep time, sweep count, non-terminal orders examined, matches, orders marked unknown, unresolved orders, unavailable-source count, terminal orders skipped, concurrent state changes and sweep errors.

The Windows runtime acceptance proves this sequence while `Execution.exe` remains running:

`SIZING + authoritative SIZING -> MATCHED`

`SIZING + authoritative WORKING -> UNKNOWN_RECONCILE_REQUIRED`

`UNKNOWN + explicit WORKING evidence -> WORKING / MATCHED`

`WORKING + missing authoritative snapshot -> UNKNOWN_RECONCILE_REQUIRED`

Restoring the snapshot alone does not clear UNKNOWN; a second explicit evidence event is required before the order becomes matched again.

No `SUBMITTING` transition, exchange credential, private order request or exchange-submission path is introduced.

## Projected exposure reservations

Accepted exposure-increasing simulation orders now create a durable projected-risk reservation before the response path completes.

The reservation policy follows the current architecture semantics where `BUY` and `SCALE_IN` increase exposure:

- every accepted BUY/SCALE_IN reserves the full normalized simulated notional;
- BUY additionally reserves one projected open-position slot;
- SCALE_IN reserves gross-notional headroom but not a new position slot because reconciled position state is already required;
- SELL and SCALE_OUT do not create projected exposure reservations.

Before every later risk evaluation, the current reconciled `AccountRiskSnapshot.v1` is overlaid with all active reservations. This means concurrent/sequential accepted intents cannot independently reuse the same gross-notional or open-position headroom before account/order reconciliation catches up.

The legacy synthetic sizing path now also caps its notional budget by remaining projected `maxGrossNotional - grossNotional` headroom and fails closed when no positive quantity remains.

Reservation evidence is persisted in the execution journal as:

- `EXPOSURE_RESERVATION_CREATED`
- `EXPOSURE_RESERVATION_RELEASED`

Active reservations are reconstructed on restart. For compatibility with journals produced immediately before this increment, a non-terminal exposure-increasing `SimulationOrderIntent.v1` that has no explicit reservation event is conservatively reconstructed in memory so projected headroom is not silently lost.

Reservations remain active through `UNKNOWN_RECONCILE_REQUIRED`, `ACKNOWLEDGED`, `WORKING`, and `PARTIAL`. They are released only when the simulated order reaches terminal `FILLED`, `CANCELED`, or `REJECTED` state. Partial fills deliberately keep the full reservation as a conservative policy.

`ExecutionStatus.v1` now exposes:

- recovered active reservations at startup;
- current active reservation count;
- total reserved gross notional;
- reserved position slots;
- create/release counts;
- implicit terminal releases recovered after an interrupted journal sequence;
- compatibility reservations reconstructed from pre-reservation journal history.

The Windows acceptance uses a synthetic account with only 10 notional units of gross headroom. The first BUY reserves the full 10, the second independent BUY is rejected as `RISK_BLOCKED`, restart reconstructs the reservation and still blocks new exposure, terminal FILLED reconciliation releases it, and a later BUY can use the restored headroom. The journal assertion continues to require `exchangeSubmissionAttempted=false` and no `SUBMITTING` transition.

## Pending entry/scale-in and per-symbol projected-risk limits

The reservation layer now feeds two additional execution-local limits:

- `maxPendingEntryScaleInReservations` limits the number of active BUY/SCALE_IN projected exposure reservations;
- `maxSymbolNotional` limits reconciled per-symbol position notional plus active reservations for that same symbol plus the newly sized simulated intent.

Both limits default to `0` (disabled) because the architecture defines the limit categories but does not prescribe numeric policy values. They can be configured with:

```text
--max-pending-entry-scale-in-reservations N
--max-symbol-notional VALUE
```

or the equivalent environment variables:

```text
ASTU_MAX_PENDING_ENTRY_SCALE_IN_RESERVATIONS
ASTU_MAX_SYMBOL_NOTIONAL
```

The pending-reservation limit is evaluated before another exposure-increasing intent is sized. Because the current simulation reservation set contains only BUY/SCALE_IN orders, its active count is the projected pending-entry/scale-in count.

The per-symbol limit is evaluated from two sources together:

1. reconciled symbol position notional from `PositionSnapshot.v1`;
2. active exposure reservations already held for the same symbol.

Sizing then caps the new simulated order by remaining symbol headroom. If the configured per-symbol limit requires position state and the symbol snapshot is missing, stale or unreconciled, the request fails closed as `POSITION_UNAVAILABLE`.

For synthetic transport/risk tests, the reconciled starting symbol notional is explicitly zero. Live/fixture execution uses the file-backed reconciled position provider.

`ExecutionStatus.v1` now publishes the configured pending-reservation and per-symbol-notional limits alongside current reservation counts and reserved gross notional.

The deterministic acceptance coverage proves:

- one active reservation with a configured maximum of one blocks another BUY even when global gross headroom remains;
- that pending limit remains effective after restart because the reservation is reconstructed;
- terminal reconciliation releases the reservation and permits a later entry;
- BTC can consume its configured per-symbol headroom while an independent ETH reservation can still be accepted;
- missing reconciled symbol exposure fails closed when a per-symbol limit is enabled.

No exchange order submission, cancel, leverage/margin mutation or `SUBMITTING` transition is introduced.

## Available-balance / margin reservations

Projected exposure reservations now also reserve an execution-local available-balance budget.

Two configurable settings control this simulation policy:

```text
--minimum-available-balance-reserve VALUE
--simulation-margin-reservation-rate RATE
```

with equivalent environment variables:

```text
ASTU_MINIMUM_AVAILABLE_BALANCE_RESERVE
ASTU_SIMULATION_MARGIN_RESERVATION_RATE
```

Both default to `0`. The architecture requires margin/reserve checks and a minimum available-balance reserve, but it does not prescribe a universal margin-per-notional formula, so this compatibility layer does not invent exchange leverage policy. When enabled, `simulationMarginReservationRate` is an explicit execution-local simulation policy: an accepted exposure-increasing order reserves

`simulatedNotional * simulationMarginReservationRate`

from the reconciled available balance.

A positive minimum available-balance reserve requires a positive simulation margin reservation rate. This prevents a configuration that claims to protect projected free balance without defining how new simulated notional consumes that balance.

Before each later risk evaluation, active reservations are subtracted from the fresh reconciled `availableBalance`. Exposure-increasing sizing is then capped by:

`(projectedAvailableBalance - minimumAvailableBalanceReserve) / simulationMarginReservationRate`

when the rate is enabled. If projected available balance is already at or below the minimum reserve, the request is rejected as `RISK_BLOCKED`.

Reservation journal records now carry the reservation rate and exact reserved available-balance amount. Terminal `FILLED`, `CANCELED`, or `REJECTED` reconciliation writes the corresponding released available-balance amount. Replay restores those persisted amounts, so the same free-balance headroom remains unavailable after process restart.

For compatibility with reservation records created immediately before this increment, missing balance fields are reconstructed using the currently configured simulation margin reservation rate. New records persist the exact amount and therefore replay independently of later configuration changes.

`ExecutionStatus.v1` now exposes:

- `reservedAvailableBalance`;
- `minimumAvailableBalanceReserve`;
- `simulationMarginReservationRate`.

The deterministic Windows acceptance uses a synthetic account with available balance 7, minimum free reserve 2 and margin reservation rate 0.5. A 10-notional accepted simulation reserves 5 balance units, leaving exactly the 2-unit safety reserve. Another exposure-increasing intent is blocked. Restart reconstructs the 5-unit reservation and remains blocked. Terminal fill reconciliation releases it, after which a later entry can again consume the restored headroom.

This is only projected simulation accounting. It does not change Binance leverage, margin mode, balances or any other exchange state.

## Effective leverage and margin-utilization enforcement

The read-only account reconciler now publishes two additional account-health inputs when the source provides them:

- `marginBalance` from the reconciled account margin balance;
- `initialMargin` from reconciled total initial margin.

They remain account observations, not sizing capital. The existing Risk Capital path is unchanged.

Because Architecture R3.1 names maximum effective leverage and maximum margin utilization but does not prescribe equations, this simulation layer makes its compatibility formulas explicit:

```text
projectedEffectiveLeverage =
    projectedGrossNotional / marginBalance

projectedMarginUtilization =
    projectedInitialMargin / marginBalance

projectedInitialMargin =
    reconciledInitialMargin + activeReservedAvailableBalance
```

For sizing a new exposure-increasing intent, the candidate notional is additionally capped by the remaining headroom implied by each configured limit. Margin-utilization headroom uses the configured simulation margin reservation rate to translate remaining margin capacity back into notional capacity.

Configuration:

```text
--max-effective-leverage VALUE
--max-margin-utilization RATIO
```

with environment equivalents:

```text
ASTU_MAX_EFFECTIVE_LEVERAGE
ASTU_MAX_MARGIN_UTILIZATION
```

A value of `0` disables the corresponding limit. `maxMarginUtilization` must be in `0..1`. A positive margin-utilization limit requires a positive `simulationMarginReservationRate` so projected initial-margin consumption is defined.

If either leverage/margin limit is enabled and reconciled margin metrics are unavailable, new exposure fails closed as `ACCOUNT_NOT_RECONCILED`. If the current projected ratio is already at or above a configured limit, new exposure is `RISK_BLOCKED`.

Active reservations are included in both calculations:

- reserved gross notional raises projected effective leverage;
- reserved available-balance/margin raises projected initial margin and margin utilization.

The deterministic acceptance coverage proves effective-leverage blocking, margin-utilization blocking, strict sizing reduction to remaining leverage headroom, missing-margin-metric fail-closed behavior, restart persistence of projected margin, terminal release, and later capacity reuse.

No Binance leverage-setting, margin-mode mutation, order submission, cancel request, transfer, or automatic `SUBMITTING` transition is added.

## Maximum net directional exposure

The read-only account reconciler now publishes signed `netDirectionalNotional` in addition to gross notional.

The sign convention is explicit:

- LONG position notional contributes positively;
- SHORT position notional contributes negatively;
- one-way/BOTH positions use the sign of `positionAmt`;
- flat positions contribute zero.

Active exposure reservations use the `SignalIntent.side` field in the same way. A LONG BUY/SCALE_IN reservation adds its full simulated notional to projected net exposure; a SHORT BUY/SCALE_IN reservation subtracts it. The execution journal already persists side + reserved notional, so signed reservation exposure is reconstructed after restart without a new mutable state source.

The configured symmetric limit is:

```text
--max-net-directional-notional VALUE
ASTU_MAX_NET_DIRECTIONAL_NOTIONAL
```

A value of `0` disables this check.

The projected risk baseline is:

```text
projectedNetDirectionalNotional =
    reconciledNetDirectionalNotional
    + signedActiveExposureReservations
```

For a new LONG exposure-increasing intent, remaining directional headroom is:

```text
maxNetDirectionalNotional
- projectedNetDirectionalNotional
```

For a new SHORT intent, it is:

```text
maxNetDirectionalNotional
+ projectedNetDirectionalNotional
```

This deliberately allows an opposite-side intent to reduce an already one-sided portfolio. Reaching the positive limit blocks additional LONG exposure but does not block a SHORT intent solely because the absolute current net equals the limit; the inverse applies at the negative limit.

Both the legacy and strict instrument sizing paths cap candidate notional by that side-specific remaining headroom. If the limit is configured but signed reconciled exposure is unavailable, new exposure fails closed as `ACCOUNT_NOT_RECONCILED`.

`ExecutionStatus.v1` now publishes:

- `maxNetDirectionalNotional`;
- `reservedNetDirectionalNotional`, the signed sum of active projected exposure reservations.

Deterministic coverage proves:

- a LONG reservation reaching the positive cap blocks another LONG;
- an equal SHORT reservation offsets the signed projected net and restores LONG directional headroom;
- signed reservation projection survives restart;
- strict LONG sizing is reduced to remaining positive directional headroom;
- strict SHORT sizing is reduced symmetrically at the negative boundary;
- missing reconciled signed exposure fails closed.

No exchange order, position, leverage, margin-mode, or routing mutation is introduced.

## Persisted UTC loss budgets and high-water drawdown

The execution risk layer now persists account-risk baselines independently of the order journal in:

```text
Core/runtime/account_loss_baseline.v1.json
```

The path is configurable with:

```text
--account-loss-baseline-file PATH
ASTU_ACCOUNT_LOSS_BASELINE_FILE
```

The state uses `AccountLossBaselineState.v1` and persists:

- UTC day index;
- Monday-aligned UTC week-start day index;
- daily and weekly starting Risk Capital;
- daily and weekly starting Margin Balance;
- all-time observed Margin Balance high-water mark;
- last persisted observation time.

The host runs a background account-risk monitor while these limits are enabled, so baseline/high-water maintenance is not dependent on a trading signal arriving. State writes are atomic and bounded to period/high-water changes plus a 60-second persistence heartbeat.

The current compatibility loss metrics are explicit:

```text
dailyRiskCapitalLoss =
    max(0, dailyStartRiskCapital - currentRiskCapital)

weeklyRiskCapitalLoss =
    max(0, weeklyStartRiskCapital - currentRiskCapital)

dailyTotalPnlLoss =
    max(0, dailyStartMarginBalance - currentMarginBalance)

weeklyTotalPnlLoss =
    max(0, weeklyStartMarginBalance - currentMarginBalance)

accountDrawdown =
    max(0, highWaterMarginBalance - currentMarginBalance)
```

Configured limits are:

```text
--max-daily-risk-capital-loss VALUE
--max-weekly-risk-capital-loss VALUE
--max-daily-total-pnl-loss VALUE
--max-weekly-total-pnl-loss VALUE
--max-account-drawdown VALUE
```

with environment equivalents:

```text
ASTU_MAX_DAILY_RISK_CAPITAL_LOSS
ASTU_MAX_WEEKLY_RISK_CAPITAL_LOSS
ASTU_MAX_DAILY_TOTAL_PNL_LOSS
ASTU_MAX_WEEKLY_TOTAL_PNL_LOSS
ASTU_MAX_ACCOUNT_DRAWDOWN
```

All default to `0` (disabled). A configured loss/drawdown control fails closed as `ACCOUNT_NOT_RECONCILED` when the required account/baseline evidence is unavailable. Once consumption reaches a configured threshold, additional exposure-increasing intents are `RISK_BLOCKED`. Exit/reduction actions remain outside the new-exposure block.

UTC period rollover resets the corresponding daily/weekly starting values to the first reconciled observation in the new UTC period. If no baseline file exists when the policy is first enabled, the first reconciled observation becomes the persisted compatibility baseline for that active period. The high-water Margin Balance does not reset on daily/weekly rollover.

`ExecutionStatus.v1` now exposes baseline readiness, baseline file, UTC period identifiers, start values, high-water value, current loss/drawdown consumption, and every configured threshold.

The deterministic coverage verifies baseline persistence across restart, UTC daily and weekly rollover, high-water advancement, clock-rollback fail-closed behavior, daily/weekly risk-capital and total-PnL gates, drawdown blocking, and malformed-state startup rejection. The Windows smoke proves a persisted daily Risk Capital loss block and a persisted Margin Balance high-water drawdown block across execution-host restarts.

The Risk Capital / Margin Balance compatibility budgets remain available, but exact realized-trade loss enforcement now uses a separate read-only income-history source described below.

No order submission, cancellation, leverage/margin mutation, transfer, hedge request or `SUBMITTING` transition is introduced.

## Read-only realized income evidence and exact realized-loss budgets

`Core/account/binance_usdm_income_reconciler.py` is a second disabled-by-default private USER_DATA reader. It uses Binance USD-M:

```text
GET /fapi/v1/income
```

and has no order, cancel, transfer, leverage, margin-mode or other mutation operation.

The reconciler freezes `endTime` to the current observation time, queries from the current Monday-aligned UTC week start, and paginates with the endpoint's `page` / `limit` fields. It requests all income types so classification is explicit rather than assuming every account flow is trading PnL.

`RealizedPnlSnapshot.v1` separates:

- `REALIZED_PNL` as realized trade PnL;
- `FUNDING_FEE` as funding;
- `COMMISSION` as commission;
- `TRANSFER` and every other income type as excluded from realized-trade-loss accounting.

Daily/weekly realized-trade PnL is the signed sum of only `REALIZED_PNL` rows. Exact loss-budget consumption is monotonic inside its UTC period:

```text
rawDailyRealizedTradeLoss =
    max(0, -dailyRealizedTradePnl)

dailyRealizedTradeLossConsumed =
    max(previousDailyConsumed, rawDailyRealizedTradeLoss)
```

with the same rule for the UTC week. This means later profitable trades do not reopen a realized-loss budget that was already consumed earlier in the same period. Daily consumption resets at the next UTC day; weekly consumption resets at the next Monday-aligned UTC week.

The persisted checkpoint is:

```text
Core/runtime/realized_pnl_accumulator.v1.json
```

using `RealizedPnlAccumulatorState.v1`. The state stores period identifiers, realized PnL, funding, commission, monotonic daily/weekly realized-loss consumption and record counts. On restart the new source result is checked against the persisted period/record state before it is accepted. Clock/state movement into the future, same-week record-count regression, corrupt state, or settlement-asset mismatch fails closed instead of silently resetting consumed loss.

The compatibility implementation currently requires one configured settlement asset (default `USDT`). If tracked `REALIZED_PNL`, `FUNDING_FEE` or `COMMISSION` evidence contains another asset, reconciliation fails closed rather than numerically adding unlike assets. This avoids pretending BNB/USDC/etc. income is directly interchangeable without an explicit conversion policy.

Exact realized-loss controls are:

```text
--max-daily-realized-trade-loss VALUE
--max-weekly-realized-trade-loss VALUE
```

with environment equivalents:

```text
ASTU_MAX_DAILY_REALIZED_TRADE_LOSS
ASTU_MAX_WEEKLY_REALIZED_TRADE_LOSS
```

and the local evidence file/freshness controls:

```text
--realized-pnl-status-file PATH
--max-realized-pnl-status-age-ms MS

ASTU_REALIZED_PNL_STATUS_FILE
ASTU_MAX_REALIZED_PNL_STATUS_AGE_MS
```

A configured exact realized-loss limit requires a fresh `RealizedPnlSnapshot.v1` for the current UTC day/week. Missing, stale, wrong-period, malformed or unreconciled evidence returns `ACCOUNT_NOT_RECONCILED`. Once daily or weekly consumed realized-trade loss reaches its configured threshold, additional exposure-increasing intents return `RISK_BLOCKED`.

`ExecutionStatus.v1` now reports the realized-PnL provider, readiness/file, realized trade PnL/loss, funding, commission, net classified trading income, source record counts and the exact daily/weekly realized-loss limits.

The supervisor exposes a separate `--realized-pnl-mode disabled|fixture|readonly`. Exact realized-loss limits are rejected at supervisor startup if that source mode is disabled. Live mode uses the same explicit `ASTU_BINANCE_PRIVATE_READONLY_ENABLED=1` gate and environment-only API credentials as the account reconciler.

This layer intentionally keeps realized trade PnL, funding and commissions separate. Funding/commission are visible evidence and are included in `dailyNetTradingIncome` / `weeklyNetTradingIncome`, but the exact **realized-trade-loss** limits use only `REALIZED_PNL`. Transfers and unrealized PnL never enter that gate.

The deterministic coverage proves income-type classification, transfer exclusion, transaction-ID deduplication, mixed-settlement-asset fail-closed behavior, monotonic consumed-loss persistence across apparent PnL recovery, stale/wrong-period provider rejection, daily/weekly exact loss blocking, missing-evidence fail-closed behavior, and no exchange-submission path.

## Local Named Pipe security hardening

The execution and reconciliation endpoints now share one hardened Windows Named Pipe creation path.

Security properties are explicit:

- the server resolves the execution-host process-user SID at runtime;
- a protected DACL contains exactly one allow ACE for that SID;
- no Everyone / Users / Authenticated Users / Anonymous / guest ACE is added;
- `PIPE_REJECT_REMOTE_CLIENTS` rejects remote Named Pipe access before application framing or JSON parsing;
- `FILE_FLAG_FIRST_PIPE_INSTANCE` causes an already-claimed canonical pipe name to fail closed rather than being silently joined.

The Windows acceptance test creates both canonical pipe names, validates the generated current-user-only DACL, impersonates the Anonymous token and requires `ERROR_ACCESS_DENIED`, and asserts the remote-rejection / first-instance flags. Both `AstuExecutionSim.v1` and `AstuExecutionReconcileSim.v1` use this same transport class.

This change only narrows local IPC access. It does not introduce order submission, cancellation, transfer, leverage/margin mutation, hedge mutation or automatic `SUBMITTING`.

## Read-only Account Risk operator view

`Core/operator/account_risk_view.py` now derives `AccountRiskView.v1` and a local auto-refreshing HTML page from `ExecutionStatus.v1`. The projection surfaces the R3.1 account-risk evidence already owned by the execution process:

- persisted UTC daily/weekly Risk Capital and Margin Balance baselines;
- high-water Margin Balance and current account drawdown;
- compatibility daily/weekly loss consumption;
- exact realized-trade daily/weekly loss consumption;
- configured limits, consumed ratios and remaining headroom;
- realized trade PnL, funding, commission and classified net income;
- projected exposure reservations and configured projected-risk limits;
- fail-closed source readiness and explicit current `ACCOUNT_NOT_RECONCILED` / `RISK_BLOCKED` reasons.

The view refuses any `ExecutionStatus.v1` that reports `orderRoutingEnabled=true`. Missing, malformed, stale, or clock-regressed source evidence is published as `ACCOUNT_NOT_RECONCILED` rather than rendered as healthy. The HTML contains no order/cancel/account controls and the generator opens no network or trading endpoint.

The simulation supervisor starts this read-only projection by default as a separately supervised child. Cross-platform tests cover clear/headroom, threshold blocking, missing realized evidence, stale evidence, clock rollback, disabled budgets and routing-invariant rejection. The Windows supervised-stack smoke requires the JSON and HTML views before continuing through the normal simulation-only request path.

## Current next implementation step

The operator view can show projected reservations and configured limits, but `ExecutionStatus.v1` does not yet publish all current reconciled account values needed to display live headroom for effective leverage, margin utilization, free balance, gross notional and signed net exposure in the same deterministic way as the loss budgets. The next increment should add those read-only account/exposure observations to `ExecutionStatus.v1` and extend `AccountRiskView.v1` with their current/projected values and headroom, without adding any exchange mutation or routing capability.
