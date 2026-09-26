# Human work authorization - core auto-trader scaffold

Date: 2026-09-19

Authorized scope:

- Add an isolated core auto-trader scaffold beside the CleanRoomR2 WSRTD work.
- Add SignalIntent/DataStatus contracts, simulation-only validation/risk/sizing interfaces, and tests.
- Add an adapter boundary for the current WSRTD R2 cache/freshness fields.
- Keep the current WSRTD DLL and runtime stack unchanged.

Explicitly not authorized:

- Binance private API access or credentials.
- Testnet or production order submission.
- Arm/disarm actions or remote trading controls.
- DLL installation or AmiBroker runtime mutation by this change.
- Milestone promotion, production authorization, or relaxation of fail-closed checks.

The scaffold must return/retain an order-routing-disabled state. Current WSRTD R2 does not provide the architecture-level universeVersion/dataGeneration identity required by SignalIntent validation, so the live R2 adapter remains fail-closed until a separately authorized interface supplies those values.
