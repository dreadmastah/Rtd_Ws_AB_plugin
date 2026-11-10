"""Future PHASE_A operator entry point. No default manifest or automatic start."""
import argparse,json,hashlib,time,os
import sys
from pathlib import Path
from external import ExternalWS,validate
from custody import Attestation
from storage import ParentCustody
from admission import Controller
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'dependencies/r3'))
from transport import Receiver,envelope,signed
def main():
 p=argparse.ArgumentParser();p.add_argument('--manifest');p.add_argument('--approved-sha256');p.add_argument('--prepare-and-wait',action='store_true');p.add_argument('--execute-phase-a',action='store_true');a=p.parse_args()
 if a.prepare_and_wait:
  actor=Attestation(os.getpid());print(json.dumps(dict(state='HELD_NO_NETWORK',producer=actor.check())),flush=True);actor.close()
  approval=json.loads(input(),object_pairs_hook=Receiver._pairs)
  if set(approval)!={'manifest','approved_sha256','execute_phase_a'} or approval['execute_phase_a'] is not True:raise ValueError('exact approval input')
  a.manifest=approval['manifest'];a.approved_sha256=approval['approved_sha256'];a.execute_phase_a=True
 if not a.execute_phase_a:raise SystemExit('explicit execution flag required')
 raw=Path(a.manifest).read_bytes()
 if len(raw)>65536:raise ValueError('manifest limit')
 m=json.loads(raw,object_pairs_hook=Receiver._pairs);out=validate(m,a.approved_sha256,False)
 if not ParentCustody.QUALIFIED_FOR_LIVE_WRITES:raise ValueError('BLOCKED_WRITER_CUSTODY: directory rename exclusion not qualified')
 # One-shot output must be newly created; no overwriting existing receipt or budget.
 custody=ParentCustody(m['storage_parent_identity']);ctl=None;backend=None
 try:
  custody.check();out.mkdir(exist_ok=False);ledger=out/'admission.sqlite';Controller.provision(ledger,m['contract']);ctl=Controller(ledger,m['contract'])
  with (out/'events.jsonl').open('x',encoding='utf-8') as f:
   backend=ExternalWS(ctl,m,a.approved_sha256);backend.connect_ws()
   validator=Receiver(m['contract']['producer_session'],b'v'*32,['BTCUSDT'])
   while time.time_ns()//1000000<m['contract']['end_ms']:
    body=backend.receive()
    event=json.loads(body,object_pairs_hook=Receiver._pairs)
    # Schema validation uses fixture-labelled internal envelope only; raw capture is
    # never promoted to finalized native history or synthetic genuine provenance.
    candle=envelope(event,m['contract']['producer_session'],time.time_ns()//1000000,{'BTCUSDT':('UM','PERPETUAL')})
    outcome=validator.ingest(signed(candle,b'v'*32))
    if outcome.startswith('INVALID'):raise ValueError(outcome)
    record=dict(schema=1,source_url=m['url'],producer=m['producer'],session=m['contract']['producer_session'],received_utc_ms=time.time_ns()//1000000,raw_utf8=body.decode(),sha256=hashlib.sha256(body).hexdigest(),provenance='CAPTURE_PENDING_INDEPENDENT_QUALIFICATION',full_prefix_complete=False)
    custody.check();f.write(json.dumps(record,separators=(',',':'))+'\n');f.flush();os.fsync(f.fileno())
 finally:
  if backend:backend.close()
  if ctl:ctl.close()
  custody.close()
if __name__=='__main__':main()
