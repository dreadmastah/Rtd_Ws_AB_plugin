from pathlib import Path
import subprocess,shutil,hashlib,json
R=Path(__file__).resolve().parent
for p in (R/'native/plugin.cpp',R/'tests/native_probe.cpp'):
 p.write_text(p.read_text().replace("'R','5'","'R','6'").replace('Forming R5','Forming R6').replace('R5Metrics','R6Metrics'))
with (R/'evidence/BUILD.log').open('w') as out:
 subprocess.run(['cmake','-S',str(R/'native'),'-B',str(R/'build'),'-G','Visual Studio 18 2026','-A','x64'],check=True,stdout=out,stderr=out)
 subprocess.run(['cmake','--build',str(R/'build'),'--config','Release'],check=True,stdout=out,stderr=out)
p=R/'artifacts/WSRTD_Data_Forming_R6.dll';shutil.copy2(R/'build/Release'/p.name,p)
(R/'evidence/DLL_BUILD.json').write_text(json.dumps(dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),file=str(p),installed=False),indent=2));print('R6 DLL built')
