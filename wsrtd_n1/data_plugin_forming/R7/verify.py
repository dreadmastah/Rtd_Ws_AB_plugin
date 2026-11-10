from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parent
review=json.loads((R/'R7_INDEPENDENT_FINAL_REVIEW.json').read_text())
hashes=review['exact_hashes'];assert hashes
for name,digest in hashes.items():assert hashlib.sha256((R/name).read_bytes()).hexdigest()==digest,('independent review drift',name)
m=json.loads((R/'R7_SHA256_MANIFEST.json').read_text())
for e in m['files']:
 p=(R/e['path']).resolve();assert p.is_relative_to(R)
 assert p.stat().st_size==e['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==e['sha256'],e['path']
S=Path(r'D:\WSRTD_N1_DATA_PLUGIN_FORMING_R6')
for e in json.loads((S/'R6_SOURCE_BINARY_SHA256_MANIFEST.json').read_text())['files']:assert hashlib.sha256((S/e['path']).read_bytes()).hexdigest()==e['sha256'],e['path']
print('PASS',len(m['files']),'R7 entries; all 57 R6 entries preserved. Not live acceptance.')
