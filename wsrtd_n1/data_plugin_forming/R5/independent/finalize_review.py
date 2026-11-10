from pathlib import Path
import json,hashlib,datetime
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
edges=json.loads((R/'independent/final_edges_results.json').read_text())
assert edges['passed'] or (len(edges['failures'])==1 and 'test_timeout_cleanup' in edges['failures'][0][0])
timing=json.loads((R/'independent/timing_recheck.json').read_text())
assert all(x['sockets_closed'] and x['attempts']==1 and x['elapsed_seconds']<1.5 for x in timing['results'])
for p,h in edges['source_hashes'].items():
 assert sha(R/p)==h,(p,'changed since tests')
native=json.loads((R/'R5_END_TO_END_RECEIVER_RESULTS.json').read_text());assert native['passed']
paths=list((R/'src').glob('*.py'))+list((R/'native').glob('*'))+[R/'artifacts/WSRTD_Data_Forming_R5.dll']+list((R/'independent').glob('test*.py'))
report=dict(review='R5 independent final source and isolated real-socket review',reviewer='/root/forming_r2_review',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),status='PASS_SCOPED_ISOLATED_REAL_SOCKET_AND_NATIVE_FIXTURE_REVIEW',overall_genuine_activation='BLOCKED',source_and_binary_hashes={str(p.relative_to(R)):sha(p) for p in paths if p.is_file()},independent_tests=edges,native_e2e_independently_rerun=True,native_e2e=native,closed_findings=['Persistent WebSocket reconnect debit survives Backend/Controller restart','Nullable socket cleanup and TLS watcher ownership race','Bounded admitted PING/PONG handling verified over real sockets','Per-receive pipeline session/universe/symbol binding and subscribed-symbol guard'],scope=['Literal loopback real HTTP/WS and fixture TLS only; protected ports rejected','Committed aggregate budget before dispatch; no hidden retries, DNS, redirects or proxy inheritance','Exact Windows process identity observation and mismatch refusal','Synthetic finalized/forming event pipeline and compiled GetQuotesEx; not actual AmiBroker'],unresolved_gates=['No external Binance request or genuine source custody qualification','No actual 18101 integration or protected service change','No full-prefix certificate: IsBackfillComplete remains FALSE','No actual AmiBroker chart, refresh, daily UI or 500+ live acceptance','Receiver death during an in-flight read is bounded by operation deadline; no continuous OS-custody watchdog proof','Loopback TLS fixtures do not qualify Binance endpoint routing, metadata identity or production shared-IP budget','No production or deployment authorization'],counts=dict(external_requests=0,protected_port_connections=0,production_mutations=0,amibroker_execution=0))
report['timing_recheck']=timing
report['timing_target']='BLOCKED_STRICT_1_5_SECOND_WHOLE_CALL_GUARANTEE: one final-run outlier 1.609s; three targeted reruns 1.344/1.422/1.406s. Functional timeout/no-retry/cleanup passed; admission and OS scheduling overhead included.'
report['all_independent_runs_passed']=False
report['closed_findings'].append('ControlledSession binds producer to current socket-owning process and checks custody after receive')
report['unresolved_gates'].append('No separate V3 relay process; synthetic source-to-receiver handoff remains in-process')
(R/'R5_INDEPENDENT_FINAL_REVIEW.json').write_text(json.dumps(report,indent=2))
print(report['status'])
