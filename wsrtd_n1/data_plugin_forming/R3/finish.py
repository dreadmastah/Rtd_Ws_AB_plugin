from pathlib import Path
import json,hashlib
R=Path(__file__).parent;P=Path(r'D:\WSRTD_N1_DATA_PLUGIN_FORMING_R2')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(n):return json.loads((R/n).read_text())
def put(n,o):(R/n).write_text(json.dumps(o,indent=2),encoding='utf-8')
review=read('R3_INDEPENDENT_FINAL_REVIEW.json')
pre=read('R3_PREDECESSOR_INTEGRITY.json');assert all(sha(P/n)==v for n,v in pre['baseline_hashes'].items())
native=read('independent/native_results.json');tests=read('independent/receiver_durable_results.json')
assert native['dll_sha256']==sha(R/'artifacts/WSRTD_Data_Forming_R3.dll')
put('R3_NATIVE_API_INDEPENDENT_TESTS.json',{'review':'R3_INDEPENDENT_FINAL_REVIEW.json','native_receipt':'independent/native_results.json','receiver_storage_receipt':'independent/receiver_durable_results.json','actual_host':False})
review_status=review.get('status',review.get('verdict','BLOCKED'))
put('R3_FINAL_DISPOSITION.json',{'TASK_ID':'WSRTD_N1_DATA_PLUGIN_R3_GENUINE_18101_HANDOFF_AND_NATIVE_READINESS','R2_PREDECESSOR_INTEGRITY':'PASS','18101_ACTIVATION_CONTRACT':'QUALIFIED_SOURCE_ONLY','18101_PRODUCER_CUSTODY':'BLOCKED','REST_REHYDRATION_BUDGET':'BLOCKED_INSTALLED_SENDER_UNBOUNDED','SENDER_METADATA_CORRECTION':'PASS_OFFLINE_CALLABLE_ADAPTER_ONLY','EVENT_FINALITY_PRESERVED':'PASS_OFFLINE','EVENT_TIMESTAMP_PROVENANCE':'PASS_OFFLINE_LINKAGE_NOT_GENUINE_AUTHORITY','RECEIVER_INTEGRATION':'PASS_OFFLINE','DURABLE_FINALIZED_STORAGE':'PASS_OFFLINE_DISPOSABLE','TRANSACTION_CRASH_RECOVERY':'PASS_PROCESS_CRASH_ONLY','FULL_PREFIX_INTEGRATION':'BLOCKED_ARCHIVE_ADMISSION_AUTHORITY','NATIVE_1M_CALLBACK':'PASS_OFFLINE','NATIVE_DAILY_CALLBACK':'PASS_OFFLINE_COMPLETE_UTC_DAY','NATIVE_MIXED_INTERVALS':'BLOCKED_REAL_HOST_SETTINGS_AND_WEEKLY_COMPRESSION','NATIVE_AUTO_REFRESH':'PASS_OFFLINE_PRIVATE_WINDOW','SCALE_13':'BLOCKED_FOUNDATIONAL_ROSTER_SYNTHETIC13_PASSED','SCALE_100':'PASS_OFFLINE','SCALE_500':'PASS_OFFLINE_SHORT_SNAPSHOT','SCALE_1024':'PASS_SYNTHETIC_SHORT_SNAPSHOT','CORRECTED_R3_DLL':'BUILT_FIXTURE_ONLY','INDEPENDENT_REVIEW':review_status,'GENUINE_18101_LIVE_RECEIPT':'NOT_EXECUTED','ACTUAL_AMIBROKER_FORMING_BAR':'NOT_EXECUTED','PRODUCTION_DLL_INSTALLED':False,'AMIBROKER_RESTARTED':False,'10101_MODIFICATIONS':0,'18101_MODIFICATIONS':0,'HISTORICAL_DATABASE_MODIFICATIONS':0,'OVERALL':'BLOCKED_GENUINE_CUSTODY_BOUNDED_ACTIVATION_FULL_PREFIX_AND_REAL_HOST_GATES','dll_sha256':native['dll_sha256'],'limitations':['No runnable qualified genuine18101 network adapter deployed or activated','Budget primitive not integrated into installed sender REST paths','Synthetic provenance only; fullprefix remains false','Daily1440 aggregation tested; actual mixed/weekly host unexecuted','Shortscale only; lifetime history and sustained durable500 load unqualified','No production filesystem provisioning/migration authority']})
(R/'README.md').write_text('''# R3 offline data-plugin integration

Implemented a distinct x64 WFR3 candidate, V3 raw-event/universe linkage, disposable SQLite epoch-fenced final commits and receipt retention, crash/idempotency/conflict/full-disk handling, restored history with receipt validation, and complete UTC daily aggregation. Forming rows remain transient; finality is exchange-event-driven. Tested integrated synthetic paths through1,024symbols. R2 preserved byte-for-byte.

Overall BLOCKED for genuine pilot: actual18101 activation is unbounded and Broker-gated; sourcecustody/fullprefix archive authority absent; actualAmiBroker weekly/mixedsettings/lifecycle unqualified. DLL is fixture-only, not deployable. See R3_FINAL_DISPOSITION.json and R3_EXACT_OPERATOR_AUTHORIZATION.md.

All productionprocess, feedconnection, installedDLL, historicalDB and scheduledtask mutations:0. No newBinance data requests. Native tests use isolated harnesses, notBroker.
''',encoding='utf-8')
files=[p for p in R.rglob('*') if p.is_file() and not any(x in p.relative_to(R).parts for x in ('build','disposable','__pycache__')) and p.name!='R3_SOURCE_BINARY_SHA256_MANIFEST.json']
put('R3_SOURCE_BINARY_SHA256_MANIFEST.json',{'type':'unsealed evidence inventory, not deployment approval','files':{str(p.relative_to(R)).replace('\\','/'):sha(p) for p in sorted(files)}})
print('Final evidence inventoried',len(files))
