# Native host preflight — BLOCKED for activation

Fresh read-only process/module observations are in evidence/HOST_READONLY.json. Broker PID 80796 was observed parented by 62440; its creation identity and image hash are bound in that receipt. Installed N1 Database Bound and Radar InHost R1 modules were observed. Module presence does not attest the selected data source or active database. Current source/database selection and exclusive writer custody remain UNATTESTED. Previous N1 GUI evidence is historical.

The candidate is x64 compiled against the copied ADK and exercises Init, Notify, GetQuotesEx and Release in a native harness. It is still OFFLINE ONLY, red status, full-prefix false. UTC minute timestamps are constructed with _gmtime64_s; daily aggregation requires all 1440 durable minutes. Weekly and mixed-EOD/intraday actual-host behavior remains BLOCKED.

Official [Plugins guide](https://www.amibroker.com/guide/w_plugins.html) documents startup scanning and loaded-DLL write locks. Its old Load/Unload text is superseded by [release notes](https://www.amibroker.com/guide/ReleaseNotes.html): those buttons were removed in 5.43.0. No hot-load or injection is proposed. [Database Settings](https://www.amibroker.com/guide/w_dbsettings.html) identifies source selection as per-database configuration. Changing it is a separate mutation, not part of this preflight.

No independently isolated AmiBroker host is proven. A second PID or /database argument does not establish Preferences, writer or supervisor isolation. Existing Broker stays open. No host startup is authorized by this package.

Later operator-controlled sequence, only after qualification and separate approvals:
1. Refresh Broker/supervisor image, creation identities, selected source and physical database/writer custody; bind the approved test host and disposable database.
2. Approve its lifecycle and DLL staging only after confirming it cannot trigger or be adopted by protected supervisors. Never overwrite a loaded DLL.
3. Stage only the approved hash under the qualified host installation lifecycle. Start the bounded receiver/coordinator before the qualified host with process-scoped identities; do not alter global Preferences.
4. Select the approved source only in the disposable database. Observe exact UTC minute/OHLCV in Quote Editor and chart; correlate source receipt, relay acknowledgment, durable commit, GetQuotesEx and lifecycle-bound refresh notification.
5. Observe two consecutive finalized minutes without manual Refresh. Weekly/mixed interval and persistence after an authorized restart are separate tests.
6. Abort on custody, configuration or protected-service change. Stop only the test-owned resources. Restore only candidate changes under a separately approved unloaded-DLL lifecycle; never remove quotations.

Native harness notification counts do not establish AmiBroker chart refresh. No host action was executed.
