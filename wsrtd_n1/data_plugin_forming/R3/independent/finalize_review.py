import pathlib,json,hashlib,datetime
R=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
n=json.loads((R/'independent/native_results.json').read_text());r=json.loads((R/'independent/receiver_durable_results.json').read_text())
assert n['passed'] and r['passed']
assert n['dll_sha256']==sha(R/'artifacts/WSRTD_Data_Forming_R3.dll')
assert n['source_sha256']==sha(R/'native/plugin.cpp')
for p,h in r['hashes'].items():assert sha(R/p)==h
files=['src/durable.py','src/pipeline.py','src/transport.py','src/fixture_pipe.py','native/plugin.cpp','native/CMakeLists.txt','artifacts/WSRTD_Data_Forming_R3.dll','tests/test_durable.py','tests/test_pipeline.py','tests/test_native_inherited.py','independent/test_r3.py','independent/native_review_run.py','independent/native_results.json','independent/receiver_durable_results.json']
review={
 'reviewer':'Independent agent /root/forming_r2_review; implementation author /root',
 'completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'status':'PASS_SCOPED_OFFLINE_R3_IMPLEMENTATION_REVIEW',
 'overall_live_pilot_ready':False,
 'source_and_binary_hashes':{p:sha(R/p) for p in files},
 'independent_execution':{'receiver_storage_budget_checks':r['tests'],'native_DLL_checks':len(n['tests']),'all_passed':True,'actual_amibroker':False},
 'reviewed_activation_contract':[
  'native_receivers requires exact Broker executable path and established remote port18101; arbitrary local receiver attachment does not meet predicate.',
  'Five-second supervisor loop starts or restarts sender on native receiver identity change, sender exit or relay restart; no receiver stops sender.',
  'Configured sender uses500pinned symbols, native-history andquotes; discoveryREST precedesWS and invalid pinned symbols abort.',
  'Nominal500-symbol startup uses5marketWS plus5publicWS,1500subscriptions and2500kline preload requests plus exchangeInfo; retries/commands/repair/reconnect prevent finite aggregateproduction budget.',
  'No-production-REST mode is not supplied by existing supervisor; candidate Budget is offline admission only and makes no request.'
 ],
 'closed_findings':[
  'Decimal normalization no longer rounds at ambient context precision.',
  'Wrong existing database scope/schema checked read-only before configuration/schema writes.',
  'V3raw event/universe linkage persisted atomically with finalized row; missing required receipt rejects restore.',
  'Ledger hashes and values checked on read; immutable conflicts and stale writer epochs rejected.',
  'Per-bucket storage errors remain visible after another symbol commits successfully.',
  'Request/weight/page/deadline types reject NaN/bool/fractional limits; reserve serialized and plan range bounded.',
  'Native daily path requires1440unique durableUTCminutes, excludes pendingfinals, uses verified64-bitDAILY_MASK.',
  'Native1m replacement, disconnect invalidation, capacity refusal, owner/session fencing, private-windowrefresh and concurrent lifecycle tests pass.'
 ],
 'durability_assessment':{
  'offline_SQLite_commit_and_duplicate_semantics':'PASS_SCOPED',
  'author_crash_tests':'Reviewed beforeCOMMIT os._exit71 and afterCOMMIT os._exit72; process-crash scope only',
  'author_storage_full_test':'Reviewed real SQLite max_page_count constraint on disposable DB',
  'power_loss_durability':'NOT_TESTED',
  'production_writer_authority':'NOT_GRANTED',
  'genuine_provenance':'NOT_QUALIFIED; synthetic rows retain synthetic labels'
 },
 'mandatory_remaining_gates':[
  'Candidate remains FIXTURE_ONLY and disposable-path constrained; genuine producer custody/admission is absent.',
  'Current sender is unmodified and loses x/E metadata; production activation and versioned output handoff need separate exact authorization.',
  'Archive/full-prefix bootstrap authority remains denied; structural completeness and locally hashed receipts do not establish authoritative provenance.',
  'Current native API returns IsBackfillComplete false; no complete-since-listing production admission implemented.',
  'OriginalN1database timezone/source/writer custody and native history preservation remain unqualified.',
  'Actual AmiBroker load, genuine chart update, mixedEOD/intraday behavior and weekly host compression NOT_EXECUTED.',
  'Scale evidence covers short synthetic snapshots and two commits per stage, not sustained500-symbol durable throughput or lifetimehistory capacity.',
  'Foundational13identity remains synthetic; no600eligibleuniverse authority.',
  'Snapshot cap65536rows andStore read cap600000rows are bounded test admission, not full-universe full-history qualification.',
  'No Broker restart/DLLinstallation/18101attachment/senderactivation/RESTrehydration authorized by this review.'
 ],
 'production_mutations':0,'protected_relay_connections':0,'binance_requests':0,
 'disposition':'BLOCKED_GENUINE_CUSTODY_FULL_PREFIX_AND_ACTUAL_NATIVE_HOST_ACCEPTANCE'
}
(R/'R3_INDEPENDENT_FINAL_REVIEW.json').write_text(json.dumps(review,indent=2),encoding='utf-8')
print(json.dumps({'status':review['status'],'dll':n['dll_sha256'],'native_checks':len(n['tests']),'receiver_checks':r['tests']},indent=2))
