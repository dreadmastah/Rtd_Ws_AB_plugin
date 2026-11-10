# Native implementation and limits

native/plugin.cpp builds a distinct DLL. Worker performs cancellable overlapped pipe reads with200ms waits, cancellation completion before OVERLAPPED destruction, fixed maximum65536 snapshot records (~5.8MB), exact owner/session/key validation, monotonically nondecreasing serial/time and equality for same-serial payloads. Worker exceptions fail health closed. State uses guarded cache and atomic lifecycle epoch; callback checks epoch before copying.

Notify owner-thread creates a private message-only timer window, validates same-process main-window/thread/DataSource, and holds a module reference. ADK documents WM_USER_STREAMING_UPDATE=WM_USER+13000 in D:\WSRTD_N1_AUTOMATIC_REFRESH_20261029_R1\adk_full\ADK\adk.html and QT example. Timer sends synchronously on owning UI thread; freshness transitions trigger invalidation too. At most3 notifications per revision/health change. Wrong-thread/reentrant unload refuses and pins module to avoid live WndProc code unloading. Normal unload joins only its own receiver and removes its own window/property.

R2Metrics counts callbacks/notifications/successes; it is not a complete per-symbol revision acknowledgment ledger. Permanent pin on wrong-thread release favors safety over unloadability; real host lifecycle qualification remains mandatory. Readiness must not be inferred from UI message delivery alone.

Direct SQLite adapter executes outside callback; lifetime-scale history admission exceeds current65536 snapshot bound and is unqualified. No durable final writer, full-prefix attestation integration, real18101 WebSocket ingestion or genuine producer custody exists. These limitations block production substitution despite functioning isolated native merge/refresh.
