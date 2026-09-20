# Auto-trader simulation runtime supervisor

`autotrader_sim_launcher.py` supervises the Windows simulation execution host and, optionally, the read-only Binance account reconciler.

It never enables order routing.

## Risk modes

- `disabled` — default. No private-account process is started. The execution host therefore fails closed unless a fresh external `AccountRiskSnapshot.v1` already exists.
- `fixture` — development/CI only. Continuously refreshes the checked-in account fixture.
- `readonly` — starts the Binance USD-M read-only account reconciler. Live network access still requires `ASTU_BINANCE_PRIVATE_READONLY_ENABLED=1` and the API key/secret environment variables.

The read-only gateway has no order, cancel, leverage, margin-mode, or transfer methods.

When `risk-mode` is `fixture` or `readonly`, the same account reconciliation process also publishes per-symbol `PositionSnapshot.v1` files under `Core/runtime/position_status`. The execution host consumes them for SCALE_IN/SCALE_OUT validation and fails closed on missing, stale, flat, hedged, or side-conflicting state.

## Instrument modes

- `disabled` — default. The execution host uses the legacy simulation sizing path and does not require an instrument snapshot.
- `fixture` — CI/development. Publishes the checked-in BTCUSDT public exchange-info fixture into `InstrumentConstraints.v1`.
- `public` — periodically reads Binance USD-M public `/fapi/v1/exchangeInfo` and publishes local `InstrumentConstraints.v1` snapshots for the configured bootstrap symbols.

The instrument publisher uses public metadata only. It has no credentials, signing, or order endpoint.

When an instrument mode is enabled, the execution host fails closed if the symbol rules are missing, stale, malformed, or fail the quantity/notional filters.

## Startup order-state authority

The supervisor can optionally forward a directory of `AuthoritativeSimulationOrderSnapshot.v1` files into the execution host:

```cmd
python Core\stack\autotrader_sim_launcher.py ^
  --risk-mode fixture ^
  --instrument-mode fixture ^
  --order-snapshot-dir Core\runtime\authoritative_order_snapshots
```

When configured, startup reconciliation is required for every normalized simulation order in the journal. Missing/stale/mismatched non-terminal state is moved to `UNKNOWN_RECONCILE_REQUIRED`; terminal disagreements fail startup closed. The same source is then swept periodically while the execution host remains running. The default interval is 2000 ms and can be changed with `--order-reconcile-interval-ms`. Runtime disagreements also move to `UNKNOWN_RECONCILE_REQUIRED`, and source recovery alone does not auto-resolve the order; explicit reconciliation evidence is required.

The local helper `Core/order_state/simulated_order_state_source.py` can publish simulation snapshots for tests. It performs no exchange I/O.

## Start

From the repository root after the C++ build:

```cmd
python Core\stack\autotrader_sim_launcher.py --risk-mode disabled
```

For a local fixture-backed simulation:

```cmd
python Core\stack\autotrader_sim_launcher.py --risk-mode fixture --instrument-mode fixture
```

For explicitly enabled read-only account reconciliation:

```cmd
set ASTU_BINANCE_PRIVATE_READONLY_ENABLED=1
set BINANCE_API_KEY=...
set BINANCE_API_SECRET=...
python Core\stack\autotrader_sim_launcher.py --risk-mode readonly --instrument-mode public
```

## Projected pending and symbol limits

The supervisor forwards two optional simulation risk limits to the execution host:

```cmd
python Core\stack\autotrader_sim_launcher.py ^
  --risk-mode fixture ^
  --max-pending-entry-scale-in-reservations 4 ^
  --max-symbol-notional 2500
```

A value of `0` disables that specific limit.

When `--max-symbol-notional` is enabled in fixture/read-only mode, the execution host requires a fresh reconciled `PositionSnapshot.v1` for the requested symbol so current symbol notional can be combined with active reservations. Missing/stale/unreconciled symbol exposure fails closed.

The pending-entry/scale-in limit counts active simulation exposure reservations. It does not claim to be an exchange open-order count; exchange private-order reconciliation remains outside this no-submission increment.

