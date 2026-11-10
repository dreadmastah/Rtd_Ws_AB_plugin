"""Evidence packaging only. No release seal or production operation."""
from pathlib import Path
import json,hashlib,datetime
R=Path(__file__).parent
def read(p):return json.loads((R/p).read_text())
def put(p,o):(R/p).write_text(json.dumps(o,indent=2),encoding='utf-8')
def doc(p,s):(R/p).write_text(s,encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
author=read('evidence/AUTHOR_TESTS.json');native=read('independent/native_results.json');receiver=read('independent/receiver_results.json')
assert native['dll_sha256']==sha(R/'artifacts/WSRTD_Data_Forming_R2.dll')
assert native['source_sha256']==sha(R/'native/plugin.cpp')
current_receiver=sha(R/'transport.py')
put('R2_18101_PRODUCER_READINESS.json',{'status':'BLOCKED','current_producer':'UNVERIFIED','reason':'No qualified current sender/output established by process/source observation. Zero established relay clients alone does not prove inactive upstream.','restoration_authorized':False,'production_receiver_connection':False,'source_chain':'R2_18101_PROCESS_AND_SOURCE_CHAIN.json'})
doc('R2_18101_PROTOCOL_GAP_ANALYSIS.md','''# Exact protocol gap

Source: D:\\WSRTD_PR3_Test_20261010\\releases\\a2401ca\\Binance\\sender.py. record() emits n,d,t,o,h,l,c,v. CandleBuffer.ingest retains E and x in its local seen version but forwards record() without E/x. That per-symbol high-water also rejects older-minute late finals after a newer minute. Historical frames have a separate hist/format/bars envelope. Legacy records cannot be upgraded to V2 by guessing missing E/x.

Relay source: releases\\a2401ca\\Relay\\Server\\Python\\relay.py, configured path protocol. /sender broadcasts bytes to /receiver or /; receiver messages flow upstream. No authentication is supplied by that relay framing. Existing receiver compatibility with new envelopes has not been demonstrated. Do not emit V2 blindly into the shared relay.

Minimum versioned correction: create V2 alongside the exact original Binance event, before legacy record() discards metadata; retain separate per-bucket finality and receipt times. Add authenticated custody/session framing and a separately routed versioned receiver channel, while preserving legacy output. transport.envelope() implements the isolated transformation; it is not deployed into sender.py. No running sender with a compatible alternate output has been verified.

The snapshot records process creation identities, executable/source hashes and sockets. It is point-in-time evidence, not proof of current Binance subscriptions, subscription universe or event freshness. No genuine payload was received. Existing18101 producer remains UNVERIFIED, not automatically INACTIVE.
''')
from transport import FIELDS
properties={k:{'type':'string'} for k in FIELDS}
for k in ('candle_open_time_utc','candle_close_time_utc','exchange_event_time_utc','local_receipt_time_utc'):properties[k]={'type':'integer','minimum':0,'maximum':4102444799999}
properties['schema_version']={'const':2};properties['is_final']={'type':'boolean'}
properties['quote_volume_if_available']={'type':['string','null']};properties['trade_count_if_available']={'type':['integer','null'],'minimum':0};properties['source_event_id_if_available']={'type':'null'}
for k in ('open','high','low','close','base_volume'):properties[k]={'type':'string','pattern':r'^(0|[1-9][0-9]{0,19})(\.[0-9]{1,18})?$'}
put('R2_CANDLE_TRANSPORT_V2_SCHEMA.json',{'$schema':'https://json-schema.org/draft/2020-12/schema','title':'R2 complete candle envelope','type':'object','additionalProperties':False,'required':sorted(FIELDS),'properties':properties,'$comment':'Cross-field validation enforced by transport.py; producer custody is NOT established by schema or MAC. Finality only from k.x. Fixture receiver admits SYNTHETIC_FIXTURE/UNQUALIFIED only.'})
put('R2_SCHEMA_COMPATIBILITY_MATRIX.json',{'legacy_n_d_t_ohlcv':'REJECTED: E/x/session/provenance absent','legacy_hist':'NOT_ADMITTED: independent historical qualification required','binance_full_kline':'offline conversion preserving t,T,E,x and decimal strings; identity roster required','candidate_v2':'PASS_OFFLINE_SYNTHETIC','genuine_v2':'BLOCKED_PENDING_PRODUCER_CUSTODY','UM_CM':'UM/PERPETUAL roster required; explicit CM rejected; absent discriminator relies on qualified roster, never endpoint alone','documentation':'Official legacy Binance documentation URL redirected to generic landing page during lookup. Search-index content supports stream semantics, not complete current schema qualification. Full current production contract still BLOCKED.'})
put('R2_CANDLE_EVENT_VALIDATION_TESTS.json',{'author_evidence':'evidence/AUTHOR_TESTS.json','independent_evidence':'independent/receiver_results.json','author_checks':author['passed'],'independent_receiver_checks':receiver['tests'],'scope':'synthetic semantic validation, not current genuine source schema qualification'})
doc('R2_RECEIVER_IMPLEMENTATION.md','''# Isolated receiver

transport.py converts complete supplied events; no Binance client. SHA256 HMAC authenticates a prebound 32-byte fixture secret and 32-character session; it does not certify Binance custody. Canonical JSON and duplicate-key rejection; 16KiB event bound; decimal strings retained; fixed identity roster; stale/future/replay/cumulative regressions rejected. At most1024 symbols and4 outstanding buckets/symbol. Pending finals backpressure instead of silent eviction. A new session requires a new Receiver instance; no event-controlled rotation.

load_history() reads only disposable SQLite under this output root, schema2/application_id1465074229 and exact context. Missing/changed prior history rejected. SQLite row dominates matching forming data; conflicts fail closed. A live final remains LIVE_FINALIZED_PENDING_STORAGE until an independently supplied matching SQLite row reconciles it. The receiver does not persist finals or provisional data. Durable writer integration remains unimplemented.

fixture_pipe.py publishes bounded little-endian snapshots in a private named pipe rejecting remote clients. Plugin validates exact server PID plus held creation-identity process handle, session and database physical key. Default Windows ACL is not a substitute for producer trust; this is an offline fixture bridge. tests/run_tests.py also passes a V2 authenticated frame through an isolated socket pair. No production18101 connection or full WebSocket deployment adapter exists.

Freshness, missing finals and invalid events exposed by Receiver.status(); those per-symbol diagnostic states are not yet completely exposed through ADK. Native GetPluginStatus stays red/OFFLINE ONLY and never claims live freshness. These are explicit remaining integration gaps.
''')
put('R2_RECEIVER_LIFECYCLE_TESTS.json',{'evidence':['evidence/AUTHOR_TESTS.json','independent/native_results.json'],'tested':['disconnect removes forming','history survives disconnect','unload clears binding','owner creation mismatch','owner PID mismatch','old session','protected database refusal','private UI refresh on disconnect'],'status':'PASS_OFFLINE_TESTED_CASES'})
put('R2_RECEIVER_PROVENANCE_TESTS.json',{'status':'PASS_OFFLINE_REJECTION_ONLY','tests':'independent/receiver_results.json','genuine_custody':'BLOCKED','MAC_alone_is_source_proof':False,'local_receipt_is_exchange_finality':False,'full_prefix_admission':False})
doc('R2_DATA_PLUGIN_V2_CONTRACT.md','''# WFR2 candidate contract

Version50202, ID WFR2, name WSRTD Forming R2 OFFLINE ONLY, x64 ADK Data Plugin. This DLL is deliberately restricted to output-root disposable directories and WFR2_FIXTURE_ONLY=1. It must not be installed into the current Broker. Existing v5.1.0 remains unchanged.

GetQuotesEx periodicity60 copies a bounded coherent snapshot under try_lock, with no SQLite or pipe I/O in the callback. Same-bucket replacement happens before publication; rows strictly ordered, unique per symbol/minute. Insufficient caller capacity fails without writing; there is no truncation or unscoped prior-buffer merge. History in the verified snapshot remains on disconnect; current forming rows expire/remove. Native timestamp conversion is UTC; Quotation fields necessarily narrow preserved decimal values to ADK float.

Full prefix, recent finalized availability, forming availability, native history readback and freshness remain separate. IsBackfillComplete always returns FALSE. No production full-prefix certificate or admission path is implemented. GetPluginStatus is always red, explaining synthetic/unqualified custody. GetRecentInfo returns null rather than inventing tick data. Configure returns0 and never registers/writes symbols. Daily callbacks are not implemented in this R2 fixture candidate and remain a compatibility gap before any replacement.

WFR2_PIPE, WFR2_SESSION, WFR2_OWNER_PID and WFR2_OWNER_CREATION are process-scoped fixture configuration. Database key is obtained independently from Notify directory handle, then matched to snapshot header. Protected or non-disposable paths rejected. No hardcoded production source or database is introduced.
''')
doc('R2_DATA_PLUGIN_V2_IMPLEMENTATION.md','''# Native implementation and limits

native/plugin.cpp builds a distinct DLL. Worker performs cancellable overlapped pipe reads with200ms waits, cancellation completion before OVERLAPPED destruction, fixed maximum65536 snapshot records (~5.8MB), exact owner/session/key validation, monotonically nondecreasing serial/time and equality for same-serial payloads. Worker exceptions fail health closed. State uses guarded cache and atomic lifecycle epoch; callback checks epoch before copying.

Notify owner-thread creates a private message-only timer window, validates same-process main-window/thread/DataSource, and holds a module reference. ADK documents WM_USER_STREAMING_UPDATE=WM_USER+13000 in D:\\WSRTD_N1_AUTOMATIC_REFRESH_20261029_R1\\adk_full\\ADK\\adk.html and QT example. Timer sends synchronously on owning UI thread; freshness transitions trigger invalidation too. At most3 notifications per revision/health change. Wrong-thread/reentrant unload refuses and pins module to avoid live WndProc code unloading. Normal unload joins only its own receiver and removes its own window/property.

R2Metrics counts callbacks/notifications/successes; it is not a complete per-symbol revision acknowledgment ledger. Permanent pin on wrong-thread release favors safety over unloadability; real host lifecycle qualification remains mandatory. Readiness must not be inferred from UI message delivery alone.

Direct SQLite adapter executes outside callback; lifetime-scale history admission exceeds current65536 snapshot bound and is unqualified. No durable final writer, full-prefix attestation integration, real18101 WebSocket ingestion or genuine producer custody exists. These limitations block production substitution despite functioning isolated native merge/refresh.
''')
put('R2_DATA_PLUGIN_NATIVE_API_TESTS.json',{'status':'PASS_OFFLINE_TESTED_CALLBACKS','independent':'independent/native_results.json','checks':len(native['tests']),'actual_amibroker':False,'dll_sha256':native['dll_sha256'],'limitations':['no full real host lifecycle','no daily callback support','no per-symbol acknowledgment completion','fixture-only database scope']})
put('R2_FINALIZED_HISTORY_MERGE_TESTS.json',{'status':'PASS_OFFLINE_TESTED_CASES','evidence':['independent/receiver_results.json','independent/native_results.json'],'durable_final_write':'NOT_IMPLEMENTED','native_array_final_pending_and_SQLite_dedup':'TESTED','historical_prefix':'NOT_ESTABLISHED'})
put('R2_HISTORY_PRESERVATION_MATRIX.json',{'protected_database_writes':0,'protected_sqlite_connections':0,'existing_R1_and_R3_changes':0,'full_prefix_complete':False,'recent_finalized_available':'fixture only; originalR1 two-row observation not refreshed','forming_available':'synthetic fixture only','native_history_readback':'isolated harness only','current_source_freshness':'UNVERIFIED','history_regression_rejection':'independent/receiver_results.json'})
pre=read('R2_PREDECESSOR_INTEGRITY.json');preserved={p:sha(Path(p))==digest for p,digest in pre['sha256'].items()}
put('R2_FINALIZED_STORAGE_NONREGRESSION.json',{'preserved_baseline_hashes':preserved,'all_match':all(preserved.values()),'fixture_sqlite_unchanged_tests':'evidence/AUTHOR_TESTS.json','production_history_writes':0,'not_a_full_historical_integrity_audit':True})
blockers=['Current18101 producer/custody/complete compatible output UNVERIFIED; no connection authorized.',
 'Full current official source schema qualification incomplete; old docs URLs redirect; synthetic semantics not genuine source proof.',
 'Independent final approval pending; tests alone not independent approval.',
 'Real WebSocket18101 adapter, durable final storage writer, full-prefix attestation and production readiness integration unimplemented.',
 'Daily callbacks and complete per-symbol freshness/revision acknowledgment interface absent; offline-only candidate cannot replace v5.1 safely.',
 'Foundational13 exact roster unbound;600 eligible identities not established;13/600 runs synthetic capacity only.',
 'Actual AmiBroker and genuine Binance acceptance not executed.']
doc('R2_NEXT_OPERATOR_AUTHORIZATION.md','''# Next gates, not an execution request

No production action is ready for approval. First close outstanding engineering/review gaps listed in FINAL_DISPOSITION. Existing scope already permits isolated repairs; no new live connection is implied.

The separately approved live gate must designate the exact18101 producer executable/source/config hashes and creation identity; approve its restoration only if necessary, exact V2 output change/routing, one authenticated receiver connection, duration and abort policy. Preserve legacy compatibility and10101/18101 ownership. No parallel Binance source by default. No automated reconnection authority.

After that contract is qualified and a deployable reviewed candidate exists, approve an exact DLL hash, supported loading lifecycle, disposable native database and process-scoped owner/session environment. Keep current Broker running until its lifecycle change is explicitly approved. Never overwrite a loaded DLL. No command in this package installs, restarts or connects to18101.

BTCUSDT thenETHUSDT native acceptance: correlate rawE/t/T/x, receiver snapshot revision, GetQuotesEx timestamps/OHLCV, same-minute replacement, final pending storage, atomic durable commit/readback and refresh callback acknowledgment. Check full-prefix gate separately. Then bound roster13,100,500 and genuinely eligible expansion; never claim600 eligibility from synthetic symbols. Native chart/UI responsiveness and persistence require actual-host evidence.

Rollback boundaries: stop only a separately authorized test receiver; unload/close only an independently qualified disposable host using supported lifecycle; preserve all history/evidence. Current production processes, DLLs, tasks, SQLite and registry are excluded. No force kill or automatic feed restoration.
''')
doc('R2_WINDOWS_CMD_VERIFICATION.md','''# CMD verification

From Windows CMD:

```cmd
py -3.12 -B D:\\WSRTD_N1_DATA_PLUGIN_FORMING_R2\\verify.py
certutil -hashfile D:\\WSRTD_N1_DATA_PLUGIN_FORMING_R2\\artifacts\\WSRTD_Data_Forming_R2.dll SHA256
```

Optional isolated regression commands (create only output-root disposable test directories and own harness processes; no Broker or feed connection):

```cmd
py -3.12 -B D:\\WSRTD_N1_DATA_PLUGIN_FORMING_R2\\tests\\run_tests.py
py -3.12 -B D:\\WSRTD_N1_DATA_PLUGIN_FORMING_R2\\independent\\test_receiver.py
py -3.12 -B D:\\WSRTD_N1_DATA_PLUGIN_FORMING_R2\\independent\\test_native.py
```

Rerunning overwrites test receipts and invalidates their manifest entries; preserve delivered evidence before an authorized new run. No install or live startup command is supplied. prepare.py is not a deployment tool. Candidate requires its isolated fixture authority and rejects the original N1 directory.
''')
put('R2_FINAL_DISPOSITION.json',{'TASK_ID':'WSRTD_N1_DATA_PLUGIN_18101_FORMING_BAR_INTEGRATION_R2','R1_PREDECESSOR_INTEGRITY':'PASS','18101_SOURCE_CHAIN':'BLOCKED','18101_CURRENT_PRODUCER':'UNVERIFIED','18101_METADATA_LOSS_ROOT_CAUSE':'IDENTIFIED','CANDLE_TRANSPORT_V2':'PASS_OFFLINE_SYNTHETIC_ONLY','FINALITY_PRESERVED':'PASS_OFFLINE','EVENT_TIMESTAMPS_PRESERVED':'PASS_OFFLINE','RECEIVER_CANDIDATE':'PASS_OFFLINE_FIXTURE_ONLY','DATA_PLUGIN_V2_NATIVE_API':'PASS_OFFLINE_TESTED_CALLBACKS','FORMING_1M_BTCUSDT':'PASS_OFFLINE','FORMING_1M_ETHUSDT':'PASS_OFFLINE','MINUTE_FINALIZATION':'PASS_OFFLINE_PENDING_STORAGE_ONLY','NATIVE_REFRESH':'PASS_OFFLINE_PRIVATE_WINDOW','FULL_PREFIX_POLICY':'PRESERVED_NO_PRODUCTION_ADMISSION','FOUNDATIONAL_13':'BLOCKED_UNBOUND_ROSTER','SCALE_100':'PASS_OFFLINE','SCALE_500':'PASS_OFFLINE','SCALE_600':'BLOCKED_ELIGIBILITY_UNVERIFIED_SYNTHETIC_CAPACITY_PASSED','SCALE_1024':'PASS_SYNTHETIC','GENUINE_18101_LIVE_RECEIPT':'NOT_EXECUTED','ACTUAL_AMIBROKER_FORMING_BAR':'NOT_EXECUTED','PRODUCTION_DLL_INSTALLED':False,'AMIBROKER_RESTARTED':False,'10101_MODIFICATIONS':0,'18101_MODIFICATIONS':0,'HISTORICAL_DATABASE_MODIFICATIONS':0,'INDEPENDENT_REVIEW':'BLOCKED_FINAL_APPROVAL_PENDING','OVERALL':'BLOCKED_INTEGRATION_AND_FINAL_REVIEW_GAPS','blockers':blockers,'author_checks':author['passed'],'independent_native_checks':len(native['tests']),'dll_sha256':native['dll_sha256']})
if not (R/'R2_INDEPENDENT_FINAL_REVIEW.json').exists():
 put('R2_INDEPENDENT_FINAL_REVIEW.json',{'status':'BLOCKED','reason':'Independent reviewer usage limit before final approval. Author-created status notice, not reviewer approval.','existing_independent_native_checks':len(native['tests']),'native_hash_matches':True,'receiver_hash_matches':receiver['source_sha256']==current_receiver,'evidence':['independent/native_results.json','independent/receiver_results.json']})
doc('README.md','''# R2 isolated data-plugin candidate

Built and exercised: signed complete candle fixture receiver, read-only disposable SQLite merge, distinct x64 Data Plugin, private-pipe custody checks, native GetQuotesEx and lifecycle-scoped refresh in an isolated ADK harness. Author2310 checks and independent26 native/16 receiver checks are available. See FINAL_DISPOSITION for exact source-hash/current-review scope.

Not production-ready: no qualified live18101 source, durable final writer, full-prefix production admission, daily callback parity or actual AmiBroker acceptance. No production deployment performed. This is implementation evidence, not another architecture-only plan or live acceptance.

Artifacts: artifacts/WSRTD_Data_Forming_R2.dll; native/plugin.cpp; transport.py; fixture_pipe.py; tests/; independent/; complete GateA-H reports. R2_RESOURCE_MEASUREMENTS contains actual short-window500/1024 measurements, not lifetime capacity proof.
''')
print('evidence package written; overall BLOCKED, no release promotion')
