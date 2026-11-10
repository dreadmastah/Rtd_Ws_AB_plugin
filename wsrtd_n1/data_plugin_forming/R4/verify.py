from pathlib import Path
import json,hashlib,sys
r=Path(__file__).parent;m=json.loads((r/'R4_SOURCE_BINARY_SHA256_MANIFEST.json').read_text());bad=[]
for n,h in m['files'].items():
 p=r/n
 if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=h:bad.append(n)
print(json.dumps({'status':'PASS' if not bad else 'BLOCKED','entries':len(m['files']),'failures':bad,'production_ready':False}));sys.exit(bool(bad))
