import json,time,pathlib
from test_socket import Tests,R
prior=json.loads((R/'independent/final_edges_results.json').read_text())
(R/'independent/final_edges_timing_outlier.json').write_text(json.dumps(prior,indent=2))
results=[]
for i in range(3):
 t=Tests();t.setUp()
 try:
  b,s,_,_=t.setup('timeout');start=time.monotonic()
  try:b.http('metadata');raise AssertionError('expected timeout')
  except (TimeoutError,OSError):pass
  elapsed=time.monotonic()-start
  assert not b.sockets and s.count==1
  results.append(dict(elapsed_seconds=elapsed,sockets_closed=True,attempts=s.count))
 finally:t.tearDown()
(R/'independent/timing_recheck.json').write_text(json.dumps(dict(results=results,interpretation='Operation transport deadline is 1 second; whole-call timing includes durable admission and host scheduling. Earlier 1.609 second outlier preserved; no strict 1.5 second end-to-end guarantee.'),indent=2));print(results)
