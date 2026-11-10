from pathlib import Path
import json,hashlib,sys
r=Path(__file__).parent
m=json.loads((r/'R2_SOURCE_BINARY_SHA256_MANIFEST.json').read_text())
bad=[]
for name,digest in m['files'].items():
 p=r/name
 if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:bad.append(name)
print(json.dumps({'entries':len(m['files']),'failures':bad,'status':'PASS' if not bad else 'BLOCKED','live_acceptance':False}))
sys.exit(bool(bad))
