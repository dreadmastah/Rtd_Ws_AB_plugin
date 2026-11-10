from pathlib import Path
import json,hashlib,datetime,sys
R=Path(__file__).resolve().parent
review=json.loads((R/'R6_INDEPENDENT_FINAL_REVIEW.json').read_text())
for name,digest in review['hashes'].items():
 assert hashlib.sha256((R/name).read_bytes()).hexdigest()==digest,('review drift',name)
assert not (R/'R6_SOURCE_BINARY_SHA256_MANIFEST.json').exists(),'package already materialized'
def read(n):return json.loads((R/n).read_text())
def put(n,v):(R/n).write_text(v if isinstance(v,str) else json.dumps(v,indent=2),encoding='utf-8')
e2e=read('R6_END_TO_END_V3_PIPELINE.json');timing=read('R6_TIMEOUT_ROOT_CAUSE_AND_REGRESSION.json')
put('R6_ENDPOINT_ADMISSION_POLICY.json',dict(version=1,status='BLOCKED_EXTERNAL_SOURCE_ADMISSION',implementation='src/endpoint_policy.py',local_validation=read('R6_ENDPOINT_NEGATIVE_TESTS.json'),external_dispatch=False,approved_external_identities=[],protocol_document_authority='UNBOUND',enforced=['exact scheme/host/port/path','TLS certificate and hostname','literal connect pin after IPv4 DNS check','no proxy inheritance','no redirect or automatic retry','persistent pre-dispatch budget','protected ports rejected'],limitations=['DNS getaddrinfo is blocking and cancellation bound unqualified','protocol_evidence_sha256 validates syntax only, not authoritative document custody','localhost loopback enforcement is not production Binance endpoint qualification','external network remains prohibited']))
put('R6_WINDOWS_PROCESS_CUSTODY.json',dict(status='PASS_ISOLATED_PROCESS_OBSERVATION_ONLY',relay=e2e['relay_identity'],relay_port=e2e['relay_port'],tls_and_process_tests=read('evidence/TLS_CUSTODY.json'),controller_tests=read('evidence/CONTROLLER.json'),actual_peer_tuple_to_pid=False,production_authority=False,limitations=['Relay child PID creation image attested through Windows handle; script identity separately manifest-bound','role authentication proves inherited-secret possession, not Windows socket peer PID','producer and receiver remain in controller process in harness','Genuine source authority absent']))
put('R6_V3_RELAY_IMPLEMENTATION.md','''# R6 independent relay

The tested path is actual loopback WebSocket -> admitted backend -> TCP sender -> separate Python relay process -> TCP receiver -> R3 forming/durable pipeline -> named pipe -> compiled R6 DLL. It does not use the direct Handoff path to qualify relay integration.

Both relay ingress and receiver validate HMAC, canonical JSON, schema, source/session/universe generation, sequence, receipt, raw-source linkage, USD-M symbol, finality, UTC minute and OHLCV. The relay commits receipt/sequence/hash before forwarding and waits for the receiver acknowledgment. The receiver commits finalized history before acknowledgment. Corrupt, duplicate, truncated, oversized, stale, replayed and mismatched frames close the session. Restart uses a new generation and new ledger; old generation replay is rejected. This is not automatic crash-resume or exactly-once recovery.

Each frame has a 3-second aggregate read deadline. Startup readiness is bounded; partial failure cleanup only controls the exact test-owned Popen child and sockets. Normal cleanup closes sockets and waits; an unresponsive test child may be terminated by its owned process handle. No production process is controlled. Delivery failure marks the receiver disconnected. Idle relay-death propagation still needs an independent lifecycle monitor; native five-second freshness remains a separate safeguard.

Source provenance stays SYNTHETIC_FIXTURE. Key possession is not genuine Binance custody or OS TCP peer ownership. No source-prefix certificate exists. Prior native failures and their partial diagnosis are retained in evidence/NATIVE_FAILURE_HISTORY.json. The revised interleaved fixture passes fresh and explicitly disconnected readback without changing freshness thresholds. Same-forming-minute-to-finalized transition at a real minute boundary remains an additional targeted integration gap; the present native fixture uses a previous finalized minute and current forming updates.
''')
put('R6_FIRST_GENUINE_BTCUSDT_PILOT.md','''# First BTCUSDT pilot: BLOCKED, not executable

R6 qualifies an isolated relay/native path, not genuine-source or host activation. Before a live approval request: qualify official endpoint identities and protocol-document custody; implement bounded DNS and external endpoint enforcement; bind actual producer/controller/relay/receiver authority and transport peers; close idle-disconnect and same-minute-finalization coverage; establish full-prefix admission; qualify an isolated AmiBroker lifecycle without changing 10101/18101.

The minimum proposed future scope is BTCUSDT only, no REST unless explicitly authorized, one WS connection and one subscription, zero reconnects, operator-set UTC window and duration. These are proposals, not granted budgets. Bind exact executable/script/DLL hashes, process creation identities, source/universe generation, permitted endpoint, disposable database physical identity and writer authority. Capture original source payload, receipt, durable commit and native callback/chart timestamp/OHLCV linkage.

Abort on identity loss, unexpected address, request/reconnect, budget/deadline failure, source/finality mismatch, historical conflict or stale native data. Cleanup only the qualified test-owned cohort. Do not reconnect production services. DLL installation, host lifecycle and data-source selection each remain separately authorized actions. Current R6 DLL is OFFLINE ONLY and is not a deployable genuine-source plugin.
''')
put('R6_EXACT_OPERATOR_AUTHORIZATION.md','''# No execution approval requested yet

Mandatory fields remain UNBOUND: official HTTPS/WSS identity and source authority; producer/controller/relay/receiver exact hashes and PID/creation; OS transport-peer custody; UTC start/end; request/weight/connection/subscription/frame/byte ceilings; disposable writer identity; full-prefix qualification; actual AmiBroker lifecycle; cleanup scope.

R6 source/binary manifest is engineering evidence only. Do not approve a network or installation command against it. No Binance requests, 10101/18101 changes, installed DLL writes or Broker restarts were performed. Once remaining implementation and authority gates close, supply a new exact-action BTC-only authorization sheet. No ready-to-run live command is invented here.
''')
states=dict(TASK_ID='WSRTD_N1_DATA_PLUGIN_R6_V3_RELAY_AND_SOURCE_ADMISSION',R5_PREDECESSOR_INTEGRITY='PASS',TIMEOUT_1_5S_REGRESSION='PASS' if timing['passed'] else 'FAIL',REAL_V3_RELAY='PASS_ISOLATED',RELAY_TO_RECEIVER='PASS_ISOLATED',V3_FINALITY_AND_TIMESTAMPS='PASS_ISOLATED',EXTERNAL_ENDPOINT_ADMISSION='BLOCKED',HTTP_WS_BUDGET_HARD_STOPS='PASS_ISOLATED',WINDOWS_PROCESS_IDENTITY='PASS_ISOLATED',GENUINE_PRODUCER_CUSTODY='BLOCKED_UNTIL_ACTUAL_AUTHORITY',BTCUSDT_FORMING='PASS_ISOLATED',ETHUSDT_FORMING='PASS_ISOLATED',DURABLE_FINALIZATION='PASS_ISOLATED',COMPILED_NATIVE_INTEGRATION='PASS_ISOLATED',FULL_PREFIX_ADMISSION='BLOCKED',ACTUAL_AMIBROKER_CHART='NOT_EXECUTED',GENUINE_BINANCE_RECEIPT='NOT_EXECUTED',PRODUCTION_DLL_INSTALLED=False,PRODUCTION_BROKER_RESTARTED=False,PRODUCTION_BINANCE_REQUESTS=0,PRODUCTION_HISTORICAL_DATABASE_WRITES=0,INDEPENDENT_REVIEW='BLOCKED_FULL_MILESTONE',OVERALL='BLOCKED_R6_GENUINE_PILOT_PREREQUISITES')
states.update({'10101_MODIFICATIONS':0,'18101_MODIFICATIONS':0,'timeout_scope':'10 measured runs, not hard real-time scheduling/fsync guarantee','same_forming_minute_finalization_integration':'BLOCKED_NOT_EXECUTED','original_R5_timeout_failure_preserved':True,'external_endpoint_policy':'local enforcement only; approved external identity unbound','native_prior_failure_root_cause':'PARTIAL_UNPROVEN','independent_review_artifact':'R6_INDEPENDENT_FINAL_REVIEW.json'})
put('R6_FINAL_DISPOSITION.json',states)
put('R6_WINDOWS_CMD_VERIFICATION.md','''# Read-only verification from Windows CMD

```cmd
py -3.12 -B D:\\WSRTD_N1_DATA_PLUGIN_FORMING_R6\\verify.py
certutil -hashfile D:\\WSRTD_N1_DATA_PLUGIN_FORMING_R6\\artifacts\\WSRTD_Data_Forming_R6.dll SHA256
type D:\\WSRTD_N1_DATA_PLUGIN_FORMING_R6\\R6_FINAL_DISPOSITION.json
```

Expected DLL SHA-256: b47b74935d90b383573234f595b27c94cb909812780eef45f15c4a884b5ae0e9

These commands do not launch a producer, install a DLL, run AmiBroker or rewrite test receipts. Do not install the fixture DLL into the running host.
''')
sys.path.insert(0,r'D:\WSRTD_N1_ACTIVE_CHART_RADAR_R1\retirement_controller_r1')
import r3_observer as observer
put('R6_PROTECTED_RUNTIME_NONINTERFERENCE.json',dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),listeners10101=observer.listeners(10101),listeners18101=observer.listeners(18101),scope='Read-only listener snapshot; not proof of market-data continuity or historical-file audit',protected_connections=0,production_process_control=0,production_database_writes=0,production_dll_writes=0,external_requests=0))
files=[]
for p in R.rglob('*'):
 if not p.is_file() or any(s in p.relative_to(R).parts for s in ('disposable','build','__pycache__')) or p.name=='R6_SOURCE_BINARY_SHA256_MANIFEST.json':continue
 files.append(dict(path=p.relative_to(R).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
put('R6_SOURCE_BINARY_SHA256_MANIFEST.json',dict(release_approved=False,files=files))
print('R6 engineering evidence packaged; live pilot blocked')
