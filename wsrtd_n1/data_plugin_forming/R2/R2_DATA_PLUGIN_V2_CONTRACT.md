# WFR2 candidate contract

Version50202, ID WFR2, name WSRTD Forming R2 OFFLINE ONLY, x64 ADK Data Plugin. This DLL is deliberately restricted to output-root disposable directories and WFR2_FIXTURE_ONLY=1. It must not be installed into the current Broker. Existing v5.1.0 remains unchanged.

GetQuotesEx periodicity60 copies a bounded coherent snapshot under try_lock, with no SQLite or pipe I/O in the callback. Same-bucket replacement happens before publication; rows strictly ordered, unique per symbol/minute. Insufficient caller capacity fails without writing; there is no truncation or unscoped prior-buffer merge. History in the verified snapshot remains on disconnect; current forming rows expire/remove. Native timestamp conversion is UTC; Quotation fields necessarily narrow preserved decimal values to ADK float.

Full prefix, recent finalized availability, forming availability, native history readback and freshness remain separate. IsBackfillComplete always returns FALSE. No production full-prefix certificate or admission path is implemented. GetPluginStatus is always red, explaining synthetic/unqualified custody. GetRecentInfo returns null rather than inventing tick data. Configure returns0 and never registers/writes symbols. Daily callbacks are not implemented in this R2 fixture candidate and remain a compatibility gap before any replacement.

WFR2_PIPE, WFR2_SESSION, WFR2_OWNER_PID and WFR2_OWNER_CREATION are process-scoped fixture configuration. Database key is obtained independently from Notify directory handle, then matched to snapshot header. Protected or non-disposable paths rejected. No hardcoded production source or database is introduced.
