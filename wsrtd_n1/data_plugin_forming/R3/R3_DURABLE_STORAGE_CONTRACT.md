# Disposable durable finalization

src/durable.py uses SQLite WAL+synchronousFULL and BEGIN IMMEDIATE. Exact(scope,symbol,UTCminute,interval) context, ownergeneration/session check inside transaction, immutable exact-decimal values, event SHA256 plus fullV3 receipt for integrated path, checkpoint advance atomically committed. Claim increments generation; stale owner commits fail. Identical values idempotent; conflicts reject. Forming events cannot commit. Process-crash tests use only disposable child os._exit before/afterCOMMIT. Not power-loss evidence.

Only output-root disposable DBs admitted. Existing scope/schema is read-only checked before write pragmas. No production migration exists. New DB initialization is not a cross-process exclusive provisioning service; production filesystem custody, atomic initialization and hardened schema/ACL checks remain separate gates. Direct low-level Store tests may omitV3receipt; integrated Pipeline persists it. Genuine custody always rejected; localchecksums cannot grant source authority.

Pipeline reports LIVE_FINALIZED_NOT_YET_DURABLE on storagefailure, then suppresses healthy forming snapshot until successful recovery. Durable rows restored and ledger hash/value linkage checked on reads. No archived/backfill source is relabelled asWS. Only synthetic source fixtures currently admitted.
