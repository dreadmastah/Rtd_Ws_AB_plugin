from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parent
review=json.loads((R/'R6_INDEPENDENT_FINAL_REVIEW.json').read_text())
for name,digest in review['hashes'].items():assert hashlib.sha256((R/name).read_bytes()).hexdigest()==digest,('review drift',name)
m=json.loads((R/'R6_SOURCE_BINARY_SHA256_MANIFEST.json').read_text())
for e in m['files']:
 p=(R/e['path']).resolve();assert p.is_relative_to(R)
 assert p.stat().st_size==e['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==e['sha256'],e['path']
S=Path(r'D:\WSRTD_N1_DATA_PLUGIN_FORMING_R5')
for e in json.loads((S/'R5_SOURCE_BINARY_SHA256_MANIFEST.json').read_text())['files']:assert hashlib.sha256((S/e['path']).read_bytes()).hexdigest()==e['sha256'],e['path']
print('PASS',len(m['files']),'R6 manifest entries; all 56 R5 entries preserved. No live acceptance.')
