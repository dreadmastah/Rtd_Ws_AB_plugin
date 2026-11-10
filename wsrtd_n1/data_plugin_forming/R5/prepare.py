from pathlib import Path
import json,hashlib,shutil
R=Path(__file__).parent;P=Path(r'D:\WSRTD_N1_DATA_PLUGIN_FORMING_R4');N=Path(r'D:\WSRTD_N1_DATA_PLUGIN_FORMING_R3')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=json.loads((P/'R4_SOURCE_BINARY_SHA256_MANIFEST.json').read_text());assert all(sha(P/n)==h for n,h in m['files'].items())
for n in ('src','tests','evidence','disposable','dependencies/r3','dependencies/disposable','independent','native','artifacts'):(R/n).mkdir(parents=True,exist_ok=True)
shutil.copy2(P/'src/admission.py',R/'src/admission.py')
for n in ('transport.py','pipeline.py','durable.py'):shutil.copy2(N/'src'/n,R/'dependencies/r3'/n)
(R/'R5_PREDECESSOR_INTEGRITY.json').write_text(json.dumps({'status':'PASS','R4_root':str(P),'R4_hashes':m['files'],'R3_DLL':str(N/'artifacts/WSRTD_Data_Forming_R3.dll'),'R3_DLL_SHA256':sha(N/'artifacts/WSRTD_Data_Forming_R3.dll')},indent=2))
print('verified/staged isolatedR5')
