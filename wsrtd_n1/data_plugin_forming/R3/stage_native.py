from pathlib import Path
import shutil
R=Path(__file__).parent;P=Path(r'D:\WSRTD_N1_DATA_PLUGIN_FORMING_R2')
p=R/'native/plugin.cpp';s=p.read_text().replace('FORMING_R2','FORMING_R3').replace('Forming R2','Forming R3').replace('WFR2','WFR3').replace("'R','2'","'R','3'").replace('50202','50303').replace('FORMING_R2/disposable','FORMING_R3/disposable').replace('R2Metrics','R3Metrics')
p.write_text(s)
for source,dest in [('tests/native_probe.cpp','tests/native_probe.cpp'),('independent/test_native.py','tests/test_native_inherited.py')]:
 s=(P/source).read_text().replace('FORMING_R2','FORMING_R3').replace('Forming_R2','Forming_R3').replace('WFR2','WFR3').replace("'R','2'","'R','3'").replace('R2Metrics','R3Metrics')
 if dest.endswith('.py'):
  s=s.replace("sys.path.insert(0,str(ROOT))","sys.path.insert(0,str(ROOT/'src'))")
 (R/dest).write_text(s)
s=(R/'native/CMakeLists.txt').read_text().replace('FORMING_R2','FORMING_R3').replace('Forming_R2','Forming_R3');(R/'native/CMakeLists.txt').write_text(s)
s=(R/'src/fixture_pipe.py').read_text().replace('FORMING_R2','FORMING_R3');(R/'src/fixture_pipe.py').write_text(s)
for n in ('transport.py','fixture_pipe.py'):
 # Top-level modules simplify inherited harness import; source lives in src.
 (R/n).write_text('from src.'+n[:-3]+' import *\n')
s=(P/'build.py').read_text().replace('Forming_R2','Forming_R3').replace('R2_DATA_PLUGIN_CANDIDATE_SHA256','R3_CANDIDATE_DLL_SHA256');(R/'build.py').write_text(s)
print('distinct native source staged')
