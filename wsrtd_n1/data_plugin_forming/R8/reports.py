from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parent
def put(n,v):(R/n).write_text(v if isinstance(v,str) else json.dumps(v,indent=2),encoding='utf-8')
def read(n):return json.loads((R/n).read_text())
put('R8_EXTERNAL_TRANSPORT_IMPLEMENTATION.md','''# R8 external WebSocket capability — implemented, not activated

`src/external.py` contains real IPv4 TCP/TLS dispatch to fstream.binance.com:443 and exact raw path /market/ws/btcusdt@kline_1m. [Official Connect](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Connect) and [migration mapping](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Important-WebSocket-Change-Notice) were rechecked. Klines use /market. No spot/COIN-M endpoint is admitted.

Future execution requires an exact caller-supplied approval digest matching a strict manifest: scope, UTC contract, one BTC stream, REST0, connection1, subscription1, reconnect0, frames/bytes, executable PID/creation/path/hash, all src and validator dependency hashes, exact approved IP set and disposable physical parent. A digest and boolean are not independent proof the operator approved them; operator delivery remains an external governance boundary. No approved live manifest is supplied.

DNS runs in an owned subprocess after persistent connection/subscription debits. All IPv4 answers must be in the approved public-address set. One address is chosen; no address iteration, fallback, redirect, proxy or automatic reconnect. A late result is rejected before socket creation. Resolver timeout terminates and reaps that test-owned subprocess; OS scheduling and DNS services are not hard real-time guarantees. System TLS verifies certificates and hostname. SSL_CERT_FILE/DIR overrides are rejected. Test mode is explicitly separate localhost/custom-test-CA scope, not a live override.

WebSocket frames and bytes are pre-debited. Fragmented/binary/oversized/masked server frames fail closed. PING receives masked PONG only after debit, capped at five outbound controls per rolling second. Control flooding closes the socket. URL subscription is counted before connection; JSON subscription and REST methods refuse. A one-second receive idle deadline can end the finite pilot early; no reconnect follows. This is an operational limitation, not evidence of exchange failure.

The Phase A capture entry point can hold a process before approval and emits its OS identity. It records raw payload/hash/time as CAPTURE_PENDING_INDEPENDENT_QUALIFICATION, never genuine full-prefix/native history. However its live execution is explicitly disabled: directory rename exclusion FAILED on this host. Parent handles and stat checks did not prove exclusive writer-directory custody. No live network call is allowed through the CLI until that technical gate is corrected and reviewed. No native code changed or DLL rebuilt.
''')
put('R8_PRODUCER_RECEIVER_WRITER_CUSTODY.json',dict(status='BLOCKED_WRITER_CUSTODY',producer='OS process attestation and exact code-set checks implemented; future approval identity UNBOUND',controller_sender_receiver='Phase A uses same held process; no protected relay',relay='R7 peer checks preserved but not required for standalone Phase A raw receipt',data_plugin='R7 fixture-only DLL preserved; not part of Phase A',writer_test=read('evidence/CAPTURE_GUARDS.json'),physical_output='parent rename-exclusion failed; new child-directory and reparse races unqualified',production_authority=False,live_cli_disabled=True))
put('R8_ACTUAL_AMIBROKER_PREFLIGHT.md','''# Actual installed host — read-only evidence, activation BLOCKED

evidence/HOST_READONLY.json and INSTALLED_BINDING.json bind the observation. Installed Broker version is 7.20.0.7200. Observed Broker PID80796, parent62440, creation134386152811195744, executable SHA256 30a6b5f3f027d6c2df50612c9e6a61ee1f23db135c35cb9d0f5c02b5d68a3b81. Refresh these before any future action.

N1 directory exists, but D:\\Amibroker_myDATA\\N1.wsrtd-n1\\feed.sqlite is absent. Therefore current SQLite schema and historical writer identity cannot be asserted. No database was opened writable, no WAL/SHM touched and no replacement file created. Loaded N1 DLL identity is observed; current selected source/database configuration is not freshly attested by those module observations. Exclusive writer custody remains unknown.

No safe independent actual-host lifecycle is proven. Existing Broker stays running. No retirement investigation was reopened. Startup plugin discovery and loaded-DLL lock rules remain applicable; no hot load, injection or overwrite is proposed. A separate PID or /database argument does not prove isolation. ABI, notification and UTC minute behavior are backed only by prior compiled harness evidence. Actual chart refresh, weekly and mixed EOD/intraday settings remain unexecuted.

Future Phase B prerequisites: operator-attest active database/source in the exact host; qualify physical directory and exclusive writers; qualify a disposable test host lifecycle without adoption/relaunch or protected-feed changes; obtain separate installation and source-selection authorization; preserve all original DLLs. Install only unloaded reviewed candidate under the qualified lifecycle. Verify source receipt -> relay -> durable commit -> GetQuotesEx -> chart/Quote Editor exact UTC timestamp/OHLCV, two consecutive updates without manual Refresh. Rollback only approved candidate files after qualified unload; never delete historical quotations. No executable installation/restart command is ready while these facts are missing.
''')
history=read('R8_HISTORY_ADMISSION_BOUNDARY.json');history['R8_boundary']='A separately approved disposable Phase A raw receipt test need not establish full-prefix production readiness. Phase B genuine adapter still unqualified.';history['production_states']=dict(GENUINE_LIVE_SOURCE_READY=False,FORMING_CANDLE_READY='ISOLATED_ONLY',FINALIZED_STORAGE_READY='ISOLATED_ONLY',FULL_PREFIX_COMPLETE=False,ACTUAL_NATIVE_HOST_READY=False,PRODUCTION_500_SYMBOL_READY=False);put('R8_HISTORY_ADMISSION_BOUNDARY.json',history)
put('R8_BTCUSDT_PHASE_A_LIVE_SOURCE_PILOT.md','''# Phase A — BLOCKED until writer custody correction and exact authorization

Proposed scope: BTCUSDT 1m, wss://fstream.binance.com/market/ws/btcusdt@kline_1m, REST0, WS1, subscription1, reconnect0, disposable raw receipts only. No AmiBroker or 18101 attachment. Full-prefix production admission is expressly not claimed.

Technical blocker: actual directory rename test failed despite held handles. Qualify Windows handle-relative creation/access or another OS-enforced exclusive output mechanism, including reparse/child-directory replacement and exact writer ownership. Review the correction; keep the CLI closed until then.

Future two-stage control (NOT authority to execute now): prepare the capture process in HELD_NO_NETWORK state, read its exact PID/creation/image, bind all source/dependency hashes and a new output directory's physical parent, then obtain explicit operator approval of the complete manifest and canonical SHA256. UTC start/end, duration (contract maximum120s), approved IPs, frame/byte ceilings remain UNBOUND. Starting the held process itself is a separately scoped future action. Do not hash a self-generated manifest and call it operator approval.

After that approval, the held process accepts the exact manifest path/digest and explicit execute flag through stdin. The current entry point refuses live execution because writer custody is unqualified. A separately reviewed correction is required before an executable command can be issued.

Abort on source/hash/process/parent mismatch, unexpected DNS, TLS failure, redirect, reconnect, budget/time exhaustion, malformed data, stale event or file failure. Close only owned socket and resolver; preserve receipts, consumed budget and failure evidence. No retry/reconnection. Raw payloads retain pending-qualification provenance. Later review must validate event timestamp, OHLCV and finality; a timeout without a final does not prove exchange malfunction.
''')
put('R8_BTCUSDT_PHASE_B_NATIVE_HOST_PILOT.md','''# Phase B — separately authorized, BLOCKED

Prerequisites: successful independently checked Phase A receipt, genuine-source admission adapter (R7 DLL remains fixture-only), qualified disposable writer, exact active source/database and host lifecycle, separate DLL installation and source-change permissions. Do not pass genuine captures through synthetic provenance merely to satisfy the current receiver.

Do not attach to 18101: its receiver-triggered legacy500 sender is outside this pilot. Use only a separately qualified test-owned relay/receiver path. No new 500-symbol streamer. No existing historical writes. Full-prefix production qualification remains independently false unless authoritative listing-to-cutoff coverage and provenance are established.

Upon separate approval: start the approved bounded receiver before the qualified host, bind process environment/session, select the candidate only for the disposable database, read BTCUSDT UTC minute/OHLCV in Quote Editor and chart, correlate source/receipt/commit/callback/refresh, and observe two finalized transitions. Weekly/mixed and restart persistence need their own acceptance. Cleanup only the test cohort and approved unloaded DLL; preserve quotations. No host operation has occurred in R8.
''')
put('R8_EXACT_OPERATOR_AUTHORIZATION.md','''# Exact approval gate — no execution requested yet

Phase A and Phase B approvals must remain separate. Phase A cannot be issued until failed directory-custody protection is corrected. Phase B additionally needs genuine adapter and host lifecycle qualification.

Required Phase A fields: approved UTC start/end/duration; exact URL; public IPv4 answer allowlist; REST0/WS1/sub1/reconnect0; received-frame/payload-byte ceilings; source/dependency/executable hashes; held process PID/creation; producer/session/universe generation; disposable physical parent/output/writer identity; exact cleanup/abort actions; operator-supplied canonical manifest digest.

Required Phase B fields: Phase A receipt hashes, genuine admission evidence, candidate DLL hash, qualified Broker identity/lifecycle, disposable database identity, source switch and installation authority, protected-service preservation and rollback scope.

All future execution identities/windows remain UNBOUND. No production modification, Binance activation or installation command is authorized by this artifact.
''')
state=dict(TASK_ID='WSRTD_N1_DATA_PLUGIN_R8_EXTERNAL_TRANSPORT_AND_PILOT_READINESS',R7_PREDECESSOR_INTEGRITY='PASS',EXTERNAL_WS_DISPATCH='IMPLEMENTED_NOT_ACTIVATED',DNS_TLS_ENDPOINT_ENFORCEMENT='PASS_ISOLATED',NETWORK_BUDGETS='PASS_ISOLATED',PRODUCER_CUSTODY='BLOCKED_FUTURE_AUTHORITY_UNBOUND',RECEIVER_PEER_CUSTODY='BLOCKED_ACTUAL_PILOT_UNBOUND',WRITER_CUSTODY='BLOCKED_RENAME_EXCLUSION_FAILED',ACTUAL_AMIBROKER_PREFLIGHT='BLOCKED_SELECTED_SOURCE_SQLITE_WRITER_UNATTESTED',NATIVE_HOST_LIFECYCLE='BLOCKED',WEEKLY_MIXED_INTERVALS='NOT_EXECUTED',FULL_PREFIX_ADMISSION='BLOCKED',PHASE_A_GENUINE_SOURCE_PILOT='BLOCKED_WRITER_CUSTODY',PHASE_B_NATIVE_CHART_PILOT='BLOCKED_GENUINE_ADAPTER_AND_HOST',GENUINE_BINANCE_REQUESTS=0,ACTUAL_AMIBROKER_FORMING_BAR='NOT_EXECUTED',PRODUCTION_DLL_INSTALLED=False,PRODUCTION_BROKER_RESTARTED=False,PRODUCTION_HISTORY_WRITES=0,INDEPENDENT_REVIEW='PASS_SCOPED_OR_BLOCKED_SEE_REVIEW',OVERALL='BLOCKED_WRITER_CUSTODY_AND_PHASE_B_HOST_GATES',native_rebuilt=False)
state.update({'10101_MODIFICATIONS':0,'18101_MODIFICATIONS':0,'live_capture_entrypoint_disabled':True,'docs_requests':'official documentation only; separate from zero market-data REST/WS'})
put('R8_FINAL_DISPOSITION.json',state)
put('R8_WINDOWS_CMD_VERIFICATION.md','''# Read-only Windows CMD verification

```cmd
py -3.12 -B D:\\WSRTD_N1_DATA_PLUGIN_FORMING_R8\\verify.py
type D:\\WSRTD_N1_DATA_PLUGIN_FORMING_R8\\R8_FINAL_DISPOSITION.json
```

No test rerun, live dispatch, Broker restart or DLL install occurs. No R8 DLL was rebuilt; R7 remains preserved. Do not invoke capture.py as live execution; writer-custody gate is closed.
''')
print('R8 reports written; exact writer blocker retained')
