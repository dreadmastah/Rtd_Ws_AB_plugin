from pathlib import Path
import hashlib,json,shutil,sys,subprocess,datetime
R=Path(__file__).parent
for name in ('native','tests','evidence','artifacts','disposable','dependencies'):(R/name).mkdir(exist_ok=True)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
old=Path(r'D:\WSRTD_N1_DATA_PLUGIN_FORMING_R1')
baseline=Path(r'D:\WSRTD_OWNED_CPP_N1_20261028_R1')
files=[old/'REPORT.md',old/'FINAL_DISPOSITION.json',baseline/'candidate/native/owned_plugin.cpp',baseline/'candidate/native/owned_reader.cpp',Path(r'C:\Program Files\AmiBroker\Plugins\WSRTD_Owned_N1_DATABASE_BOUND.dll')]
proof={str(p):sha(p) for p in files}
assert proof[str(files[-1])]=='ae7f6bc4e9ec61c3103b48d8ee43769173b44ed1619aa61ffbcc15b513af4179'
assert proof[str(files[2])]=='73f7981797cb9cb60700579f1756b4182db8b3bf6de0677be7e864d15b5c58af'
(R/'R2_PREDECESSOR_INTEGRITY.json').write_text(json.dumps({'status':'PASS','sha256':proof},indent=2))
shutil.copytree(baseline/'dependencies/ADK/ADK/include',R/'dependencies/adk',dirs_exist_ok=True)
print('prepared isolated output; baseline hashes matched')
print('vcvars',list(Path('C:/Program Files/Microsoft Visual Studio').glob('*/**/vcvars64.bat')))
