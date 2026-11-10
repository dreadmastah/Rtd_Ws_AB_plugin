from pathlib import Path
import json,hashlib
root=Path(__file__).resolve().parent
data=json.loads((root/'ARCHIVE_INVENTORY.json').read_text())
for e in data['files']:
 p=(root/e['path']).resolve()
 assert p.is_relative_to(root),e['path']
 assert p.stat().st_size==e['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==e['sha256'],e['path']
print('PASS',len(data['files']),'exact-byte archived artifacts; omissions remain documented')
