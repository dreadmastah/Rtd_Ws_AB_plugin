from pathlib import Path
import json,hashlib,shutil,sys,datetime
R=Path(__file__).parent;P=Path(r'D:\WSRTD_N1_DATA_PLUGIN_FORMING_R2')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def put(n,o):(R/n).write_text(json.dumps(o,indent=2),encoding='utf-8')
def doc(n,s):(R/n).write_text(s,encoding='utf-8')
def read(n):return json.loads((R/n).read_text())
paths=[Path(r'D:\WSRTD_PR3_Test_20261010\persistent-feed-20261010\supervise_test_feed.py'),Path(r'D:\WSRTD_PR3_Test_20261010\releases\a2401ca\Binance\sender.py'),Path(r'D:\WSRTD_PR3_Test_20261010\releases\a2401ca\Relay\Server\Python\relay.py'),Path(r'D:\WSRTD_PR3_Test_20261010\persistent-feed-20261010\selected-symbols.txt')]
put('R3_SOURCE_CHAIN_PROVENANCE.json',{'source_sha256':{str(p):sha(p) for p in paths},'production_changes':0,'live_output_observed':False,'running_sender':'not started by task'})
sys.path.insert(0,r'D:\WSRTD_N1_ACTIVE_CHART_RADAR_R1\retirement_controller_r1');import r3_observer as obs
ps=[]
for pid,b in obs.nt_processes().items():
 if b['image'].lower() not in ('broker.exe','python.exe','pythonw.exe'):continue
 try:
  with obs.opened(pid) as h:
   ident=obs.handle_identity(h);args=obs.arguments(h)
  if not any(x in ' '.join(args).lower() for x in ('18101','10101','supervise_test_feed','broker.exe')):continue
  ps.append({'pid':pid,'parent':b['parent'],'creation_filetime':ident[1],'executable':ident[2],'executable_sha256':sha(ident[2]),'arguments':args})
 except (OSError,ValueError,RuntimeError):pass
