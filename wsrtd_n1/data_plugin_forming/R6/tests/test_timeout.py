from pathlib import Path
import sys,time,json,threading
R=Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'src'),str(R/'tests')]
from test_network import Tests
rows=[]
for contention in (False,True):
 for i in range(5):
  test=Tests();test.setUp();b,s=test.setup_backend('timeout');stop=threading.Event()
  def competing():
   while not stop.wait(.002):
    try:b.control.reserve('HEALTH',**b.bindings)
    except Exception:return
  worker=threading.Thread(target=competing);worker.start() if contention else None
  start=time.perf_counter_ns();error=None
  try:b.http('metadata')
  except Exception as e:error=type(e).__name__+':'+str(e)
  end=time.perf_counter_ns();trace=list(b.trace);empty=not b.sockets;stop.set()
  if contention:worker.join(2)
  test.tearDown()
  rows.append(dict(contention=contention,index=i,elapsed_seconds=(end-start)/1e9,error=error,sockets_empty=empty,connections=s.count,trace=trace,pass_bound=(end-start)<1500000000))
out=dict(predecessor_failure_seconds=1.609,threshold_seconds=1.5,historical_root_cause='UNPROVEN: original trace unavailable',demonstrated_defect='R5 starts deadline after durable REST and connection debits; R6 propagates HTTP ingress deadline through admission and reads',results=rows,passed=all(x['pass_bound'] and x['error'] and x['sockets_empty'] and x['connections']<=1 for x in rows),guarantee='Measured Windows runs only; OS scheduling and fsync are not hard real-time guarantees')
(R/'R6_TIMEOUT_ROOT_CAUSE_AND_REGRESSION.json').write_text(json.dumps(out,indent=2));print(out['passed'],max(x['elapsed_seconds'] for x in rows))