## Available-balance reservation controls

The supervisor also forwards the simulation-only free-balance policy:

```cmd
python Core\stack\autotrader_sim_launcher.py ^
  --risk-mode fixture ^
  --minimum-available-balance-reserve 100 ^
  --simulation-margin-reservation-rate 0.10
```

The rate is deliberately configurable rather than inferred from Binance leverage. A rate of `0.10` means the simulator reserves 0.10 units of reconciled available balance for each unit of accepted simulated notional. No exchange leverage or margin setting is changed.

A positive `--minimum-available-balance-reserve` requires a positive `--simulation-margin-reservation-rate`. Active balance reservations survive restart through the execution journal and are released only after terminal simulated reconciliation.

## Effective leverage and margin utilization

The supervisor forwards two additional simulation-only account-risk limits:

```cmd
python Core\stack\autotrader_sim_launcher.py ^
  --risk-mode fixture ^
  --simulation-margin-reservation-rate 0.10 ^
  --max-effective-leverage 3 ^
  --max-margin-utilization 0.60
```

`--max-effective-leverage 0` and `--max-margin-utilization 0` disable their respective checks. Margin utilization is a ratio in `0..1` and requires a positive simulation margin reservation rate.

These options only evaluate reconciled/projected account state. They do not call Binance leverage or margin-mode mutation APIs.

## Net directional exposure

The supervisor forwards the symmetric signed-net-notional limit:

```cmd
python Core\stack\autotrader_sim_launcher.py ^
  --risk-mode fixture ^
  --max-net-directional-notional 5000
```

A value of `0` disables the limit. Live/fixture risk snapshots provide reconciled signed net notional, while active simulation reservations contribute signed projected notional from `SignalIntent.side`.

The limit is directional rather than gross: a SHORT projected reservation can offset LONG net exposure, and vice versa. Gross-notional limits remain independently enforced.

This control evaluates only simulation/account state; it does not submit an opposite-side hedge or otherwise mutate exchange positions.

## UTC loss budgets and high-water drawdown

The supervisor forwards persisted account-risk loss controls:

```cmd
python Core\stack\autotrader_sim_launcher.py ^
  --risk-mode fixture ^
  --max-daily-risk-capital-loss 250 ^
  --max-weekly-risk-capital-loss 750 ^
  --max-daily-total-pnl-loss 300 ^
  --max-weekly-total-pnl-loss 900 ^
  --max-account-drawdown 1000 ^
  --account-loss-baseline-file Core\runtime\account_loss_baseline.v1.json
```

A value of `0` disables an individual limit. Daily/weekly Risk Capital consumption uses the persisted Risk Capital baseline. The optional total-PnL compatibility budgets and high-water drawdown use reconciled Margin Balance.

The baseline tracker runs continuously in the execution host while any of these limits are active. Daily and weekly baselines roll on UTC boundaries; the week is Monday-aligned. The Margin Balance high-water mark persists across those period rollovers.

The current account endpoint does not provide an exact historical realized-PnL ledger, so these controls must not be described as exact realized-trade-PnL limits. A separate read-only realized-income source remains required for that distinction.

## Synthetic projected-risk controls

The execution host synthetic mode exposes test-only limits for projected-risk acceptance:

```cmd
astu_execution_pipe_host.exe --synthetic ^
  --synthetic-max-gross-notional 10 ^
  --synthetic-max-open-positions 1
```

These switches are used only by deterministic simulation acceptance tests. Active exposure reservations are included in the next request's projected gross-notional and open-position checks. They do not enable order routing or exchange connectivity.

## Status and stop

```cmd
python Core\stack\autotrader_sim_launcher.py --status
python Core\stack\autotrader_sim_launcher.py --stop
```

Runtime PID/log/journal state stays under `Core/runtime`.

The execution host continues to use `\\.\pipe\AstuExecutionSim.v1` and every successful simulated path terminates at `ORDER_ROUTING_DISABLED`.
