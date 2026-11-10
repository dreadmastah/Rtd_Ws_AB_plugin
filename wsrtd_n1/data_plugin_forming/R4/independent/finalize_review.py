import pathlib,json,hashlib,datetime
R=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
a=json.loads((R/'independent/admission_results.json').read_text());s=json.loads((R/'independent/sender_results.json').read_text())
assert a['passed'] and s['passed']
assert a['source_sha256']==sha(R/'src/admission.py')
assert s['source_sha256']==sha(R/'src/sender.py')
dll=pathlib.Path(r'D:\WSRTD_N1_DATA_PLUGIN_FORMING_R3\artifacts\WSRTD_Data_Forming_R3.dll')
assert sha(dll)=='f0b09413fa555ea85781b8745fc6c1108e6edf7f6189fa00bfdc35e098d77647'
files=['src/admission.py','src/sender.py','independent/test_admission.py','independent/test_sender.py','independent/admission_results.json','independent/sender_results.json','R4_BOUNDED_NETWORK_ADMISSION.json','R4_FIRST_GENUINE_BTCUSDT_PILOT.md','R4_DURABLE_HANDOFF_NONREGRESSION.json']
deps=list((R/'dependencies/r3').glob('*.py'))
review={
 'reviewer':'Independent agent /root/forming_r2_review; implementation author /root',
 'completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'status':'PASS_SCOPED_OFFLINE_ADMISSION_AND_V3_FIXTURE_REVIEW',
 'overall_live_pilot_ready':False,
 'independent_checks':{'admission':a['tests'],'sender_handoff':s['tests'],'all_passed':True},
 'reviewed_hashes':{p:sha(R/p) for p in files},
 'dependency_hashes':{str(p.relative_to(R)):sha(p) for p in deps},
 'preserved_R3_DLL':{'path':str(dll),'sha256':sha(dll),'rebuilt':False},
 'network_callsite_review':[
  {'callsite':'Sender.metadata','admission':'REST_METADATA reserve before fixture request; HEALTH after; fixed exchangeInfo path; zeroREST refuses dispatch'},
  {'callsite':'Sender.history','admission':'exact symbol, minute range and499page cap; REST_KLINE reserve before fixture request; HEALTH after'},
  {'callsite':'Sender.connect','admission':'persistent WS_CONNECT aggregate and reconnect semantics before fixture connect; HEALTH after; no automatic retry'},
  {'callsite':'Sender.subscribe','admission':'connectionrequired and SUBSCRIBE reserve before fixed kline_1m stream; HEALTH after'},
  {'callsite':'Sender.source_event','admission':'FRAME bytes/count reserve, duplicateJSONkey rejection, subscribed symbol and exact pipeline session/universe/symbolset checks'},
  {'callsite':'IsolatedRelay.forward','admission':'FRAME reserve plus receiver session/universe/symbolset; frame budget deliberately counts both source and relay stages'},
  {'callsite':'production sockets/HTTP/DNS','admission':'ABSENT; FixtureBackend exacttype only. Actualnetwork hard-stop not qualified'}
 ],
 'verified_offline_properties':[
  'Request/weight/connection/subscription/frame counters persist before dispatch and are not refunded after failure.',
  'Restart reopens existing exactcontract ledger; missingledger cannot silently reset; existingfile cannot reprovision.',
  'STOP persists, wrongsession/receiver/deadline/clockrollback failclosed, concurrent calls cannot exceed testedcaps.',
  'Malformed negative/fractionalcounters rejected; modifiedcontract rejected eachreservation.',
  'RawV3x/E/t/T/f/L/volume anduniverse roundtrip to unchangedR3 disposablefinalledger; local receipts remain synthetic.',
  'No genuineconnection/backend, productionpath modification, Brokercontrol or R3rebuild occurred.'
 ],
 'closed_findings':[
  'Duplicate sourceJSON keys formerlycollapsed silently; now rejected.',
  'Unrelated pipeline session/universe/symbolset formerlyencodable; now fenced.',
  'Direct relayforward formerlyomitted aggregateframe accounting; now reserves beforedispatch.',
  'Corrupt persisted counters formerlyallowed negative/fractionalbudgetstate; now rejected.'
 ],
 'remaining_blockers':[
  'No qualified real HTTP/WebSocket backend exists; sockettimeouts/cancellation/redirects/reconnect teardown/quietexpiry cannot be inferred from fixture doubles.',
  'Producer/receiver PIDcreation declarations are not OS-attested custody; genuine sourceauthority andactual endpoint identity remain unqualified.',
  'Trustedclock authority across processdowntime/rollback not established; lastseenwallclock plus processmonotonic checks have statedlimits.',
  'Existing18101supervisor andsender unchanged; Brokerattachment can trigger500symbol legacyREST/WSstartup. Limitedgenuinepilot needs separatelyreviewed productioncontroller/output handoff.',
  'R3DLL remains FIXTURE_ONLY; actualAmiBrokerload, genuineformingbars, weeklycompression andmixedinterval settings NOT_EXECUTED.',
  'Historicalfullprefix admission remains denied; no syntheticreceipt or shortformingwindow grants completehistoricalcoverage.',
  'LiveUTCwindow, source/receiverexecutableidentity, networkweightauthority, writerphysicalidentity andhostlifecycleapproval remain UNBOUND.',
  'Review grants no deployment, producerstart, protectedrelayattachment, RESTrehydration orproductionwrite authority.'
 ],
 'production_changes':0,'protected_relay_connections':0,'binance_requests':0,
 'overall':'BLOCKED_REAL_NETWORK_BACKEND_GENUINE_CUSTODY_AND_NATIVE_HOST_ACCEPTANCE'
}
(R/'R4_INDEPENDENT_FINAL_REVIEW.json').write_text(json.dumps(review,indent=2),encoding='utf-8')
print(json.dumps({'status':review['status'],'checks':a['tests']+s['tests'],'source_hashes':{p:sha(R/p) for p in ['src/admission.py','src/sender.py']}},indent=2))
