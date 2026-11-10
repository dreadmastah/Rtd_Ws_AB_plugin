from pathlib import Path
import json,hashlib,sys,datetime
R=Path(__file__).parent;P=Path(r'D:\WSRTD_N1_DATA_PLUGIN_FORMING_R3')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(n,o):(R/n).write_text(json.dumps(o,indent=2),encoding='utf-8')
def doc(n,s):(R/n).write_text(s,encoding='utf-8')
def read(n):return json.loads((R/n).read_text())
pre=read('R4_PREDECESSOR_INTEGRITY.json');assert all(sha(P/n)==v for n,v in pre['hashes'].items())
tests=read('evidence/AUTHOR_TESTS.json')
doc('R4_18101_ACTIVATION_CORRECTION.md','''# Bounded candidate activation

src/admission.py provisions a new exclusive disposable SQLite budget ledger. Startup requires an existing exact contract/session ledger; it never recreates lost state or generates replacement authority. Every dispatch consumes aggregate counters inside BEGIN IMMEDIATE before backend invocation; exceptions do not refund attempts. Exceeded caps, time regression/expiry and custody mismatch latch STOP durably. Restart reads consumed counters and cannot enlarge the contract. Explicit shutdown also latches STOP. No fallback to legacy startup.

Allowlist limited to at most BTCUSDT/ETHUSDT; initial proposed livepilot BTCUSDT only. Controller binds producer session, receiver session, receiver PID/creation declaration and universeversion. These are compared as exact inputs, not independently authenticated OS custody or operator approval. Ledger filesystem custody/trusted clock across process downtime are not qualified production controls. Contract is not a signed execution authorization.

Existing18101 supervisor requires exact installedBroker with an established18101 connection, then launches fixed500symbol sender with nativehistory/quotes. Helperreceiver cannot satisfy that predicate; Brokerreceiver can trigger unbounded REST/reconnect acquisition. This isolatedcontroller does not modify or control that supervisor. A separately reviewed controller replacement or routedadapter remains necessary. No safe live swap is authorized.

src/sender.py centralizes metadata/history/connection/subscription/frame callsites and has no automatic retries. Backend is exact FixtureBackend only: it performs no HTTP, DNS, TLS or WebSocket traffic. Therefore actual production network enforcement and one-shot genuine activation remain BLOCKED. This package supplies working offline policy/metadata code, not a claimed deployable network engine.
''')
put('R4_BOUNDED_NETWORK_ADMISSION.json',{'implementation':'src/admission.py','maturity':'OFFLINE_CONTROLLER_ONLY','persistent_consumption':True,'failed_attempt_refund':False,'caps':['RESTrequests','RESTweight','connectionattempts','subscriptioncount','reconnectattempts','frames','bytes','UTCendtime','processmonotonicelapsed'],'no_rest':'zero request/weight denies metadata andkline paths','endpoints':['/fapi/v1/exchangeInfo','/fapi/v1/klines','wss://fstream.binance.com/market/ws'],'weight_model':'offline fixture assumption metadata1;kline<100=>1,100..499=>2; current official/live weight authority unqualified','backend':'FixtureBackend only','production_network_enforcement':'BLOCKED_NO_QUALIFIED_REAL_BACKEND','clock_limit':'wallrollbackbelowlastseen rejected; downtime rollback cannot be proven without trusted clock authority','watchdog':'optional fixtureownthread; actual socket lifetime cancellation not qualified'})
doc('R4_SENDER_V3_IMPLEMENTATION.md','''# Sender-to-receiver V3 metadata

src/sender.py validates subscribedsymbol and pipeline producer/session/universe/symbolset, rejects duplicateJSONkeys and nonobjectroot, and passes complete supplied sourceevent into unchanged R3 Pipeline.encode. It retains raw x/E/t/T/OHLCV/volume/count and optionalraw fields. No nextminute or wallclock finalization inference. IsolatedRelay validates exact declared custody plus receiverpipeline before exact-byte handoff. R3validates reconstructedcandle/rawlinkage and atomically persists receipt with finalrow.

V3 sourceevent encoding remains SYNTHETIC_FIXTURE through the unchanged R3 receiver. This cannot accept or attest genuine Binance custody. No localHMAC or newproducer label promotes trust. Missingevent fields reject. RESTmetadata fixture does not produce a verified universe; allowlist is an explicit testinput. A real networkadapter, TLSprovenance and OSprocess custody verifier are not supplied and remain required.

No running sender changed. src/admission.py and sender.py are versioned Python source, not standalone compiledbinaries. Exact Python executable hash is recorded in the sourceinventory; no senderbinary is invented. R3nativeDLL unchanged.
''')
for name in ('R4_METADATA_ROUNDTRIP_TESTS.json','R4_TWO_SYMBOL_INTEGRATION.json','R4_REST_WS_BUDGET_REGRESSION.json'):
 put(name,{'author_evidence':'evidence/AUTHOR_TESTS.json','author_checks':tests['tests'],'passed':tests['passed'],'source_event_kind':'synthetic Binance-shaped fixtures','actual_network':False,'actual_amibroker':False,'scope':'counteradmission/session/restart and two-symbolforming/final/duplicate/durable receipt handoff; not genuine network'})
