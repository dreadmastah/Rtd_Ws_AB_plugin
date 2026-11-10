from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parent;assert not (R/'R8_SHA256_MANIFEST.json').exists()
review=json.loads((R/'R8_INDEPENDENT_FINAL_REVIEW.json').read_text());hashes=review.get('exact_hashes',review.get('hashes',{}));assert hashes
for name,digest in hashes.items():assert hashlib.sha256((R/name).read_bytes()).hexdigest()==digest,('review drift',name)
state=json.loads((R/'R8_FINAL_DISPOSITION.json').read_text());state['INDEPENDENT_REVIEW']='PASS_SCOPED';(R/'R8_FINAL_DISPOSITION.json').write_text(json.dumps(state,indent=2))
files=[]
for p in R.rglob('*'):
 if not p.is_file() or any(x in p.relative_to(R).parts for x in ('disposable','__pycache__','build')) or p.name=='R8_SHA256_MANIFEST.json':continue
 files.append(dict(path=p.relative_to(R).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
(R/'R8_SHA256_MANIFEST.json').write_text(json.dumps(dict(release_approved=False,files=files),indent=2));print(len(files),'R8 evidence entries')
