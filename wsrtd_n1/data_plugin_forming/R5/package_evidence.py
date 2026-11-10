from pathlib import Path
import json,hashlib,datetime
R=Path(__file__).resolve().parent
def read(n):return json.loads((R/n).read_text())
def put(n,v):
 (R/n).write_text(json.dumps(v,indent=2) if not isinstance(v,str) else v,encoding='utf-8')
native=read('R5_END_TO_END_RECEIVER_RESULTS.json');review=read('R5_INDEPENDENT_FINAL_REVIEW.json')
put('R5_HTTP_WS_BUDGET_RESULTS.json',dict(author=read('R5_REAL_SOCKET_ADMISSION_RESULTS.json'),controller=read('evidence/CONTROLLER.json'),tls=read('evidence/TLS_CUSTODY.json'),independent_review='R5_INDEPENDENT_FINAL_REVIEW.json',strict_whole_call_1500ms='BLOCKED_OBSERVED_1609ms',persisted_debit_before_dispatch=True,external_endpoint_admission='BLOCKED_LOOPBACK_ONLY'))
put('R5_V3_EVENT_ROUNDTRIP.json',dict(status='PASS_ISOLATED',source='SYNTHETIC_FIXTURE',evidence='R5_END_TO_END_RECEIVER_RESULTS.json',outcomes=native['source_events'],separate_relay_process_tested=False,production_source_admission=False))
put('R5_DATA_PLUGIN_INTEGRATION_RESULTS.json',dict(status='PASS_ISOLATED',native=native['native'],dll=read('evidence/DLL_BUILD.json'),source_change='R3 native namespace, path and version only',weekly='BLOCKED_ACTUAL_HOST_REQUIRED',mixed_interval='BLOCKED_ACTUAL_HOST_REQUIRED',daily='R3 unchanged implementation; no new actual-host evidence',full_prefix=False,genuine_source=False))
put('R5_NATIVE_CALLBACK_STATUS.json',dict(status='PASS_ISOLATED',measurement=native['native'],actual_amibroker=False,notification_scope='Native harness window notification; not actual AmiBroker chart acknowledgment'))
put('R5_REAL_NETWORK_BACKEND.md','''# R5 real socket backend

`src/network.py` implements literal IPv4 loopback HTTP/1.1 and WebSocket framing with explicit TLS trust and hostname validation. Real sockets are exercised, not mocked method calls. Only ephemeral ports are admitted; 10101 and 18101 are forbidden. DNS, inherited proxies, redirects, hidden retries, compression, fragmented WebSocket messages and automatic reconnect are disabled. This is a qualified isolated backend subset, not a completed production Binance client.

`src/admission.py` commits SQLite aggregate debits before dispatch. REST count/weight, connection attempts, subscriptions, explicit reconnects, frames, bytes and expiration are persistent. Failed attempts remain charged. Reconnect status is derived from persisted WS attempt history. HTTP klines are capped at 499 per page. HTTP headers are capped at 8192 bytes, bodies at 65536, events at 16384. Inbound PING and outbound masked PONG consume frame/byte budget; control-frame loops are bounded.

Each socket operation has an at-most-one-second configured I/O deadline bounded by remaining admission time. This is not a proven strict whole-call wall-time guarantee: durable ledger work and scheduling precede or surround socket operations. Independent testing observed 1.609 seconds against a 1.5-second assertion. Failure evidence remains preserved. Cancellation closes owned sockets; it does not control any protected process.

TLS tests use disposable self-signed localhost credentials: trusted success, wrong-host rejection and valid unrelated-CA chain rejection. These do not qualify Binance DNS, endpoint routing or real certificates. Production protocol documentation/endpoint authority remains a required gate; no external request was made.
''')
put('R5_WINDOWS_PROCESS_CUSTODY.md','''# Windows custody scope

`src/custody.py` holds a query/synchronize process handle and checks PID, creation FILETIME, executable path and SHA-256, plus liveness. `src/controller.py` requires the producer PID to be the executing backend process, matches receiver PID/creation to the persistent ledger, and verifies both identities before startup, before read and after read. Start/read failure closes the owned backend. Wrong identities and contract digest fail before dispatch in isolated tests.

This proves isolated process identity, not external authority. The caller-supplied approval digest is not a signed operator authorization. Executable file hashing is not immutable image custody. Receiver death during blocked I/O is checked after the bounded read, not by a continuously qualified OS watcher. Ledger rollback/tampering protection and authentic production custody remain unqualified. No arbitrary PID string is promoted to genuine Binance custody.
''')
put('R5_18101_VERSIONED_HANDOFF.md','''# Versioned handoff and exact replacement boundary

The existing PR3 supervisor recognizes Broker by executable path and an established connection to 18101, then can restart the legacy fixed 500-symbol sender on receiver changes. Its fixed startup, discovery/preload/retry behavior is unsuitable for a one-symbol budget. R5 does not patch, connect to or replace it.

The isolated ControlledSession requires an explicit BTCUSDT-only contract and hash, live exact process attestations, persistent budget, explicit start and no automatic restart. Zero REST ceilings prevent REST dispatch. `src/handoff.py` rechecks receiver pipeline session/universe/symbol bindings on every event and rejects unsubscribed symbols and duplicate JSON keys. R3 V3 preserves source event metadata and finality through disposable durable storage.

Implemented path: real loopback WS -> admitted backend -> in-process V3 handoff/receiver -> disposable SQLite -> named pipe -> compiled R5 GetQuotesEx. A separate versioned relay process between sender and receiver is NOT implemented/qualified. Therefore the requested complete 18101 replacement boundary is BLOCKED, despite isolated handoff success.

Future integration must replace the legacy sender-start decision boundary with an explicitly authorized bounded controller, preserve V3 metadata end-to-end through a qualified relay, fence stale source/receiver generations and prove genuine custody. The running supervisor must not see a new qualifying receiver until its legacy launch behavior is safely fenced under separate authorization. No production execution command is supplied for an unqualified replacement.
''')
put('R5_FIRST_GENUINE_BTCUSDT_PILOT.md','''# First genuine BTCUSDT pilot — blocked, not executable

Proposed first scope: BTCUSDT only, one explicitly authorized connection/subscription, zero REST unless separately approved, no reconnect, no automatic restart. ETHUSDT is a subsequent separately bounded test. No 500-symbol producer is proposed.

Before approval: qualify external TLS/DNS endpoint routing and official current protocol contract; implement/test the separate V3 relay; qualify producer/receiver authority and genuine provenance; resolve deadline/accounting limits; establish full-prefix admission without relabeling synthetic history; qualify the test-owned writer and actual AmiBroker lifecycle. The current DLL is deliberately fixture-only and cannot be promoted by merely changing a flag.

Then bind exact final hashes, UTC start/end, REST weight/count, connection/subscription/frame/byte ceilings, endpoint, producer/receiver PID+creation+image, source generation, disposable directory identity and cleanup ownership. Start bounded producer only after receiver custody is verified. Correlate finalized source events, V3 receipt, durable commit, native callback and chart timestamps/OHLCV. Forming candles must replace only transient current-minute data; finalized history stays immutable.

Abort on identity/session change, stale generation, budget exhaustion, invalid finality, history conflict, unexpected request/reconnect, lost receiver or native mismatch. Close only test-owned network resources. Do not reconnect or alter 10101/18101. Actual host deployment/restart and network activation each need separate explicit authorization.
''')
put('R5_EXACT_OPERATOR_AUTHORIZATION.md','''# Authorization sheet — NOT READY FOR EXECUTION

R5 only authorizes isolated tests already performed. Do not approve production activation against this incomplete fixture candidate.

Required future fields: final controller/sender/relay/DLL SHA-256; endpoint/protocol authority; producer and receiver executable hash/PID/creation; source/session/universe generation; UTC window; REST request+weight ceilings; WS connection+subscription+reconnect ceilings; frames/bytes; exact disposable writer/database identity; full-prefix qualification; protected-service preservation; native host installation and lifecycle scope; cleanup/abort controls.

All live fields remain UNBOUND. Network, protected relay changes, DLL installation and Broker restart remain unauthorized. R5 manifest identifies engineering artifacts only, not production permission. The smallest next step is offline closure of the missing relay/external-admission/custody contract, followed by a fresh exact-action approval package; no live operation is currently qualified.
''')
states=dict(TASK_ID='WSRTD_N1_DATA_PLUGIN_R5_REAL_NETWORK_BACKEND_AND_18101_HANDOFF',R4_PREDECESSOR_INTEGRITY='PASS',REAL_HTTP_BACKEND='PASS_ISOLATED',REAL_WEBSOCKET_BACKEND='PASS_ISOLATED',REST_HARD_BUDGET='PASS_REAL_LOOPBACK',WS_HARD_BUDGET='PASS_REAL_LOOPBACK',RECONNECT_HARD_STOP='PASS_REAL_LOOPBACK',NETWORK_CLEANUP='PASS_REAL_LOOPBACK',WINDOWS_PROCESS_CUSTODY='QUALIFIED_ISOLATED',V3_FINALITY_TRANSPORT='PASS_ISOLATED',BTCUSDT_FORMING='PASS_ISOLATED',ETHUSDT_FORMING='PASS_ISOLATED',DURABLE_FINALIZATION='PASS_ISOLATED',NATIVE_DATA_PLUGIN_INTEGRATION='PASS_ISOLATED',ACTUAL_AMIBROKER_CHART='NOT_EXECUTED',GENUINE_BINANCE_RECEIPT='NOT_EXECUTED',FULL_PREFIX_ADMISSION='UNQUALIFIED',R5_CANDIDATE_DLL='BUILT',INDEPENDENT_REVIEW='BLOCKED',INDEPENDENT_FUNCTIONAL_SCOPE='PASS_WITH_RECORDED_TIMING_GATE_FAILURE',PRODUCTION_DLL_INSTALLED=False,PRODUCTION_BROKER_RESTARTED=False,PROTECTED_18101_CONNECTIONS=0,PRODUCTION_BINANCE_REQUESTS=0,HISTORICAL_DATABASE_MODIFICATIONS=0,OVERALL='BLOCKED_R5_GENUINE_PILOT_PREREQUISITES')
states['18101_VERSIONED_HANDOFF']='BLOCKED_SEPARATE_RELAY_NOT_QUALIFIED'
states['blockers']=['External endpoint/DNS/TLS routing and production protocol admission not implemented or qualified','Separate versioned relay process and legacy supervisor replacement integration absent','Genuine source authority, production process custody and full-prefix qualification absent','Strict 1.5-second whole-call timing not qualified; observed 1.609 seconds','Actual AmiBroker chart/refresh/weekly/mixed-interval acceptance not executed']
put('R5_FINAL_DISPOSITION.json',states)
put('R5_WINDOWS_CMD_VERIFICATION.md',r'''# Windows CMD verification

Read-only artifact integrity (does not install or run the feed):

```cmd
py -3.12 -B D:\WSRTD_N1_DATA_PLUGIN_FORMING_R5\verify.py
certutil -hashfile D:\WSRTD_N1_DATA_PLUGIN_FORMING_R5\artifacts\WSRTD_Data_Forming_R5.dll SHA256
type D:\WSRTD_N1_DATA_PLUGIN_FORMING_R5\R5_FINAL_DISPOSITION.json
```

Expected DLL SHA-256: 98fdf9d713e9200294ad5c111ed459de96d5b416e30a49726347b7f506b2f84b

Do not copy into AmiBroker Plugins. Do not launch this candidate against protected ports or installed SQLite. Test receipts already exist; verification does not rerun tests or rewrite them.
''')
files=[]
for p in R.rglob('*'):
 if not p.is_file() or any(x in p.relative_to(R).parts for x in ('build','disposable','__pycache__')) or p.name=='R5_SOURCE_BINARY_SHA256_MANIFEST.json':continue
 files.append(dict(path=p.relative_to(R).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
put('R5_SOURCE_BINARY_SHA256_MANIFEST.json',dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),release_seal=False,files=files))
print('R5 evidence package written; genuine pilot BLOCKED')
