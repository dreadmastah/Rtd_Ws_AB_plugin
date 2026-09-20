# Core auto-trader scaffold - simulation only

This subtree is the first bounded attachment between the existing CleanRoomR2 WSRTD data path and the Architecture R3.1 trading-engine shape.

## Safety boundary

This code cannot submit an exchange order. It contains a disabled-by-default Binance USD-M read-only account reconciler for risk/position state, but no order, cancel, leverage, margin-mode, transfer, Testnet-routing, or production-routing operation. Credentials are read only from environment variables when read-only reconciliation is explicitly enabled. The terminal simulated path is `OrderRoutingDisabled`.

## Component map

- `common/` - bounded contracts shared by signal, data and execution simulation.
- `trade_plugin/` - `SignalIntentBuilder` scaffold for the future Trade.dll boundary.
- `wsrtd/` - adapter from observable R2 cache/freshness state to `DataStatus`.
- `execution/` - fail-closed intent validation, account risk gate, deterministic simulation sizing, instrument filters, durable journal, and disabled order manager.
- `account/` - read-only private-account boundary plus stale/missing fail-closed risk and per-symbol position snapshot providers.
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

Windows uses `FILE_FLAG_WRITE_THROUGH` plus `FlushFileBuffers` for journal appends. The journal path defaults to:

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

## Current next implementation step

After this available-balance reservation layer is validated, the next simulation-only risk increment should add explicit maximum effective-leverage and maximum margin-utilization checks using reconciled account metrics plus active projected reservations. The implementation should keep the policy values configurable and fail closed when the required account fields are unavailable, without adding any leverage-setting or margin-mode mutation endpoint.
