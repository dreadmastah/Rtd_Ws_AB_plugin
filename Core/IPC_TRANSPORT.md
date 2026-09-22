# Simulation IPC transport

The core now contains a bounded Windows Named Pipe request/response path for the future `Trade.dll -> Execution.exe` boundary.

## Pipe

```text
\\.\pipe\AstuExecutionSim.v1
```

Current transport properties:

- local Windows Named Pipe only;
- remote clients are rejected by the kernel with `PIPE_REJECT_REMOTE_CLIENTS`;
- the server applies a protected DACL granting pipe access only to the execution-host Windows user SID;
- `FILE_FLAG_FIRST_PIPE_INSTANCE` prevents silently joining an already-claimed pipe name;
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

The host defaults to the live file-backed WSRTD DataStatus provider. Use `--synthetic` only for isolated transport tests. The risk provider is still synthetic in both modes.

Start the host against the normal WSRTD runtime status directory:

```cmd
astu_execution_pipe_host.exe --status-dir CleanRoomR2\stack\runtime\autotrader_status
```

For transport-only testing:

```cmd
astu_execution_pipe_host.exe --synthetic
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

The execution host persists idempotency reservations and simulation decisions in an append-only journal. The smoke runner restarts the host with the same journal and verifies that the same idempotency key remains rejected after process restart.

## Local security boundary

Both canonical endpoints:

```text
\\.\pipe\AstuExecutionSim.v1
\\.\pipe\AstuExecutionReconcileSim.v1
```

use the same secure server-creation path. At creation time the host resolves its current process-user SID and builds a protected DACL with exactly one allow ACE for that SID. No Everyone, Users, Authenticated Users, Anonymous, network, or guest ACE is added.

The pipe mode also includes `PIPE_REJECT_REMOTE_CLIENTS`, so SMB/remote Named Pipe clients are rejected before protocol parsing. The host requests `FILE_FLAG_FIRST_PIPE_INSTANCE` so a pre-existing instance with the same canonical name causes startup/serve failure rather than being silently joined.

Windows acceptance coverage inspects the generated DACL, checks that only the current user SID is granted access, verifies an anonymous impersonation token receives `ERROR_ACCESS_DENIED` on both canonical pipe names, and compile-time asserts the remote-client rejection and first-instance flags.

## Fail-closed layers

A request is rejected before simulated sizing when any of these fail:

1. Windows Named Pipe local-user/remote-client security policy;
2. binary frame length/magic/version;
3. CRC32C;
4. JSON/request schema;
5. request/idempotency identity;
6. WSRTD data readiness/identity;
7. universe ID/version;
8. data generation;
9. synthetic risk gate.

No implementation in this transport opens a Binance private connection or submits an order.


## Reserved Demo execution endpoint

The Demo execution milestone reserves a separate local endpoint:

```text
\\.\pipe\AstuExecutionDemo.v1
```

This endpoint is deliberately distinct from `AstuExecutionSim.v1`. The
simulation request must never be reinterpreted as an exchange-submission
request.

The first Demo milestone increment adds only the request/result contract and
admission policy. Admission requires all of the following before a future
router may be invoked:

1. the existing local-user Named Pipe security boundary;
2. `DemoExecutionRequest.v1` schema validation;
3. a bounded, unexpired request timestamp;
4. an explicit application capability ID and high-entropy bearer token;
5. a fresh `TestnetUserDataState.v1` convergence snapshot;
6. live/orderly user-data, reconciled account + positions + orders, no REST
   fallback requirement, and zero unresolved ASTU orders.

The capability token is request-only sensitive material. It must not be copied
to responses, journals, status artifacts, or logs.

At this checkpoint no Demo pipe server, Binance order gateway, or
`/fapi/v1/order` submission path is wired. A successful admission result means
only that the request passed the pre-routing gate; it is not proof that an
exchange order was attempted.