put('R4_DURABLE_HANDOFF_NONREGRESSION.json',{'dependency_hashes_match':all(sha(R/'dependencies/r3'/n)==v for n,v in pre['dependency_copies'].items()),'R3_manifest_unchanged':True,'two_symbol_committed_rows':'tested','duplicate_commit':'idempotent','full_prefix':'remainsfalse','production_storage_writes':0})
put('R4_WEEKLY_MIXED_INTERVAL_RESULTS.json',{'weekly':'BLOCKED_ACTUAL_HOST_COMPRESSION_REQUIRED','mixed':'BLOCKED_ACTUAL_DATABASE_SETTINGS_AND_CALLBACK_ORDER_REQUIRED','UTCdaily':'R3unchanged36independentnativechecks; complete1440durableminuteaggregation; partialdayrejected in R4handoff','R3_evidence_sha256':sha(P/'independent/native_results.json'),'R4_native_tests_repeated':False,'actual_host_operation':False})
put('R4_NATIVE_REFRESH_QUALIFICATION.json',{'status':'PASS_OFFLINE_INHERITED_R3_PRIVATE_WINDOW_ONLY','actual_chart':'NOT_EXECUTED','genuine_event_native_binding':'BLOCKED','DLL_sha256':pre['dll_sha256'],'full_prefix_policy':'PRESERVED_FAIL_CLOSED','no_R3_rebuild':True})
sys.path.insert(0,r'D:\WSRTD_N1_ACTIVE_CHART_RADAR_R1\retirement_controller_r1');import r3_observer as obs
baseline=json.loads((P/'R3_PROTECTED_RUNTIME_BASELINE.json').read_text());after=[]
for b in baseline['processes']:
 try:
  with obs.opened(b['pid']) as h:pid,created,exe=obs.handle_identity(h)
  after.append({'pid':pid,'creation':created,'matches_R3_observation':created==b['creation_filetime'],'exe':exe})
 except OSError as exc:after.append({'pid':b['pid'],'unavailable':str(exc)})
