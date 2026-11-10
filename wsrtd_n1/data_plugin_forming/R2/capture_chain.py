from pathlib import Path
import json,hashlib,datetime,subprocess
import sys
sys.path.insert(0,r'D:\WSRTD_N1_ACTIVE_CHART_RADAR_R1\retirement_controller_r1')
import r3_observer as ob
R=Path(__file__).parent
def sha(p):
 try:return hashlib.sha256(Path(p).read_bytes()).hexdigest()
 except OSError:return None
process=[]
for pid,basic in ob.nt_processes().items():
 try:
  if basic['image'].lower() not in ('broker.exe','python.exe','pythonw.exe','node.exe'):continue
  with ob.opened(pid) as handle:
   apid,created,exe=ob.handle_identity(handle);args=ob.arguments(handle)
  if created!=basic['creation']:raise ValueError('PID reuse')
  x={'pid':pid,'ppid':basic['parent'],'name':basic['image'],'exe':exe,'cmdline':args,'creation_filetime':created,'create_time':(created-116444736000000000)/10000000}
  text=' '.join(x['cmdline'] or [])
  if not any(s.lower() in text.lower() for s in ('WSRTD','CleanRoomR2','Broker.exe')):continue
  x['executable_sha256']=sha(x['exe']);x['creation_local']=datetime.datetime.fromtimestamp(x['create_time']).astimezone().isoformat()
  x['source_files']=[{'path':a,'sha256':sha(a)} for a in x['cmdline'] if a.endswith(('.py','.js')) and Path(a).is_file()]
  process.append(x)
 except (OSError,ValueError,RuntimeError):continue
raw=subprocess.run(['netstat','-ano','-p','tcp'],capture_output=True,text=True,check=True).stdout
connections=[line.strip() for line in raw.splitlines() if ':10101 ' in line or ':18101 ' in line]
sender=Path(r'D:\WSRTD_PR3_Test_20261010\releases\a2401ca\Binance\sender.py')
roles=[]
for role in ('upstream_producer','acquisition','sender','relay','listener','consumer','intended_receiver'):
 matches=[p for p in process if (role in ('relay','listener') and any('18101'==a for a in p['cmdline'])) or (role=='intended_receiver' and p['name'].lower()=='broker.exe')]
 roles.append({'PROCESS_ROLE':role,'PROCESS_IDENTITIES':matches,'SOURCE_PATH':str(sender) if role=='sender' else None,
 'SOURCE_SHA256':sha(sender) if role=='sender' else None,'INPUT_PROTOCOL':'Binance kline WebSocket JSON' if role=='sender' else 'UNVERIFIED',
 'OUTPUT_PROTOCOL':'legacy OHLCV JSON drops E/x' if role=='sender' else 'UNVERIFIED','EVENT_SCHEMA':'n,d,t,o,h,l,c,v' if role=='sender' else None,
 'LIVE_STATUS_EVIDENCE':'snapshot only; no live payload connection','UNRESOLVED_LIMITATIONS':'No matching process is not proof of inactive upstream; no production connection authorized'})
out={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'components':roles,'processes':process,'endpoints':connections,'current_producer':'UNVERIFIED','source_chain':'BLOCKED','production_connections_opened':0}
(R/'R2_18101_PROCESS_AND_SOURCE_CHAIN.json').write_text(json.dumps(out,indent=2))
print('read-only process/socket evidence captured',len(process),len(connections))
