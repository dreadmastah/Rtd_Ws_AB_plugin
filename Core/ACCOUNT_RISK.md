# Account risk and reconciliation boundary

The execution simulator now has a separate read-only account-risk input boundary.

## Interface

`PrivateAccountGateway` exposes only:

```text
read_account_risk() -> AccountRiskSnapshot
```

It intentionally has no order-submission, cancellation, leverage, margin-mode, credential-management, or transfer methods.

## Runtime snapshot

The live execution host consumes a flat `AccountRiskSnapshot.v1` file. The snapshot contains:

- generation timestamp;
- reconciled flag;
- risk state;
- risk capital;
- available balance;
- gross notional;
- maximum gross notional;
- open-position count;
- maximum open-position count.

The file-backed provider is fail-closed. Missing, malformed, stale, or unreconciled input produces:

```text
reconciled=false
riskState=EMERGENCY
```

which causes the simulation engine to return `ACCOUNT_NOT_RECONCILED` before sizing.

## Host configuration

Default path:

```text
Core/runtime/account_risk_status.v1.json
```

Overrides:

```text
--risk-status-file <path>
--max-risk-status-age-ms <milliseconds>
ASTU_RISK_STATUS_FILE=<path>
```

In `--synthetic` transport-test mode the deterministic synthetic risk provider is used instead.

## Binance USD-M read-only gateway

`binance_usdm_readonly_gateway.py` can populate the same snapshot from the USD-M Futures USER_DATA account endpoint. Live private access is disabled unless:

```text
ASTU_BINANCE_PRIVATE_READONLY_ENABLED=1
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
```

The gateway uses only a signed account read. It does not expose or call order, cancel, leverage, transfer, or margin-mutation endpoints.

Default live endpoint:

```text
https://fapi.binance.com/fapi/v3/account
```

The base URL is configurable through `BINANCE_USDM_BASE_URL` or `--base-url`.

When the gateway is disabled, credentials are missing, the response cannot be reconciled, or a non-zero position lacks notional data, it writes a fresh fail-closed snapshot with:

```text
reconciled=false
riskState=EMERGENCY
```

Credentials are read from environment variables only and are not written to the risk snapshot or logs.

Fixture validation:

```cmd
Core\tools\run_readonly_account_fixture.cmd
```

## Restart reconciliation behavior

`run_reconciliation_restart_smoke.cmd` verifies three execution-host restarts:

1. reconciled account snapshot -> simulation reaches `ORDER_ROUTING_DISABLED`;
2. account snapshot missing after restart -> `ACCOUNT_NOT_RECONCILED`;
3. reconciled snapshot restored -> simulation again reaches `ORDER_ROUTING_DISABLED`.

All three decisions share the same durable execution journal, using distinct idempotency keys.

## Current boundary

The private gateway is read-only and disabled by default. Exchange order submission is still absent.
