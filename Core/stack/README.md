# Auto-trader simulation runtime supervisor

`autotrader_sim_launcher.py` supervises the Windows simulation execution host and, optionally, the read-only Binance account reconciler.

It never enables order routing.

## Risk modes

- `disabled` — default. No private-account process is started. The execution host therefore fails closed unless a fresh external `AccountRiskSnapshot.v1` already exists.
- `fixture` — development/CI only. Continuously refreshes the checked-in account fixture.
- `readonly` — starts the Binance USD-M read-only account reconciler. Live network access still requires `ASTU_BINANCE_PRIVATE_READONLY_ENABLED=1` and the API key/secret environment variables.

The read-only gateway has no order, cancel, leverage, margin-mode, or transfer methods.

## Start

From the repository root after the C++ build:

```cmd
python Core\stack\autotrader_sim_launcher.py --risk-mode disabled
```

For a local fixture-backed simulation:

```cmd
python Core\stack\autotrader_sim_launcher.py --risk-mode fixture
```

For explicitly enabled read-only account reconciliation:

```cmd
set ASTU_BINANCE_PRIVATE_READONLY_ENABLED=1
set BINANCE_API_KEY=...
set BINANCE_API_SECRET=...
python Core\stack\autotrader_sim_launcher.py --risk-mode readonly
```

## Status and stop

```cmd
python Core\stack\autotrader_sim_launcher.py --status
python Core\stack\autotrader_sim_launcher.py --stop
```

Runtime PID/log/journal state stays under `Core/runtime`.

The execution host continues to use `\\.\pipe\AstuExecutionSim.v1` and every successful simulated path terminates at `ORDER_ROUTING_DISABLED`.
