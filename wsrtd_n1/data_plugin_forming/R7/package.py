from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parent
assert not (R/'R7_SHA256_MANIFEST.json').exists(),'existing output'
review=json.loads((R/'R7_INDEPENDENT_FINAL_REVIEW.json').read_text())
hashes=review['exact_hashes'];assert hashes,'missing independent hash binding'
for name,digest in hashes.items():assert hashlib.sha256((R/name).read_bytes()).hexdigest()==digest,('review drift',name)
files=[]
for p in R.rglob('*'):
 if not p.is_file() or any(x in p.relative_to(R).parts for x in ('build','disposable','__pycache__')) or p.name=='R7_SHA256_MANIFEST.json':continue
 files.append(dict(path=p.relative_to(R).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
(R/'R7_SHA256_MANIFEST.json').write_text(json.dumps(dict(release_approved=False,files=files),indent=2));print('R7 evidence manifest written')
