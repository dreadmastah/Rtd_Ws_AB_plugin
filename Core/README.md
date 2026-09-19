# Core auto-trader scaffold - simulation only

This subtree is the first bounded attachment between the existing CleanRoomR2 WSRTD data path and the Architecture R3.1 trading-engine shape.

## Safety boundary

This code cannot submit an exchange order. It contains no Binance private API client, no credentials, no signing, and no production/Testnet routing. The terminal simulated path is `OrderRoutingDisabled`.

## Component map

- `common/` - bounded contracts shared by signal, data and execution simulation.
- `trade_plugin/` - `SignalIntentBuilder` scaffold for the future Trade.dll boundary.
- `wsrtd/` - adapter from observable R2 cache/freshness state to `DataStatus`.
- `execution/` - fail-closed intent validation, synthetic risk gate, synthetic sizing, and disabled order manager.
- `schemas/` - JSON Schema Draft 2020-12 contracts for `SignalIntent.v1` and `DataStatus.v1`.
- `tests/` - deterministic simulation-only checks.

## WSRTD R2 integration status

The current CleanRoomR2 plugin exposes cache counters such as `CacheEOD` and `CacheIntraday`, but it does not expose the Architecture R3.1 `universeVersion` and `dataGeneration` identity fields. The adapter therefore reports cache/freshness observations but intentionally sets identity unavailable. The simulation engine rejects that state with `IdentityUnavailable` rather than guessing values.

No current WSRTD files are modified by this scaffold.

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

## Next separately authorized interface step

Before any live signal can pass the identity gate, an authoritative versioned interface must provide the committed `universeVersion` and current `dataGeneration` from the data/universe authority. Do not synthesize, infer, or default those values.
