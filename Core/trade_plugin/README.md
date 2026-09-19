# AstuTrade AmiBroker AFL plug-in

`AstuTrade.dll` is the simulation-only AFL-facing bridge for the auto-trader core.

It is separate from the WSRTD data DLL.

## Exported AFL functions

### AstuSimulate

```text
AstuSimulate(
    symbol,
    action,
    side,
    strategyId,
    strategyVersion,
    sourcePeriodicity,
    triggerPrice,
    validitySeconds
)
```

Argument order follows the AmiBroker ADK rule that string arguments precede numeric arguments.

Supported action strings: `BUY`, `SELL`, `SCALE_IN`, `SCALE_OUT`.

Supported side strings: `LONG`, `SHORT`.

The function:

- reads the current per-symbol WSRTD runtime DataStatus from `ASTU_STATUS_DIR`;
- binds its verified universe identity and completed-1m generation into a new SignalIntent;
- uses that completed generation as `sourceBarTime`;
- generates unique signal/request/idempotency IDs;
- sends the request to `\\.\pipe\AstuExecutionSim.v1`;
- returns the numeric `DecisionCode`.

It does not contain exchange credentials and does not submit orders.

### AstuVersion

Returns `10000` (1.0.0 encoding).

### AstuLastDecision

Returns the numeric `DecisionCode` from the last `AstuSimulate` call in the current DLL process.

## Runtime prerequisite

Set:

```text
ASTU_STATUS_DIR=<absolute path to CleanRoomR2\stack\runtime\autotrader_status>
```

and run `astu_execution_pipe_host.exe` with live WSRTD status and reconciled account-risk inputs.

## Decision code values

The numeric values are explicit stable codes in `astu/core/contracts.hpp`:

| Code | Meaning |
|---:|---|
| 0 | SIMULATED_ACCEPTED |
| 10 | INVALID_INTENT |
| 20 | DATA_NOT_READY |
| 21 | IDENTITY_UNAVAILABLE |
| 22 | UNIVERSE_MISMATCH |
| 23 | DATA_GENERATION_MISMATCH |
| 24 | NOT_YET_VALID |
| 25 | EXPIRED |
| 30 | ACCOUNT_NOT_RECONCILED |
| 31 | RISK_BLOCKED |
| 100 | ORDER_ROUTING_DISABLED |
| 110 | DUPLICATE_REQUEST |
| 120 | FRAME_INVALID |

AFL should treat code `100` / `ORDER_ROUTING_DISABLED` as the successful simulation terminal state, not as a live order confirmation.

## AmiBroker ABI

The plug-in implements the AFL plug-in exports required by the AmiBroker ADK:

```text
GetPluginInfo
SetSiteInterface
GetFunctionTable
Init
Release
```

The minimal ABI declarations in `amibroker_abi_min.hpp` are based on AmiBroker ADK 2.1a. The original ADK license notice is preserved there.
