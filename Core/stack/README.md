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

These Risk Capital / Margin Balance controls are separate from exact realized-trade-loss evidence.

## Realized income mode

The supervisor can run the dedicated USD-M income reconciler independently of the account snapshot process:

- `disabled` — default; no income-history process;
- `fixture` — CI/development using the checked-in income fixture;
- `readonly` — signed read-only `GET /fapi/v1/income`, still gated by `ASTU_BINANCE_PRIVATE_READONLY_ENABLED=1` and environment-only credentials.

Example:

```cmd
python Core\stack\autotrader_sim_launcher.py ^
  --risk-mode readonly ^
  --realized-pnl-mode readonly ^
  --max-daily-realized-trade-loss 250 ^
  --max-weekly-realized-trade-loss 750
```

The supervisor refuses a positive exact realized-loss limit when `--realized-pnl-mode disabled` is selected.

The reconciler writes:

```text
Core/runtime/realized_pnl_status.v1.json
Core/runtime/realized_pnl_accumulator.v1.json
```

and classifies `REALIZED_PNL`, `FUNDING_FEE` and `COMMISSION` separately. Transfers/other flow types are excluded from the realized-trade-loss gate. The persisted accumulator keeps the maximum realized-loss consumption reached inside each UTC day/week so later profits cannot silently reopen a consumed loss budget.

The default settlement asset is `USDT`. Tracked income in another asset fails reconciliation closed until an explicit conversion policy exists.

## Read-only Account Risk operator view

The supervisor now starts a local read-only Account Risk view by default. It does not expose an HTTP server, Named Pipe command, order button, cancel action, or any exchange/account mutation route. It only reads the atomically published `ExecutionStatus.v1` file and writes:

```text
Core/runtime/account_risk_view.v1.json
Core/runtime/account_risk_view.html
Core/runtime/symbol_risk_status.v1.json
```

The projection reports:

- UTC daily/weekly period identifiers and persisted starting baselines;
- Risk Capital loss, Margin Balance compatibility loss, high-water drawdown, and exact realized-trade-loss consumption;
- each configured limit, remaining headroom, consumed ratio, readiness and block status;
- realized PnL, funding, commission, classified net trading income, settlement asset and record counts;
- projected exposure reservations and configured projected-risk limits;
- per-symbol current/reconciled notional, active symbol reservations, projected notional and max-symbol headroom for the bounded bootstrap universe;
- current/projected available balance, gross notional and open-position counts;
- current Margin Balance / initial margin plus projected effective leverage and margin utilization;
- current/projected signed net-directional exposure with LONG and SHORT headroom;
- explicit `ACCOUNT_NOT_RECONCILED` and `RISK_BLOCKED` reasons derived from the current status evidence;
- `orderRoutingEnabled=false` as a required invariant.

The view fails closed when its source is missing, malformed, stale, clock-regressed, or reports routing enabled. The HTML file auto-refreshes locally and contains no form controls or mutation endpoints.

Supervisor controls:

```cmd
python Core\stack\autotrader_sim_launcher.py ^
  --account-risk-view-mode local ^
  --account-risk-view-poll-seconds 1 ^
  --account-risk-view-max-source-age-ms 5000
```

Use `--account-risk-view-mode disabled` to suppress the derived view process. Custom output paths are available through `--account-risk-view-json` and `--account-risk-view-html`.

For a one-shot projection outside the supervisor:

```cmd
python Core\operator\account_risk_view.py ^
  --execution-status-file Core\runtime\execution_status.v1.json
```

## Synthetic projected-risk controls

The execution host synthetic mode exposes test-only limits for projected-risk acceptance:

```cmd
astu_execution_pipe_host.exe --synthetic ^
  --synthetic-max-gross-notional 10 ^
  --synthetic-max-open-positions 1
```

These switches are used only by deterministic simulation acceptance tests. Active exposure reservations are included in the next request's projected gross-notional and open-position checks. They do not enable order routing or exchange connectivity.

## Controlled Binance Demo Trading activation

The supervisor remains simulation-only by default. Runtime order routing is
available only for Binance USD-M Demo Trading and requires both explicit
routing switches:

```cmd
set ASTU_BINANCE_TESTNET_USER_DATA_ENABLED=1
python Core\stack\autotrader_sim_launcher.py ^
  --risk-mode readonly ^
  --instrument-mode public ^
  --testnet-user-data-mode live ^
  --enable-testnet-order-routing ^
  --arm-testnet-order-routing
```

The Demo credentials remain environment-only:

```text
ASTU_BINANCE_TESTNET_API_KEY
ASTU_BINANCE_TESTNET_API_SECRET
ASTU_BINANCE_TESTNET_USER_STREAM_URL_TEMPLATE
```

When both routing switches are present the supervisor additionally requires:

- REST base exactly `https://demo-fapi.binance.com`;
- a non-empty explicit Demo user-stream WebSocket template;
- live read-only account and position reconciliation;
- public instrument constraints sourced from the same Demo REST venue;
- `MARKET_LOT_SIZE` when Binance publishes it, with `LOT_SIZE` only as a fallback;
- live user-data convergence with account, positions and ASTU-owned orders converged;
- zero unresolved ASTU orders and no REST fallback requirement;
- authoritative order snapshots from the live user-data authority directory.

The C++ order gateway independently allowlists only
`demo-fapi.binance.com` and the legacy `testnet.binancefuture.com` host.
`fapi.binance.com` is rejected. The runtime path has no transfer, leverage,
margin-mode, cancel/amend, or mainnet routing capability.

## Status and stop

```cmd
python Core\stack\autotrader_sim_launcher.py --status
python Core\stack\autotrader_sim_launcher.py --stop
```

Runtime PID/log/journal state stays under `Core/runtime`.

The execution host continues to use `\\.\pipe\AstuExecutionSim.v1` and every successful simulated path terminates at `ORDER_ROUTING_DISABLED`.
