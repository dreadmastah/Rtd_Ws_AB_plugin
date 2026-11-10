from pathlib import Path
import subprocess,hashlib,json,shutil
r=Path(__file__).parent
cmake=r'C:\Program Files\CMake\bin\cmake.exe'
cmds=[[cmake,'-S',str(r/'native'),'-B',str(r/'build'),'-G','Visual Studio 18 2026','-A','x64'],[cmake,'--build',str(r/'build'),'--config','Release']]
with (r/'evidence/BUILD.log').open('w') as f:
 for cmd in cmds:
  p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
  if p.returncode:raise SystemExit('build failed; see log')
p=r/'artifacts/WSRTD_Data_Forming_R3.dll';shutil.copy2(r/'build/Release'/p.name,p)
(r/'R3_CANDIDATE_DLL_SHA256.json').write_text(json.dumps({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'commands':cmds,'installed':False},indent=2))
print(p)
