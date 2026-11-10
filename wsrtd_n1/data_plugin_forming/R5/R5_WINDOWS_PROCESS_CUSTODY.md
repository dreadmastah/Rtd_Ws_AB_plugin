# Windows custody scope

`src/custody.py` holds a query/synchronize process handle and checks PID, creation FILETIME, executable path and SHA-256, plus liveness. `src/controller.py` requires the producer PID to be the executing backend process, matches receiver PID/creation to the persistent ledger, and verifies both identities before startup, before read and after read. Start/read failure closes the owned backend. Wrong identities and contract digest fail before dispatch in isolated tests.

This proves isolated process identity, not external authority. The caller-supplied approval digest is not a signed operator authorization. Executable file hashing is not immutable image custody. Receiver death during blocked I/O is checked after the bounded read, not by a continuously qualified OS watcher. Ledger rollback/tampering protection and authentic production custody remain unqualified. No arbitrary PID string is promoted to genuine Binance custody.
