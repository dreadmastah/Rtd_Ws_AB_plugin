"""Independent reviewer receipt bound to inspected sources and executed tests."""
import pathlib,hashlib,json,datetime
R=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
n=json.loads((R/'independent/native_results.json').read_text());t=json.loads((R/'independent/receiver_results.json').read_text())
assert n['passed'] and t['passed']
assert n['dll_sha256']==sha(R/'artifacts/WSRTD_Data_Forming_R2.dll')
assert n['source_sha256']==sha(R/'native/plugin.cpp')
assert t['source_sha256']==sha(R/'transport.py')
paths=['native/plugin.cpp','native/CMakeLists.txt','transport.py','fixture_pipe.py','artifacts/WSRTD_Data_Forming_R2.dll','tests/native_probe.cpp','independent/test_receiver.py','independent/test_native.py','independent/native_results.json','independent/receiver_results.json','dependencies/adk/Plugin.h','R2_18101_PROCESS_AND_SOURCE_CHAIN.json','R2_RESOURCE_MEASUREMENTS.json']
receipt={
 'reviewer':'independent agent /root/forming_r2_review; implementation author /root',
 'completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'status':'PASS_SCOPED_OFFLINE_FIXTURE_IMPLEMENTATION_REVIEW',
 'release_or_live_approval':False,
 'scope':'Exact isolated synthetic receiver, disposable SQLite merge, x64 data DLL, native callback and private-window refresh; not genuine feed or actual AmiBroker acceptance',
 'independent_tests':{'receiver_passed':t['tests'],'native_passed':len(n['tests']),'native_type':'actual compiled DLL callbacks; own process and private same-thread window','actual_amibroker':False},
 'reviewed_hashes':{p:sha(R/p) for p in paths},
 'closed_findings':[
  'Late-final per-bucket processing replaces predecessor per-symbol timestamp suppression.',
  'Disconnect and stale transition now invalidate the host cache via supported WM_USER_STREAMING_UPDATE.',
  'Old serial and changed same-serial snapshot replay are rejected.',
  'Decimal-equivalent history compares numerically; historical snapshot regression rejected.',
  'Malformed deep JSON fails closed; finalized-pending backlog backpressures instead of evicting history.',
  'Native callback map access uses guard and lifecycle epoch; lifecycle operations use recursive nonblocking gate.',
  'Worker pipe handles have RAII cleanup across exceptions; worker exceptions cannot escape thread entry.'
 ],
 'source_chain_assessment':{
  'metadata_loss':'Confirmed sender.record serializes n,d,t,o,h,l,c,v and drops x/E; self.seen is not forwarded provenance.',
  'current_producer':'UNVERIFIED; zero relay connections alone does not prove upstream inactivity.',
  'running_sender_version_bound':False,
  'protocol_correction_deployed':False
 },
 'mandatory_remaining_gates':[
  'Fixture-only candidate rejects genuine provenance. Independently qualified real producer custody/admission is not implemented.',
  'Full-prefix certificate is not implemented: IsBackfillComplete always false; source status is red, prefix false. No production admission exists.',
  'Only disposable OUTPUT_ROOT databases are supported. Protected historical database loading and production migration are not approved.',
  '65536 total snapshot rows, 1024 symbols and four pending live buckets per symbol are explicit bounds; full-history lifetime capacity unqualified.',
  'Scale measurements use short synthetic snapshots, not sustained genuine 500+ traffic. Foundational13 identity and600 eligible-symbol universe not established.',
  'Source precision retained as decimal strings; snapshot and ADK quotation conversion is floating-point and actual AmiBroker rounding/readback remains untested.',
  'Actual AmiBroker7.20 native load, callback ordering, refresh/chart behavior, persistent history and safe host unload remain NOT_EXECUTED.',
  'No genuine18101 connection, producer restoration, sender change, DLL installation or host lifecycle action is authorized by this review.',
  'Finite lifecycle concurrency tests are not exhaustive race or memory fault qualification. Live upgrade needs its own final-source tests and review.'
 ],
 'nonmutation':{'production_process_controls':0,'protected_relay_connections':0,'binance_connections':0,'installed_dll_changes':0,'historical_database_writes':0},
 'overall':'BLOCKED_GENUINE_PRODUCER_CUSTODY_FULL_PREFIX_ADMISSION_AND_REAL_HOST_ACCEPTANCE',
}
(R/'R2_INDEPENDENT_FINAL_REVIEW.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps({'status':receipt['status'],'dll_sha256':n['dll_sha256'],'native_checks':len(n['tests']),'receiver_checks':t['tests']},indent=2))
