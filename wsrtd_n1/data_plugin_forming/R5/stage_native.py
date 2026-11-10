from pathlib import Path
import shutil,subprocess,json,hashlib
R=Path(__file__).parent;P=Path(r'D:\WSRTD_N1_DATA_PLUGIN_FORMING_R3')
shutil.copytree(P/'dependencies/adk',R/'dependencies/adk',dirs_exist_ok=True)
for n in ('native/plugin.cpp','native/CMakeLists.txt','tests/native_probe.cpp'):
 s=(P/n).read_text().replace('FORMING_R3','FORMING_R5').replace('Forming_R3','Forming_R5').replace('Forming R3','Forming R5').replace('WFR3','WFR5').replace("'R','3'","'R','5'").replace('R3Metrics','R5Metrics').replace('50303','50505')
 (R/n).write_text(s)
shutil.copy2(P/'src/fixture_pipe.py',R/'src/fixture_pipe.py')
p=R/'src/fixture_pipe.py';p.write_text(p.read_text().replace('FORMING_R3','FORMING_R5'))
cmake=r'C:\Program Files\CMake\bin\cmake.exe'
with (R/'evidence/BUILD.log').open('w') as f:
 for cmd in ([cmake,'-S',str(R/'native'),'-B',str(R/'build'),'-G','Visual Studio 18 2026','-A','x64'],[cmake,'--build',str(R/'build'),'--config','Release']):subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
p=R/'artifacts/WSRTD_Data_Forming_R5.dll';shutil.copy2(R/'build/Release'/p.name,p)
(R/'evidence/DLL_BUILD.json').write_text(json.dumps({'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'file':str(p),'change':'isolated output-path/ID/version namespace only; R3native logic unchanged','installed':False},indent=2));print(p)
