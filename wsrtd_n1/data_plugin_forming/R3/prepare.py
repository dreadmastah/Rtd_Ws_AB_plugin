from pathlib import Path
import json,hashlib,shutil
R=Path(__file__).parent;P=Path(r'D:\WSRTD_N1_DATA_PLUGIN_FORMING_R2')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=json.loads((P/'R2_SOURCE_BINARY_SHA256_MANIFEST.json').read_text())
assert all(sha(P/n)==h for n,h in m['files'].items())
assert sha(P/'artifacts/WSRTD_Data_Forming_R2.dll')=='8ac9987e6588b3c8f5c1ce7b35481e931a58b6145672b8fa09ed570ad547ec01'
for n in ('src','tests','evidence','disposable','artifacts','native','dependencies'):(R/n).mkdir(exist_ok=True)
for n in ('transport.py','fixture_pipe.py'):shutil.copy2(P/n,R/'src'/n)
shutil.copytree(P/'dependencies',R/'dependencies',dirs_exist_ok=True)
for n in ('plugin.cpp','CMakeLists.txt'):shutil.copy2(P/'native'/n,R/'native'/n)
for n in ('R2_FINAL_DISPOSITION.json','R2_INDEPENDENT_FINAL_REVIEW.json','R2_WINDOWS_CMD_VERIFICATION.md'):shutil.copy2(P/n,R/'evidence'/n)
(R/'R3_PREDECESSOR_INTEGRITY.json').write_text(json.dumps({'status':'PASS','entries':len(m['files']),'manifest_sha256':sha(P/'R2_SOURCE_BINARY_SHA256_MANIFEST.json'),'baseline_hashes':m['files'],'review_scope_caveat':'R2 final packaging changed chain report after independent review; review does not cover that later report hash.'},indent=2))
print('R2 verified; isolated R3 source staged')
