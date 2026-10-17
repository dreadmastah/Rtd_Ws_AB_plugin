"""R4 reference vs actual R5 scheduler on identical corrected fixtures."""
import asyncio
import hashlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import sys
import time

from Benchmarks.offline_fairness import run_case, SCENARIOS, STRATEGIES
from Benchmarks.run_offline_tests import network_audit

ROOT=Path(__file__).resolve().parents[1]

async def run(tag):
    reference_path=ROOT/'Tests/references/r4_sender.py'
    spec=importlib.util.spec_from_file_location('frozen_r4_sender',reference_path)
    reference=importlib.util.module_from_spec(spec);spec.loader.exec_module(reference)
    directory=Path(os.environ['RC2_OUTPUT'])/('experiments-'+tag)
    directory.mkdir(exist_ok=False)
    results=[]
    for scenario in SCENARIOS:
        for strategy in (*STRATEGIES,'IMPLEMENTED'):
            if strategy=='IMPLEMENTED': result,trace=await run_case(scenario,strategy)
            else: result,trace=await run_case(scenario,strategy,module=reference)
            (directory/(scenario+'-'+strategy+'.json')).write_text(json.dumps(trace,indent=2)+'\n')
            results.append(result)
    (Path(os.environ['RC2_OUTPUT'])/('R5_EXPERIMENT_RESULTS_'+tag+'.json')).write_text(json.dumps(results,indent=2)+'\n')
    # Original R4 evidence tests expect precisely15x4 reference candidates.
    originals=[r for r in results if r['strategy']!='IMPLEMENTED']
    (Path(os.environ['RC2_OUTPUT'])/'FAIRNESS_RAW_RESULTS.json').write_text(json.dumps(originals,indent=2)+'\n')
    accepted=all(r['verdict']=='PASS' for r in results)
    count_equal={s:next(r for r in results if r['scenario']==s and r['strategy']=='BASELINE')['rest_request_count']==next(r for r in results if r['scenario']==s and r['strategy']=='IMPLEMENTED')['rest_request_count'] for s in SCENARIOS}
    assert all(count_equal.values()), count_equal
    for scenario in SCENARIOS:
        reference_row=next(r for r in results if r['scenario']==scenario and r['strategy']=='BASELINE')
        actual=next(r for r in results if r['scenario']==scenario and r['strategy']=='IMPLEMENTED')
        assert reference_row['history_digest']==actual['history_digest'],scenario
    summary=dict(experiments=len(results),passed=sum(r['verdict']=='PASS' for r in results),failed=sum(r['verdict']!='PASS' for r in results),
                 requests_equal_to_baseline=count_equal,reference_sender_sha256=hashlib.sha256(reference_path.read_bytes()).hexdigest(),
                 r5_sender_sha256=hashlib.sha256((ROOT/'Binance/sender.py').read_bytes()).hexdigest())
    (Path(os.environ['RC2_OUTPUT'])/('EXPERIMENT_SUMMARY_'+tag+'.json')).write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary))
    return accepted

if __name__=='__main__':
    sys.addaudithook(network_audit);logging.disable(logging.CRITICAL)
    raise SystemExit(0 if asyncio.run(run(sys.argv[1])) else 1)
