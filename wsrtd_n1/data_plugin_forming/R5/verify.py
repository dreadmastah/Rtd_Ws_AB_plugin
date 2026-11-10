from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parent
m=json.loads((R/'R5_SOURCE_BINARY_SHA256_MANIFEST.json').read_text())
for e in m['files']:
 p=(R/e['path']).resolve();assert p.is_relative_to(R)
 assert p.stat().st_size==e['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==e['sha256'],e['path']
review=json.loads((R/'R5_INDEPENDENT_FINAL_REVIEW.json').read_text())
for n,h in review['source_and_binary_hashes'].items():assert hashlib.sha256((R/n).read_bytes()).hexdigest()==h,n
assert hashlib.sha256(Path(r'D:\WSRTD_N1_DATA_PLUGIN_FORMING_R3\artifacts\WSRTD_Data_Forming_R3.dll').read_bytes()).hexdigest()=='f0b09413fa555ea85781b8745fc6c1108e6edf7f6189fa00bfdc35e098d77647'
print(f"PASS {len(m['files'])} manifest entries; independent hashes and preserved R3 DLL match. Not live acceptance.")
