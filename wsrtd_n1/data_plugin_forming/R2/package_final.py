from pathlib import Path
import json,hashlib,datetime,sys
R=Path(__file__).parent
def read(p):return json.loads((R/p).read_text())
def put(p,o):(R/p).write_text(json.dumps(o,indent=2),encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
review=read('R2_INDEPENDENT_FINAL_REVIEW.json')
print('review',review.get('verdict',review.get('status')))
native=read('independent/native_results.json');assert native['dll_sha256']==sha(R/'artifacts/WSRTD_Data_Forming_R2.dll')
receiver=read('independent/receiver_results.json');assert receiver['source_sha256']==sha(R/'transport.py')
assert native['passed'] and receiver['passed']
status_path=Path(r'D:\WSRTD_PR3_Test_20261010\persistent-feed-20261010\status.json')
status=json.loads(status_path.read_text());chain=read('R2_18101_PROCESS_AND_SOURCE_CHAIN.json')
supervisors=[p for p in chain['processes'] if p['pid']==status['supervisor_pid']]
assert supervisors and abs(supervisors[0]['create_time']-status['supervisor_created'])<.01
assert status['source_root'].lower()==r'D:\WSRTD_PR3_Test_20261010\releases\a2401ca'.lower()
inactive=status['sender_pid'] is None and status['sender_running'] is False
put('R2_18101_PRODUCER_READINESS.json',{'status':'BLOCKED','current_producer':'INACTIVE' if inactive else 'UNVERIFIED','evidence':status,'supervisor_creation_identity_matched':True,'limitation':'Point-in-time supervisor status corroborated by process census, not proof of all possible upstream activity.','reason':'Supervisor requires a Broker.exe connection to18101; none reported. Existing sender log previously rejected pinned invalid symbols.','future_external_adapter_issue':'Non-Broker receiver alone does not satisfy native_receivers(); connecting a qualified Broker triggers sender and REST rehydration. Requires separately reviewed controller/output changes and activation approval.','historical_log_symbols_not_current_eligibility':['EPICUSDT','MITOUSDT','PTBUSDT','VELODROMEUSDT'],'restoration_authorized':False})
chain['current_producer']='INACTIVE' if inactive else 'UNVERIFIED'
chain['source_chain']='QUALIFIED_CONFIGURED_PATH_NOT_LIVE';chain['corroborating_status']=status
for c in chain['components']:
 if c['PROCESS_ROLE'] in ('sender','upstream_producer','acquisition'):
  c['LIVE_STATUS_EVIDENCE']='Corroborated supervisor sender_running=false, sender_pid=null; known configured sender inactive at observation.'
  c['SOURCE_PATH']=r'D:\WSRTD_PR3_Test_20261010\releases\a2401ca\Binance\sender.py';c['SOURCE_SHA256']=sha(Path(c['SOURCE_PATH']))
 if c['PROCESS_ROLE']=='listener':c['PROCESS_IDENTITIES']=[p for p in c['PROCESS_IDENTITIES'] if p['pid']==119852]
 if c['PROCESS_ROLE'] in ('relay','listener'):
  c['SOURCE_PATH']=r'D:\WSRTD_PR3_Test_20261010\releases\a2401ca\Relay\Server\Python\relay.py';c['SOURCE_SHA256']=sha(Path(c['SOURCE_PATH']));c['INPUT_PROTOCOL']='WebSocket path /sender';c['OUTPUT_PROTOCOL']='broadcast to /receiver or /; receiver commands upstream'
put('R2_18101_PROCESS_AND_SOURCE_CHAIN.json',chain)
p=R/'R2_18101_PROTOCOL_GAP_ANALYSIS.md'
p.write_text(p.read_text()+'''\n## Refreshed configured-chain evidence\n\nBounded existing status/log/source inspection corroborates the configured18101 sender is INACTIVE at observation: status sender_pid=null and sender_running=false, supervisor PID26188 creation matches process census. The supervisor detects only Broker.exe at the installed path with an established18101 socket. A helper receiver does not satisfy this rule. A Broker connection can launch the sender with --native-history --quotes and cause REST rehydration. Do not treat either connection type as a qualified passive path.\n\nHistorical sender-log tail records strict pinned-universe rejection of EPICUSDT, MITOUSDT, PTBUSDT and VELODROMEUSDT. This identifies the old failure, not current eligible membership. Do not delete those symbols/history or silently replace the pinned configuration. Output metadata correction, receiver-gating compatibility and separately authorized restoration remain required.\n''')
final=read('R2_FINAL_DISPOSITION.json');final['18101_CURRENT_PRODUCER']='INACTIVE' if inactive else 'UNVERIFIED';final['18101_SOURCE_CHAIN']='QUALIFIED_CONFIGURED_CHAIN_LIVE_DELIVERY_BLOCKED';final['INDEPENDENT_REVIEW']='PASS_SCOPED_OFFLINE_FIXTURE_IMPLEMENTATION_REVIEW';final['OVERALL']='BLOCKED_GENUINE_INTEGRATION_AND_NATIVE_HOST_GATES';final['independent_native_checks']=len(native['tests']);final['dll_sha256']=native['dll_sha256'];final['blockers']=[s for s in final['blockers'] if not s.startswith('Independent final')];final['blockers'][0]='Configured18101 sender observed inactive; supervisor Broker-only receiver gate, legacy pinned universe and metadata output require separately qualified correction/restoration.'
put('R2_FINAL_DISPOSITION.json',final)
put('R2_DATA_PLUGIN_NATIVE_API_TESTS.json',{'status':'PASS_OFFLINE_TESTED_CALLBACKS','independent':'independent/native_results.json','checks':len(native['tests']),'actual_amibroker':False,'dll_sha256':native['dll_sha256'],'limitations':['real host not executed','daily callback parity absent','per-symbol acknowledgment completion absent','fixture-only database scope']})
sys.path.insert(0,r'D:\WSRTD_N1_ACTIVE_CHART_RADAR_R1\retirement_controller_r1');import r3_observer as ob
after={};baseline={p['pid']:p for p in chain['processes']}
for pid in (92688,62440,114976,116276,119852,126792,26188):
 with ob.opened(pid) as h:
  _,created,exe=ob.handle_identity(h)
  after[str(pid)]={'creation':created,'same_creation':created==baseline[pid]['creation_filetime'],'exe':exe}
put('evidence/PROTECTED_PROCESS_AFTER.json',{'processes':after,'listeners10101':ob.listeners(10101),'listeners18101':ob.listeners(18101),'process_control_operations':0,'connections_to_protected_ports':0})
assert all(p['same_creation'] for p in after.values())
paths=[p for p in R.rglob('*') if p.is_file() and not any(x in p.relative_to(R).parts for x in ('build','disposable','__pycache__')) and p.name!='R2_SOURCE_BINARY_SHA256_MANIFEST.json']
put('R2_SOURCE_BINARY_SHA256_MANIFEST.json',{'type':'evidence inventory, NOT release seal','files':{str(p.relative_to(R)).replace('\\','/'):sha(p) for p in sorted(paths)}})
print('packaged',len(paths),'files; no deployment')
