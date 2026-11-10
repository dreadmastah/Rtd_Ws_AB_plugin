# R4 bounded controller and metadata handoff

Implemented persistent one-shot admission, exact contract/session binding, aggregate REST/weight/connection/subscription/reconnect/frame/byte limits, clock checks and durable STOP latch. Failed attempts remain consumed across restart. Sender and relay preserve complete V3 event metadata through unchanged R3 disposable storage. Independent review and targeted tests recorded separately.

Fixture-only backend: no actual HTTP/WebSocket network implementation or production activation. Overall BLOCKED for genuine pilot; see R4_FINAL_DISPOSITION and R4_NEXT_OPERATOR_AUTHORIZATION. R3 DLL and 67-entry evidence preserved unchanged. No native rebuild or installation.

Source ingress and relay dispatch both consume the shared frame/byte budget. Ledger corruption checks are not hostile filesystem rollback protection; trusted clock, filesystem and OS custody remain production prerequisites. No automatic startup on receiverarrival, automaticreconnect or legacyfallback.