put('R3_PROTECTED_RUNTIME_BASELINE.json',{'observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'processes':ps,'listeners10101':obs.listeners(10101),'listeners18101':obs.listeners(18101),'controls_executed':0,'connections_opened':0})
doc('R3_18101_ACTIVATION_STATE_MACHINE.md','''# Exact configured18101 activation

Entrypoint D:\\WSRTD_PR3_Test_20261010\\persistent-feed-20261010\\supervise_test_feed.py; --root binds releases/a2401ca and --runtime binds persistent-feed-20261010. selected-symbols.txt is the pinned500 configuration, not current eligibility proof. Source hashes and current process identities are in SOURCE_CHAIN_PROVENANCE and PROTECTED_RUNTIME_BASELINE.

IDLE: supervisor owns relay; no qualifying native receivers => sender None. Every5seconds native_receivers scans exact installed C:\\Program Files\\AmiBroker\\Broker.exe and an ESTABLISHED remote18101 socket. A helper/WebSocket client alone does not satisfy it.

RECEIVER_CONNECTED: sorted(pid,creation) list nonempty. SENDER_STARTING follows absent/exited sender or changed receiver list. It may stop a previous sender first. Fixed args --symbols selected-symbols.txt --limit500 --relay ws://127.0.0.1:18101/sender --native-history --quotes.

Discovery REST exchangeInfo validates pinned identities. Rejection => DEGRADED, no genuine streaming. Historical log reports invalid pinned names; that is not current discovery authority. Successful discovery launches market/public WebSocket shards. REST_REHYDRATION and WEBSOCKET_LIVE may overlap; they are not an unconditional linear success chain. Preload1500closed1m/300daily each symbol; commands/reconnect/gap/rollover can addREST. RELAY_ACTIVE merely means output transport; it does not prove history, finality or native receipt. Receiver loss => DISCONNECTED and sender stop; relay restart or receiver identity changes can rebuild/rehydrate.

No production no-REST admission mode exists. Omitting native-history removes preload/stale/rollover paths but not initial exchangeInfo, gap repair, reconnect repair or command history. New src/pipeline.py Budget implements offline exactint, synchronized, aggregate request/weight/deadline admission and zero-request denial. It is not wired into the installed sender and cannot limit its production requests.

Future compatible event sequence requires qualified receiver identity and explicit authority for the resulting sender/REST effects OR reviewed versioned controller/output changes for an external adapter. Do not use a new connection as a passive diagnostic.
''')
put('R3_PRODUCER_STARTUP_AND_REST_BUDGET.json',{'activation_contract':'QUALIFIED_SOURCE_ONLY','configured_symbols':500,'nominal_market_ws':5,'nominal_public_ws':5,'subscriptions_with_quotes':1500,'initial_exchange_info_requests':1,'preload_per_symbol':{'minute_rows':1500,'daily_rows':300,'max_page':499,'nominal_kline_pages':5},'nominal_preload_kline_requests':2500,'unbounded_paths':['six_attempt_request_retries','preload_retry_loop','commands','reconnect','gap_repair'],'aggregate_production_budget':'BLOCKED','candidate_budget':'src/pipeline.py Budget, offlineonly; zeroREST denies every reserve','fullprefix_limit':'legacy repair truncates to configured1500m/300d orhistory_days; not complete since listing','request_weight_authority':'requires contemporaneous official endpoint weight verification and shared-IP allocation; no reservation made'})
put('R3_CANDLE_TRANSPORT_V3.json',{'schema_version':3,'envelope':['schema_version','universe_version','source_event','candle'],'inner_candle_fields':'src/transport.py FIELDS','raw_event':'preserved verbatim JSON fields; linked by reconstruction againstcandle','MAC':'HMACSHA256 of canonical wrapper; fixturesecret is not Binance custody','durable_receipt':'receipts table retains fullwrapper JSON+SHA256 atomically with newfinal','duplicate_policy':'first committed event receipt retained; equalOHLCV replay idempotent','maturity':'SYNTHETIC_FIXTURE_ONLY; genuine custody verifier unavailable'})
doc('R3_SENDER_RECEIVER_CORRECTION.md','''# Versioned correction

src/pipeline.py encode/receive retains original source_event, universeversion, session and explicitV3 wrapper. Inner candle carries E,t,T,x,decimalOHLCV/basevolume,optionalquotevolume/tradecount and null eventID where absent. No timestamp or finality is inferred. Full wrapper is persisted atomically for newly committed finals. Receiver rejects corruptMAC/version/universe/raw linkage, invalidbody and stale sessions. No running sender source is edited.

This is a callable offline adapter, not a deployed WebSocket transport or Binance acquisition process. Existing18101 legacy fields cannot be converted losslessly after E/x discard. A versioned producer correction must occur before record() and must retain legacy receiver compatibility. Actual producer custody and complete current UM/CM metadata qualification remain blocked.
''')
put('R3_METADATA_NONLOSS_TESTS.json',{'source':'R3_END_TO_END_EVENT_REPLAY.json','raw_receipt_persisted':True,'genuine_provenance':'BLOCKED','precision_regression':'R3_SQLITE_TRANSACTION_ACCEPTANCE.json test_precision','full_current_exchange_schema_qualification':'BLOCKED','synthetic_only':True})
doc('R3_DURABLE_STORAGE_CONTRACT.md','''# Disposable durable finalization

src/durable.py uses SQLite WAL+synchronousFULL and BEGIN IMMEDIATE. Exact(scope,symbol,UTCminute,interval) context, ownergeneration/session check inside transaction, immutable exact-decimal values, event SHA256 plus fullV3 receipt for integrated path, checkpoint advance atomically committed. Claim increments generation; stale owner commits fail. Identical values idempotent; conflicts reject. Forming events cannot commit. Process-crash tests use only disposable child os._exit before/afterCOMMIT. Not power-loss evidence.

Only output-root disposable DBs admitted. Existing scope/schema is read-only checked before write pragmas. No production migration exists. New DB initialization is not a cross-process exclusive provisioning service; production filesystem custody, atomic initialization and hardened schema/ACL checks remain separate gates. Direct low-level Store tests may omitV3receipt; integrated Pipeline persists it. Genuine custody always rejected; localchecksums cannot grant source authority.

Pipeline reports LIVE_FINALIZED_NOT_YET_DURABLE on storagefailure, then suppresses healthy forming snapshot until successful recovery. Durable rows restored and ledger hash/value linkage checked on reads. No archived/backfill source is relabelled asWS. Only synthetic source fixtures currently admitted.
''')
shutil.copy2(R/'R3_SQLITE_TRANSACTION_ACCEPTANCE.json',R/'R3_CRASH_RECOVERY_AND_IDEMPOTENCY.json')
bootstrap=Path(r'D:\WSRTD_N1_POST_R3_FULL_PREFIX_BOOTSTRAP_20261102_R2')
put('R3_FULL_PREFIX_NONREGRESSION.json',{'references':{str(bootstrap/n):sha(bootstrap/n) for n in ('IMPLEMENTATION_REPORT.md','FINAL_DISPOSITION.json','src/handoff.py','src/coverage.py')},'archive_admission':'still denied by governing require_r3_admission','newcoverage':'exactlisting-ceiling/minuterecurrence, localledger linkage only','structural_complete_not_provenance':True,'full_prefix_qualified':False,'production_changes':0})
doc('R3_HISTORY_TO_LIVE_HANDOFF.md','''# Full-prefix handoff remains fail-closed

Reused governing contracts: D:\\WSRTD_N1_POST_R3_FULL_PREFIX_BOOTSTRAP_20261102_R2\\src\\handoff.py and coverage.py. Existing require_r3_admission always rejects absent qualified archive custody. No adapter may turn archive checksum, synthetic fixture or localreceipt into REST_TLS or Binance proof.

Proposed segments: archive prefix with qualified listing/cutoff -> separately authorized exact REST gap pages(max499) -> immutable previouslycommittedfinals -> exchangefinal live events -> transientforming. Exact minute key deduplicates boundaries; conflicts reject, missingminute staysgap. Newcoverage validates listingceil and cutoff recurrence against durableledger, but verifiedprovenance/fullprefix/liveReady stayfalse. R3doesnot silently weaken complete-since-listing into recentwindow.

No production backfill. Actual listingdate, complete archiveinventory, sourcecustody, qualified cutoff and admissionauthority are missing. Integration into the existing archiveStore is not implemented; new Store is independent disposablefixture. Preserve originalN1 and all archive artifacts.
''')
put('R3_HISTORY_GAP_AND_REPLAY_TESTS.json',{'evidence':['R3_SQLITE_TRANSACTION_ACCEPTANCE.json','R3_END_TO_END_EVENT_REPLAY.json'],'tested':['missingminute refusesstructuralcomplete','latefinal closesexactgap','replayidempotent','corruptedledger fails','prefixqualification remainsfalse'],'archive_handoff_execution':'NOT_IMPLEMENTED'})
doc('R3_REHYDRATION_AUTHORIZATION_REQUIREMENTS.md','''# No production REST authorization

Initialsymbol BTCUSDT only; ETHUSDT separate after pass. Exactperiod listingceil through approvedfinalcutoff must be independently bound, excluding alreadyqualified archived ranges. Planner src/pipeline.py plan gives exact startTime/endTime/limit<=499, max600000minutes percall. Limits inheritedbootstrap600000rows/16sources are not lifetime500symbol proof. Actual requestcount cannot be specified until authoritative gaps are available.

Operator must separately bind metadata and history endpoints, exactpagecount, shared-IP requestweight allocation, connection/retry ceilings, UTCstart/end, persisted checkpointnamespace and resumeauthority. Budget check is aggregate and failclosed but no real network implementation has been authorized. ZeroREST mode in candidate denies allrequests; installedsender has no equivalent guarantee. Rollback preserves committedhistory and quarantines/conflicts rather than deletingdata. Existing10101/18101services must not be reconfigured implicitly.
''')
doc('R3_AMIBROKER_NATIVE_CALLBACK_CONTRACT.md','''# Native contract and unproven host gates

Verifiedlocal ADK from R2dependencies Plugin.h/legacy: GetQuotesEx(periodicity60 or86400), Quotation40bytes x64, DAILY_MASK0x000007FFffffFFC0, GetSymbolLimit, Notify and WM_USER_STREAMING_UPDATE=WM_USER+13000. R3retains owner-thread synchronousnotification/privatewindow lifecycle and worker cachepublication. Allcallback tests run in isolatedPython/C++processes, neverBroker.

New daily callback aggregates only1440unique DURABLE1mrows within UTC00:00..23:59. Missingminute or pending/ forming exclusion leaves daily absent. ADKdaily mask used. Weekly directperiod604800 unsupported; weekly compression belongs to host and remains unqualified. MixedEOD/intraday actualsettings and time-shift are not attested; do not reuse oldscreenshots as currentproof or modifysettings. No actual native chart success claimed.

Snapshot total65536row bound remains. Full-history reading/sustainable500symboldailydata may exceed it; actual lifetime capacity blocked. Daily aggregation occurs in bounded callback but worstcasecallbackresource profile still needs qualification before deployment. Originalcallerbuffer is not merged acrossunbounddatabase. Fullprefix authority remains false; fixture-only path gate retained.
''')
native=read('evidence/native_results.json')
put('R3_DAILY_INTRADAY_COMPATIBILITY.json',{'daily_complete1440UTC':'PASS_OFFLINE','daily_gap':'PASS_OFFLINE_REJECT','DAILY_MASK':'PASS_OFFLINE','weekly_host_compression':'BLOCKED','mixed_host_settings':'BLOCKED_UNATTESTED','Windows_local_not_boundary':True,'evidence':'evidence/native_results.json'})
put('R3_NATIVE_REFRESH_ACCEPTANCE.json',{'status':'PASS_OFFLINE_PRIVATE_WINDOW','evidence':'evidence/native_results.json','actual_chart_refresh':'NOT_EXECUTED','notification':'WM_USER+13000 owner-thread synchronous; bounded3retries/revision','genuine_commit_to_chart_latency':'NOT_MEASURED'})
put('R3_NATIVE_API_INDEPENDENT_TESTS.json',{'author_inherited_checks':len(native['tests']),'author_pass':native['passed'],'independent_final':'PENDING','actual_host':False})
doc('R3_DATA_PLUGIN_CANDIDATE_BUILD.md','''# Distinct candidate

artifacts/WSRTD_Data_Forming_R3.dll; WFR3version50303. BuiltMSVCx64 against preservedADK. MaturityFIXTURE_ONLY. Callable V3metadataadapter and disposabletransactional storage implemented; genuine custody not admitted. Native1m/daily tests are offline, weekly/mixedhost unknown. Not deployable and not ready for livepilot. No installedDLL/R2binary changes.
''')
doc('R3_FIRST_GENUINE_SOURCE_PILOT.md','''# Pilot BLOCKED pending engineering and explicit execution authority

TargetBTCUSDT only, ETHUSDT after native/source pass. Current18101 uses pinned500, nativeBrokerpredicate, and unbounded preload/retries. ConnectingBroker may cause500symbolREST/WSacquisition; helperconnection will not trigger predicate. Neither is a qualifiedone-symbolpilot.

Beforeapproval: versionedproducer/controller must limituniverseBTCUSDT, preserveV3metadata, enforce request/connection/deadlinecaps acrossdiscovery/preload/repair/commands/retry, and provide custody binding. Actual hashes for that runnable networkcomponent are UNBOUND; offline src/pipeline.py is not its substitute. Existing source hashes/process identities are evidenceonly, not retirementauthority. No parallelfull-marketstreamer.

ExactRESTsymbols/ranges/count/weight and UTCobservationwindow remain UNBOUND until qualifiedhistoricalgaps and shared-IPallocation exist. Do notinvent budget. ExistingBroker staysrunning; candidateinstallation/restart/loading lifecycle requires laterindependentqualification and approval. R3DLL currentlyrejects productionDB and cannot be enabled just by approvingcopy.

Nativepilot after gates: verifycandidate+producerhashes, sameprocessdatabase/source custody, genuineE/t/T/xandOHLCV linkage, two observedcurrentminuteupdates, finalcommit+readback, refreshack/chart, ETHthen. Abortonwrongsession/database,missingfinal,staleness,writefailure,unexpectedrequests,protectedfeedstatechange. Gracefully stoponlytest-ownedresources; noautoRESTrecovery or broadprocesstermination. Committedhistory retained; nooverwrite/deletion. No trading.
''')
doc('R3_EXACT_OPERATOR_AUTHORIZATION.md','''# Execution authorization not yet solicited

Required separate approvals aftertechnicalclosure:

- Exact reviewed producer/controller/sender change and custody, boundedBTCUSDT-onlyactivation, REST/WSrequest/weight/connection caps andUTCwindow.
- One qualified receiver connection and its sideeffects; existing18101controller currentlycan start/restart/rehydratesender onBrokerreceiverchanges.
- Exact reviewed deployableDLLhash and supported hostlifecycle. CurrentBrokerrestart, installedDLLreplacement and currentdatasourceswitch remain prohibited.
- ExactdisposablepilotDB/writeridentity, durablewrites scopedthere only; noexistinghistorymutation.
- Test-ownedgracefulcleanup; independent10101/18101restoration actions remainexcluded.

Runnableproductiontransaction is BLOCKED. No command in this package starts/ connects/ installs/ restarts anythingproduction.
''')
doc('R3_WINDOWS_CMD_VERIFICATION.md','''# Windows CMD

```cmd
py -3.12 -B D:\\WSRTD_N1_DATA_PLUGIN_FORMING_R3\\verify.py
certutil -hashfile D:\\WSRTD_N1_DATA_PLUGIN_FORMING_R3\\artifacts\\WSRTD_Data_Forming_R3.dll SHA256
```

Optionalnewisolatedregression (rewrites R3receipts; invalidatesmanifest, preservesR2/production):

```cmd
py -3.12 -B D:\\WSRTD_N1_DATA_PLUGIN_FORMING_R3\\tests\\test_durable.py
py -3.12 -B D:\\WSRTD_N1_DATA_PLUGIN_FORMING_R3\\tests\\test_pipeline.py
py -3.12 -B D:\\WSRTD_N1_DATA_PLUGIN_FORMING_R3\\tests\\test_native_inherited.py
py -3.12 -B D:\\WSRTD_N1_DATA_PLUGIN_FORMING_R3\\tests\\test_integrated_scale.py
```

Noinstallation/livecommands. prepare.py/stage_native.py are one-time derivation helpers; do not rerun over finalsource.
''')
print('Gate reports written; final disposition awaits final review')
