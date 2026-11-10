from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parent
def put(n,v):(R/n).write_text(v if isinstance(v,str) else json.dumps(v,indent=2),encoding='utf-8')
def read(n):return json.loads((R/n).read_text())
put('R7_OFFICIAL_ENDPOINT_EVIDENCE.md','''# Official endpoint evidence — reviewed 2026-11-10

Sources: [USD-M Connect](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Connect) and [routing migration](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Important-WebSocket-Change-Notice), both showing October 30, 2026 modification dates.

The Connect page identifies fstream.binance.com, routed /public, /market and /private URLs, lowercase stream names and raw /ws/<streamName> access. It documents 24-hour connections, server pings, 10 incoming messages/second and 1024 streams/connection. These are exchange limits, not permission to use them.

The migration page maps klines to /market and gives the <symbol>@kline_<interval> format. It states the April 23, 2026 migration deadline and warns that unrouted connections no longer deliver market/private streams. Therefore the exact proposed raw BTCUSDT minute endpoint is wss://fstream.binance.com/market/ws/btcusdt@kline_1m. It is USD-M, not dstream COIN-M or spot.

The R7 allowlist accepts only that exact URL; explicit alternate ports, queries, credentials, fragments, other symbols and routes are rejected. Its URL stream consumes one subscription before connect; no JSON SUBSCRIBE is allowed. All dispatch remains test-owned localhost TLS. External address routing and genuine authority remain BLOCKED. Documentation retrieval is recorded separately from zero Binance trading/market-data REST and WS requests.

Existing sender inspection: evidence/LEGACY_SENDER_ROUTES.json binds the deployed release source. Its defaults already use /public/stream and /market/stream; no claim that this source is unrouted is warranted. The separate legacy automatic 500-symbol launch policy remains unsuitable for a BTC-only pilot.
''')
host=read('evidence/HOST_READONLY.json')
put('R7_NATIVE_HOST_PREFLIGHT.md','''# Native host preflight — BLOCKED for activation

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
''')
put('evidence/R7_FAILURE_HISTORY.json',dict(source='Execution tool observations retained as narrative, not recovered raw stderr files',failures=['Initial repeated final rejected: changed local receipt made final immutable comparison fail','Boundary-adjacent forming event expired in transit; admission correctly rejected'],corrections=['Exact exchange-field duplicate final permits different local receipt, retains original cached receipt','Fixture stops forming emission one second before real minute boundary'],final_evidence='R7_SAME_MINUTE_FINALIZATION.json',predecessor_failures_preserved=True))
put('R7_FIRST_GENUINE_BTCUSDT_PILOT.md','''# BTCUSDT genuine pilot — NOT READY FOR EXECUTION

Proposed exact endpoint: wss://fstream.binance.com/market/ws/btcusdt@kline_1m
Symbol BTCUSDT, interval 1m, REST 0, WS connections 1, URL stream subscriptions 1, reconnects 0, disposable database only. UTC start/end and duration remain UNBOUND. No current process identity is carried forward as future authority.

Shortest remaining path:
1. Implement/qualify the external DNS/address/TLS transport against the documented policy. R7 deliberately dispatches only localhost; a local TLS success is not external production readiness. Resolve bounded DNS cancellation limitations and outbound control-frame rate enforcement before approval.
2. Bind actual permitted producer/controller/relay/receiver/writer identities, final hashes and physical disposable database. Local observed TCP peer custody is not operator authorization or atomic protection against all OS races.
3. Supply authoritative listing-to-cutoff historical coverage and provenance admission. Existing bootstrap R2 recorded suffix and synthetic coverage cannot establish full-prefix completeness. Reuse parser/planner tests; do not reacquire everything blindly, but missing genuine coverage still needs separate acquisition authority.
4. Qualify the host lifecycle/source selection and preserve 10101/18101. Do not attach a new receiver to the existing 18101 supervisor: it can start the legacy 500-symbol sender. A versioned separately authorized handoff must fence that decision first, or an independently qualified test-owned path must remain disconnected from 18101.
5. After technical gates and review pass, bind one finite UTC window, byte/frame ceilings, all hashes, source generation, cleanup and exact host/network permissions. Genuine network, DLL installation, source change and historical admission are separate approvals.

Abort for wrong peer/generation, unexpected endpoint/request/reconnect, budget/deadline failure, stale data, finality conflict or storage failure. Close only authorized test-owned sockets/processes; no fallback to legacy sender and no automatic reconnect. Preserve original DLLs and historical records. R7 itself remains fixture-only and may not be installed as a genuine feed.
''')
put('R7_EXACT_OPERATOR_AUTHORIZATION.md','''# Approval fields — BLOCKED, not an execution request

SYMBOL=BTCUSDT; INTERVAL=1m; REST_REQUESTS=0; WS_CONNECTIONS=1; STREAM_SUBSCRIPTIONS=1; RECONNECTS=0; DATABASE=DISPOSABLE_ONLY.

UNBOUND: UTC window/duration, real source-generation authority, approved external DNS/address set and TLS route, producer/controller/relay/receiver executable and script hashes, PID/creation identities, disposable writer identity, full-prefix certificate, qualified host lifecycle, installation/source-selection scope, cleanup limits.

The manifest binds offline engineering artifacts, not live authority. Do not run a producer or install the candidate based on this document. No host-changing CMD commands are supplied while these fields remain unqualified. The immediate technical work is the external dispatch/genuine custody and historical admission adapter; host changes remain separately gated.
''')
status=dict(TASK_ID='WSRTD_N1_DATA_PLUGIN_R7_GENUINE_SOURCE_AND_HOST_PREFLIGHT',R6_PREDECESSOR_INTEGRITY='PASS',BINANCE_USDM_ENDPOINT='DOCUMENTATION_QUALIFIED',EXTERNAL_ENDPOINT_ENFORCEMENT='BLOCKED_EXTERNAL_DISPATCH_NOT_IMPLEMENTED',BOUNDED_DNS_BEHAVIOR='LIMITATION',NETWORK_HARD_STOPS='PASS_ISOLATED',WINDOWS_PEER_CUSTODY='PASS_ISOLATED',SAME_MINUTE_FINALIZATION='PASS_ISOLATED',NATIVE_STALE_DISCONNECT='PASS_ISOLATED',NATIVE_HOST_PREFLIGHT='BLOCKED_CURRENT_SOURCE_AND_WRITER_CUSTODY_UNATTESTED',WEEKLY_MIXED_INTERVALS='BLOCKED',FULL_PREFIX_ADMISSION='BLOCKED',GENUINE_PRODUCER_CUSTODY='BLOCKED',GENUINE_BINANCE_RECEIPT='NOT_EXECUTED',ACTUAL_AMIBROKER_CHART='NOT_EXECUTED',R7_DLL='BUILT',INDEPENDENT_REVIEW='BLOCKED_FULL_MILESTONE_SCOPED_REPORT_SEPARATE',PRODUCTION_DLL_INSTALLED=False,PRODUCTION_BROKER_RESTARTED=False,PROTECTED_10101_MODIFICATIONS=0,PROTECTED_18101_MODIFICATIONS=0,BINANCE_REQUESTS=0,PRODUCTION_DATABASE_WRITES=0,OVERALL='BLOCKED_GENUINE_SOURCE_AND_HOST_PREREQUISITES',BINANCE_REQUESTS_SCOPE='Market-data/trading API and WebSocket; official documentation pages read separately',release_approved=False)
put('R7_FINAL_DISPOSITION.json',status)
dll=read('evidence/DLL_BUILD.json')
put('R7_WINDOWS_CMD_VERIFICATION.md',f'''# Windows CMD read-only verification

```cmd
py -3.12 -B D:\\WSRTD_N1_DATA_PLUGIN_FORMING_R7\\verify.py
certutil -hashfile D:\\WSRTD_N1_DATA_PLUGIN_FORMING_R7\\artifacts\\WSRTD_Data_Forming_R7.dll SHA256
type D:\\WSRTD_N1_DATA_PLUGIN_FORMING_R7\\R7_FINAL_DISPOSITION.json
```

Expected DLL hash: {dll['sha256']}

These commands do not rerun tests, install plugins, launch AmiBroker, alter sources or access Binance feeds. Test TLS credentials are disposable and excluded from the manifest. All live approval fields remain unbound.
''')
print('R7 reports written; no live approval')
