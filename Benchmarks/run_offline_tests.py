"""Complete RC2 suite: fresh deterministic experiments then regression tests.

Use the isolated environment and Tests/guard on PYTHONPATH. All results belong to
RC2_OUTPUT, never to the source tree or installed runtime.
"""
import argparse,asyncio,hashlib,importlib.util,json,logging,os,sys,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'Tests'))
def network_audit(event,args):
    # Compatibility import for the archived experiment entry point. The active
    # suite requires the stronger inherited sitecustomize guard.
    if event in ('socket.connect','socket.bind'):
        host,port=args[1][:2]
        if host not in ('127.0.0.1','::1','localhost') or port in (10101,18101,18102):raise PermissionError('Protected endpoint')
def source_manifest():
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(ROOT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and '.pyc'!=p.suffix}
def load_reference(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
async def experiments(out):
    from Benchmarks.offline_fairness import run_case,SCENARIOS,STRATEGIES
    reference=load_reference(ROOT/'Tests/references/r4_sender.py','rc2_r4_reference')
    rows=[];trace_bindings=[]
    for scenario in SCENARIOS:
        for strategy in (*STRATEGIES,'IMPLEMENTED'):
            row,trace=await run_case(scenario,strategy,**({} if strategy=='IMPLEMENTED' else {'module':reference}))
            rows.append(row)
            trace_bindings.append({'scenario':scenario,'strategy':strategy,'sha256':hashlib.sha256(json.dumps(trace,sort_keys=True).encode()).hexdigest(),'rest_count':len(trace['rest'])})
        print('EXPERIMENT '+scenario,flush=True)
    (out/'FAIRNESS_RAW_RESULTS.json').write_text(json.dumps([r for r in rows if r['strategy']!='IMPLEMENTED'],indent=2))
    (out/'FAIRNESS_75_RESULTS.json').write_text(json.dumps(rows,indent=2))
    (out/'FAIRNESS_TRACE_HASHES.json').write_text(json.dumps(trace_bindings,indent=2))
    for s in SCENARIOS:
        base=next(r for r in rows if r['scenario']==s and r['strategy']=='BASELINE')
        actual=next(r for r in rows if r['scenario']==s and r['strategy']=='IMPLEMENTED')
        assert base['rest_request_count']==actual['rest_request_count'],s
        assert base['history_digest']==actual['history_digest'],s
    assert all(r['verdict']=='PASS' for r in rows),[(r['scenario'],r['strategy'],r['checks']) for r in rows if r['verdict']!='PASS']
    return {'experiments':len(rows),'pass':len(rows),'fail':0}
class RecordedResult(unittest.TextTestResult):
    def __init__(self,*a,**k):super().__init__(*a,**k);self.outcomes=[]
    def addSuccess(self,t):super().addSuccess(t);self.outcomes.append({'test':t.id(),'status':'PASS'})
    def addFailure(self,t,e):super().addFailure(t,e);self.outcomes.append({'test':t.id(),'status':'FAIL','detail':self._exc_info_to_string(e,t)})
    def addError(self,t,e):super().addError(t,e);self.outcomes.append({'test':t.id(),'status':'ERROR','detail':self._exc_info_to_string(e,t)})
    def addSkip(self,t,r):super().addSkip(t,r);self.outcomes.append({'test':t.id(),'status':'SKIP','reason':r})
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--modules',nargs='*');args=parser.parse_args()
    import sitecustomize
    assert hasattr(sitecustomize,'owned_ports'),'Inherited network/write guard required'
    out=Path(os.environ['RC2_OUTPUT']);out.mkdir(parents=True,exist_ok=False)
    for name in ['test-tmp','fixtures']:(out/name).mkdir()
    tempfile.tempdir=str(out/'test-tmp')
    for name in ['TMP','TEMP','TMPDIR']:os.environ[name]=tempfile.tempdir
    before=source_manifest();start=time.monotonic();logging.disable(logging.CRITICAL)
    (out/'SOURCE_BEFORE.json').write_text(json.dumps(before,indent=2))
    exp={'status':'NOT_RUN_FOCUSED_DEVELOPMENT_ONLY'}
    if not args.modules:exp=asyncio.run(experiments(out))
    logging.disable(logging.NOTSET)
    suite=unittest.TestSuite()
    if args.modules:
        for name in args.modules:suite.addTests(unittest.defaultTestLoader.loadTestsFromName(name))
    else:suite=unittest.defaultTestLoader.discover(str(ROOT/'Tests'))
    result=unittest.TextTestRunner(verbosity=2,resultclass=RecordedResult).run(suite)
    after=source_manifest();unchanged=before==after
    value={'python':sys.version,'command':sys.argv,'tests':result.testsRun,'passed':result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'elapsed_seconds':time.monotonic()-start,'outcomes':result.outcomes,'experiments':exp,'source_unchanged':unchanged,'source_manifest_sha256':hashlib.sha256((''.join(h+'  '+p+'\n' for p,h in before.items())).encode()).hexdigest(),'network_policy':'Inherited guard: only test-owned ephemeral loopback endpoints, external DNS denied; only isolated Python children; file writes confined to RC2.','owned_ports':sorted(sitecustomize.owned_ports)}
    (out/'RESULTS.json').write_text(json.dumps(value,indent=2))
    print(json.dumps({k:v for k,v in value.items() if k not in ('outcomes','owned_ports')}),flush=True)
    return 0 if result.wasSuccessful() and unchanged else 1
if __name__=='__main__':raise SystemExit(main())
