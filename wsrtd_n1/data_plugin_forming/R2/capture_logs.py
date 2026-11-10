from pathlib import Path
import json,hashlib,re,datetime
R=Path(__file__).parent;root=Path(r'D:\WSRTD_PR3_Test_20261010\persistent-feed-20261010')
out=[]
for name in ('status.json','sender.log','relay.log','supervisor.stderr.log','supervisor.stdout.log','supervise_test_feed.py','selected-symbols.txt'):
 p=root/name
 if not p.exists():continue
 st=p.stat()
 with p.open('rb') as f:
  if name.endswith('.log'):f.seek(max(0,st.st_size-16384))
  b=f.read(65536)
 text=b.decode('utf-8',errors='replace')
 lines=[line for line in text.splitlines() if any(x in line.lower() for x in ('sender','error','18101','exit','symbol','invalid','backoff','connect','pid'))]
 out.append({'path':str(p),'size':st.st_size,'mtime_utc':datetime.datetime.fromtimestamp(st.st_mtime,datetime.timezone.utc).isoformat(),'bounded_read_sha256':hashlib.sha256(b).hexdigest(),'relevant_lines':lines[-30:],'live_proof':False})
(R/'evidence/BOUNDED_EXISTING_LOGS.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
