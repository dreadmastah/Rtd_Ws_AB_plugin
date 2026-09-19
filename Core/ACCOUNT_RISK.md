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

## Current boundary

There is still no Binance private network implementation in this increment. The file contract is the reconciliation boundary that a later read-only `BinancePrivateGateway` implementation can populate. Order routing remains absent.
