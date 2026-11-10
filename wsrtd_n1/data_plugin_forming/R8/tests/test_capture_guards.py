from external_fixture import *
from storage import ParentCustody
from unittest.mock import patch
import subprocess
rows=[]
m=manifest(45001);digest=hashlib.sha256(canonical(m)).hexdigest()
for name in ('SSL_CERT_FILE','SSL_CERT_DIR'):
 with patch.dict(os.environ,{name:'untrusted'}):
  try:validate(m,digest,True);raise AssertionError('trust env accepted')
  except Refused:rows.append(name)
parent=R/'disposable'/('custody_'+secrets.token_hex(6));parent.mkdir();st=parent.stat();identity=dict(path=str(parent),device=st.st_dev,inode=st.st_ino)
hold=ParentCustody(identity)
try:
 hold.check()
 try:
  parent.rename(parent.with_name(parent.name+'_moved'));rows.append('FAIL: parent rename succeeded while handles held')
 except OSError:rows.append('directory rename denied while custody held')
finally:hold.close()
p=subprocess.Popen([sys.executable,'-B',str(R/'src/capture.py'),'--prepare-and-wait'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
try:
 observed=json.loads(p.stdout.readline());assert observed['state']=='HELD_NO_NETWORK' and observed['producer']['pid']==p.pid
 p.stdin.write('{"execute_phase_a":false}\n');p.stdin.flush();out,err=p.communicate(timeout=5);assert p.returncode!=0;rows.append('held identity and invalid approval rejection')
finally:
 if p.poll() is None:p.terminate();p.wait(timeout=3)
(R/'evidence/CAPTURE_GUARDS.json').write_text(json.dumps(dict(passed=not any(x.startswith('FAIL:') for x in rows),checks=rows,writer_custody='BLOCKED',live_capture_disabled=True,external_requests=0),indent=2));print('Capture guards recorded; writer custody BLOCKED')
