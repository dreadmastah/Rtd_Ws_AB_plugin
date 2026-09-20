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
- `schemas/` - JSON Schema Draft 2020-12 contracts for `SignalIntent.v1` and `DataStatus.v1`.
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

`astu_sim_reconcile` is currently an **offline simulation/recovery tool**. Stop the execution host before applying events to its journal, then restart the host to verify reconstruction. It does not call Binance or any other exchange endpoint.

Example:

```cmd
astu_sim_reconcile.exe --journal execution_journal.v1.jsonl ^
  --order-id SIMORD-... ^
  --event-id EV-001 ^
  --event MARK_UNKNOWN
```

The reconciliation restart acceptance follows this simulation path:

`SIZING -> UNKNOWN_RECONCILE_REQUIRED -> ACKNOWLEDGED -> WORKING -> PARTIAL -> FILLED`

It then restarts the execution host and verifies the final state, cumulative fill evidence, duplicate guard, transition count, reconciliation count, and the invariant that no `SUBMITTING` transition or exchange-submission attempt occurred.

## Current next implementation step

After this reconciliation head is validated, the next simulation-only increment should move reconciliation ingestion into the running execution service itself using a bounded local IPC contract, so external simulated account/order events do not write the journal concurrently. That service-side ingress should preserve the same journal/FSM validation and still contain no exchange submission endpoint.
