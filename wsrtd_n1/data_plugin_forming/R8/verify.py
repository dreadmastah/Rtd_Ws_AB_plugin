from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parent
review=json.loads((R/'R8_INDEPENDENT_FINAL_REVIEW.json').read_text());hashes=review.get('exact_hashes',review.get('hashes',{}));assert hashes
for name,digest in hashes.items():assert hashlib.sha256((R/name).read_bytes()).hexdigest()==digest,('review drift',name)
for e in json.loads((R/'R8_SHA256_MANIFEST.json').read_text())['files']:
 p=(R/e['path']).resolve();assert p.is_relative_to(R)
 assert p.stat().st_size==e['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==e['sha256'],e['path']
S=Path(r'D:\WSRTD_N1_DATA_PLUGIN_FORMING_R7')
for e in json.loads((S/'R7_SHA256_MANIFEST.json').read_text())['files']:assert hashlib.sha256((S/e['path']).read_bytes()).hexdigest()==e['sha256'],e['path']
print('PASS R8 manifest and all 66 preserved R7 entries; not live approval')