put('R4_PROTECTED_RUNTIME_NONINTERFERENCE.json',{'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'processes':after,'listeners10101':obs.listeners(10101),'listeners18101':obs.listeners(18101),'process_control_operations':0,'productionconnections':0,'installedDLLwrites':0,'historicalDBwrites':0,'R3_manifest_unchanged':True,'scope':'taskoperationcounts andpointintimeidentity; no blanket marketdatacontinuity claim'})
doc('R4_FIRST_GENUINE_BTCUSDT_PILOT.md','''# First genuine pilot: BLOCKED, not executable

Proposed symbol BTCUSDT only. No automaticETH or500expansion. Suggested policy to review: zeroREST, oneWSconnectionattempt, oneBTCUSDT@kline_1msubscription, zero reconnect, at most120seconds. These are proposed bounds, not an approvedUTCwindow or shared-IPreservation. UTCstart/end UNBOUND. A qualified current symbolmetadata snapshot and actualUMidentity are necessary for zeroRESTadmission; absentmetadata stops.

Producer implementation: src/admission.py + src/sender.py hashes in manifest; Pythoninterpreter hash inventoried. Actual networkbackend/sender executable: UNBOUND (fixture backend only). Receiver: unchangedR3 Pipeline dependency plus declared-session checks; genuinecustody/OSreceiverattestation UNQUALIFIED. DataDLL: unchangedR3 f0b09413fa555ea85781b8745fc6c1108e6edf7f6189fa00bfdc35e098d77647; fixture-only, not genuine-source-ready.

Disposablepilotdatabase would be newly provisioned under R4output; exactphysicalidentity/writer/session must be bound beforeauthorization. No originalhistorycopy/migration. CurrentBroker staysrunning; no supported loading/lifecycle authority has been granted. R3DLLcannot be turned into productioncandidate merely by setting an environmentvariable. Nativeweekly/mixedsettings and genuinequote binding require an independently approved hosttest.

Existing18101 cannot be used by connectingBroker under this policy: currentreceiverpredicate can start500sender+RESTrehydration. An external helper does not satisfy predicate. Required route is a separately reviewed versionedproducer/controller adapter with realIO hardcaps and legacyreceiver compatibility, with explicit handoff approval. Do not reconnect or replace it now.

Future actualevidence must bindTLS/endpoint,rawE/t/T/x/UMidentity,receipt/session/universe,exactOHLCV,commitreceipt,GetQuotesEx timestamp/value and nativechartupdate. LocalMAC/digest andsynthetictests are not sourceproof. Abort on limit/time/session/sourcegap/invalidfinal/storagefailure/hostmismatch/protectedfeedchange. Close only authorized testowned transport/coordinator gracefully; retaincommitteddata andreceipts; nofallbacklegacyrestart andnoautomaticreconnect.
''')
doc('R4_NEXT_OPERATOR_AUTHORIZATION.md','''# Remaining engineering and authorization

No execution approval is requested yet. Working offlinecounter/controller andV3handoff do not qualify genuinebackend or current18101replacement.

First implement/review realbounded networkcalls, TLS/source/OSreceivercustody, accepted genuineprovenance admission, sourcecompatible18101handoff and deployable native lifecycle. Preserve fullprefix separation. Actualweekly/mixedinterval gates need isolated AmiBroker authorization; currenthost unchanged.

Then approval must bind exact producer/sender/receiver/runtime/DLL hashes, BTCUSDTonly, noRESTor exactRESTranges+requestweights, connection/subscription/retrycaps, UTCstart/end, processcreationidentities, disposableDBwriter, permittedhostlifecycle andcleanup. ZeroRESTmust reject metadata discovery/repair/commands as well aspreload. Never authorize an unbounded legacy fallback by implication.
''')
doc('R4_WINDOWS_CMD_VERIFICATION.md','''# CMD verification

```cmd
py -3.12 -B D:\\WSRTD_N1_DATA_PLUGIN_FORMING_R4\\verify.py
py -3.12 -B D:\\WSRTD_N1_DATA_PLUGIN_FORMING_R3\\verify.py
```

Optionalnewoffline test (creates onlyR4disposableledgers/databases; overwritesR4testreceipt, requiringnewmanifest):

```cmd
py -3.12 -B D:\\WSRTD_N1_DATA_PLUGIN_FORMING_R4\\tests\\test_r4.py
```

No liveproducer/receiverconnect/install/start command is included because those gates remainblocked. Do not rerun prepare.py overaccepted artifacts.
''')
put('evidence/PYTHON_RUNTIME.json',{'path':sys.executable,'sha256':sha(Path(sys.executable)),'source_delivery':True,'standalone_sender_binary':'NOT_BUILT'})
print('reports prepared; waiting final review')
