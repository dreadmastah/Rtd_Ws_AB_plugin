from pathlib import Path
import json,hashlib
R=Path(__file__).parent;P=Path(r'D:\WSRTD_N1_DATA_PLUGIN_FORMING_R3')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(n,o):(R/n).write_text(json.dumps(o,indent=2),encoding='utf-8')
review=json.loads((R/'R4_INDEPENDENT_FINAL_REVIEW.json').read_text());pre=json.loads((R/'R4_PREDECESSOR_INTEGRITY.json').read_text())
assert all(sha(P/n)==v for n,v in pre['hashes'].items())
assert all(sha(R/n)==v for n,v in review['reviewed_hashes'].items()), 'Reviewed artifact changed'
assert all(sha(R/n)==v for n,v in review['dependency_hashes'].items()), 'Reviewed dependency changed'
put('R4_FINAL_DISPOSITION.json',{'TASK_ID':'WSRTD_N1_DATA_PLUGIN_R4_BOUNDED_18101_PRODUCER_AND_V3_HANDOFF','R3_PREDECESSOR_INTEGRITY':'PASS','BOUNDED_18101_ACTIVATION':'BLOCKED_REAL_BACKEND_AND_LEGACY_HANDOFF_UNIMPLEMENTED','REST_HARD_BUDGET':'PASS_OFFLINE_FIXTURE_DISPATCH_ONLY','WEBSOCKET_HARD_BUDGET':'PASS_OFFLINE_FIXTURE_DISPATCH_ONLY','NO_REST_MODE':'PASS_OFFLINE','RECONNECT_CONTROL':'PASS_OFFLINE_PERSISTED_ATTEMPTS','V3_FINALITY_PRESERVATION':'PASS_OFFLINE','V3_EVENT_TIME_PROVENANCE':'PASS_OFFLINE_RAW_LINKAGE_NOT_GENUINE_CUSTODY','BTCUSDT_FORMING':'PASS_OFFLINE','ETHUSDT_FORMING':'PASS_OFFLINE','DURABLE_FINALIZATION':'PASS_OFFLINE_DISPOSABLE_R3_HANDOFF','WEEKLY_MIXED_INTERVALS':'BLOCKED_REAL_HOST_REQUIRED','NATIVE_REFRESH':'PASS_OFFLINE_INHERITED_R3_NOT_ACTUAL_CHART','FULL_PREFIX_POLICY':'PRESERVED','ACTUAL_AMIBROKER_FORMING_BAR':'NOT_EXECUTED','GENUINE_BINANCE_RECEIPT':'NOT_EXECUTED','18101_PRODUCTION_MODIFICATIONS':0,'10101_PRODUCTION_MODIFICATIONS':0,'BROKER_RESTARTED':False,'HISTORICAL_DATABASE_MODIFICATIONS':0,'INDEPENDENT_REVIEW':review.get('status',review.get('verdict','BLOCKED')),'OVERALL':'BLOCKED_REAL_NETWORK_CUSTODY_HANDOFF_AND_NATIVE_HOST_GATES','blockers':['OnlyFixtureBackend supplied; actualHTTP/WSbudget and timeout/redirect/retry/cleanup enforcement notqualified','No genuine-source admission into unchangedfixtureonlyR3 or OSproducer/receivercustody','Current18101supervisor incompatible with passiveone-symbolactivation; no controllerreplacementexecuted','Actualweekly/mixed/chartrefresh and supportedhostloading requireseparatequalification','Fullprefixhistoryauthority remainsfalse; no productionbackfillauthorization'],'R3_DLL_UNCHANGED':pre['dll_sha256']})
(R/'README.md').write_text('''# R4 bounded controller and metadata handoff

Implemented persistent one-shot admission, exact contract/session binding, aggregate REST/weight/connection/subscription/reconnect/frame/byte limits, clock checks and durable STOP latch. Failed attempts remain consumed across restart. Sender and relay preserve complete V3 event metadata through unchanged R3 disposable storage. Independent review and targeted tests recorded separately.

Fixture-only backend: no actual HTTP/WebSocket network implementation or production activation. Overall BLOCKED for genuine pilot; see R4_FINAL_DISPOSITION and R4_NEXT_OPERATOR_AUTHORIZATION. R3 DLL and 67-entry evidence preserved unchanged. No native rebuild or installation.

Source ingress and relay dispatch both consume the shared frame/byte budget. Ledger corruption checks are not hostile filesystem rollback protection; trusted clock, filesystem and OS custody remain production prerequisites. No automatic startup on receiverarrival, automaticreconnect or legacyfallback.
''',encoding='utf-8')
files=[p for p in R.rglob('*') if p.is_file() and not any(x in p.relative_to(R).parts for x in ('disposable','__pycache__')) and p.name!='R4_SOURCE_BINARY_SHA256_MANIFEST.json']
put('R4_SOURCE_BINARY_SHA256_MANIFEST.json',{'kind':'unsealed source/evidence inventory; no deploymentapproval','files':{str(p.relative_to(R)).replace('\\','/'):sha(p) for p in sorted(files)}})
print('inventoried',len(files),'files')
