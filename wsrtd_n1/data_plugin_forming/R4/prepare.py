from pathlib import Path
import json,hashlib,shutil
R=Path(__file__).parent;P=Path(r'D:\WSRTD_N1_DATA_PLUGIN_FORMING_R3')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=json.loads((P/'R3_SOURCE_BINARY_SHA256_MANIFEST.json').read_text());assert all(sha(P/n)==v for n,v in m['files'].items())
assert sha(P/'artifacts/WSRTD_Data_Forming_R3.dll')=='f0b09413fa555ea85781b8745fc6c1108e6edf7f6189fa00bfdc35e098d77647'
for n in ('src','tests','evidence','disposable','dependencies/r3','dependencies/disposable','independent'):(R/n).mkdir(parents=True,exist_ok=True)
for n in ('durable.py','transport.py','pipeline.py'):shutil.copy2(P/'src'/n,R/'dependencies/r3'/n)
(R/'R4_PREDECESSOR_INTEGRITY.json').write_text(json.dumps({'status':'PASS','entries':len(m['files']),'hashes':m['files'],'root':str(P),'dependency_copies':{n:sha(R/'dependencies/r3'/n) for n in ('durable.py','transport.py','pipeline.py')},'dll_sha256':sha(P/'artifacts/WSRTD_Data_Forming_R3.dll')},indent=2))
shutil.copy2(P/'R3_INDEPENDENT_FINAL_REVIEW.json',R/'evidence/R3_INDEPENDENT_FINAL_REVIEW.json')
print('R3 verified; unchanged dependency sources copied; no DLL rebuild')
