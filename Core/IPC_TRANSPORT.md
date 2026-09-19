# Simulation IPC transport

The core now contains a bounded Windows Named Pipe request/response path for the future `Trade.dll -> Execution.exe` boundary.

## Pipe

```text
\\.\pipe\AstuExecutionSim.v1
```

Current transport properties:

- local Windows Named Pipe only;
- one request and one response per connection;
- 16-byte binary frame header;
- maximum payload: 64 KiB;
- payload length checked before allocation/read;
- CRC32C verified before JSON parsing;
- schema/message-type version checked;
- request ID and signal ID correlation checked by the client;
- bounded idempotency cache rejects duplicate keys;
- response always carries `orderRoutingEnabled=false`.

The JSON request body is intentionally flat in Revision 1 so the proof-of-contract codec stays small and deterministic. The pipe framing is independent of JSON and can later carry the canonical serializer selected for the implementation baseline.

## Binaries on Windows

CMake builds:

```text
astu_execution_pipe_host.exe
astu_trade_pipe_smoke.exe
```

The host currently uses a deterministic in-process simulation DataStatus/Risk provider. It is a transport proof, not yet the live WSRTD status provider.

Start the host:

```cmd
astu_execution_pipe_host.exe
```

Then from another console:

```cmd
astu_trade_pipe_smoke.exe
```

Expected response:

```text
decision=ORDER_ROUTING_DISABLED
acceptedForSimulation=true
orderRoutingEnabled=false
```

A repeated request with the same idempotency key is rejected by the dispatcher as `DUPLICATE_REQUEST`.

## Fail-closed layers

A request is rejected before simulated sizing when any of these fail:

1. binary frame length/magic/version;
2. CRC32C;
3. JSON/request schema;
4. request/idempotency identity;
5. WSRTD data readiness/identity;
6. universe ID/version;
7. data generation;
8. synthetic risk gate.

No implementation in this transport opens a Binance private connection or submits an order.
