from pathlib import Path
import sys,json,hashlib,secrets
from unittest.mock import patch
R=Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'src')]
import capture
root=R/'disposable';path=root/('ind_manifest_'+secrets.token_hex(6)+'.json');out=root/('never_created_'+secrets.token_hex(6));path.write_text('{}')
with patch.object(sys,'argv',['capture','--manifest',str(path),'--approved-sha256','0'*64,'--execute-phase-a']),patch.object(capture,'validate',return_value=out),patch.object(capture,'ExternalWS',side_effect=AssertionError('network constructor reached')):
 try:capture.main();raise AssertionError('writer gate bypassed')
 except ValueError as e:assert str(e).startswith('BLOCKED_WRITER_CUSTODY')
assert not out.exists()
report=dict(passed=True,scope='Writer gate after manifest validation, before output creation/network construction',manifest_validation_mocked=True,external_requests=0,production_changes=0,source_hashes={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (R/'src').glob('*.py')})
(R/'independent/capture_block_result.json').write_text(json.dumps(report,indent=2));print('writer guard refusal PASS')
