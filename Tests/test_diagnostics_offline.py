import asyncio
import os
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from Binance import sender as mod
from Binance.diagnostics import Diagnostics
from Benchmarks.offline_fairness import (Clock, FakeREST, FakeRelay, fake_event,
                                         run_case, SCENARIOS, STRATEGIES, direct_wait)


def args(**overrides):
    return SimpleNamespace(**dict(dict(batch_size=100, flush_ms=250, native_history=True,
                                      history_days=1, shard_size=100, quotes=True,
                                      rest='memory://fixtures'), **overrides))


class DiagnosticTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Virtual-time experiments contain many zero-time cooperative yields;
        # asyncio's wall-clock debug tracing is unrelated to their assertions.
        asyncio.get_running_loop().set_debug(False)

    def sender(self):
        self.clock = Clock(200)
        self.diag = Diagnostics(256, self.clock)
        s = mod.Sender(args(), None, self.diag)
        s.symbols = ['BTCUSDT']
        return s

    def test_ring_and_state_bounds(self):
        d = Diagnostics(16, Clock(200))
        for i in range(2000):
            d.event(fake_event('S'+str(i), 60000), True, 'accepted')
        self.assertEqual(len(d.records), 16)
        self.assertEqual(len(d.symbols), 500)
        self.assertEqual(d.overwritten, 484)
        for i in range(2000): d.enqueue((str(i),'1m'),(0,60000),(0,60000),'MINUTE_STALE')
        self.assertEqual(len(d.jobs), 1000)
        self.assertEqual(d.counts['job_tracking_capacity'], 1000)

    def test_shard2_exact_membership_and_consecutive_stale(self):
        clock = Clock(200)
        d = Diagnostics(16, clock)
        symbols = [f'S{i:03}USDT' for i in range(500)]
        for i in range(5):
            key = d.shard(i+1, set(symbols[i*100:(i+1)*100]), False)
            for s in symbols[i*100:(i+1)*100]:
                d.event(fake_event(s, 60000 if i==1 else 180000),True,'accepted',key)
        snap=d.snapshot()
        self.assertEqual(snap['consecutive_stale_symbols']['market:2'], symbols[100:200])
        self.assertEqual(snap['consecutive_stale_symbols']['market:1'], [])
        self.assertEqual(snap['shards']['market:2']['kline_events'],100)

    def test_quotes_do_not_refresh_kline_timestamp(self):
        s=self.sender(); s.ingest(fake_event('BTCUSDT',60000))
        self.clock.now=250
        s.ingest(dict(e='bookTicker',s='BTCUSDT',E=250000,b='10',B='1',a='12',A='1'))
        state=self.diag.snapshot()['symbols']['BTCUSDT']
        self.assertEqual(state['raw_kline_utc'],200)
        self.assertEqual(state['quote_utc'],250)
        self.assertEqual(s.buffer.latest['BTCUSDT'][0][1],60000)

    def test_rejection_preserves_final_ohlcv(self):
        s=self.sender(); s.ingest(fake_event('BTCUSDT',60000,True))
        original=dict(s.buffer.latest['BTCUSDT'][1])
        event=fake_event('BTCUSDT',60000,False,'0'); event['E']=90000
        self.assertFalse(s.ingest(event))
        self.assertEqual(s.buffer.latest['BTCUSDT'][1],original)
        rec=self.diag.records[-1]
        self.assertFalse(rec['accepted'])
        self.assertEqual(rec['reason'],'stale_version_or_reopen_final')

    def test_final_and_raw_time_distinct(self):
        s=self.sender(); s.ingest(fake_event('BTCUSDT',60000,True))
        state=self.diag.snapshot()['symbols']['BTCUSDT']
        self.assertEqual(state['raw_kline_utc'],200)
        self.assertEqual(state['accepted_event_ms'],61000)
        self.assertEqual(state['final_close_ms'],119999)

    def test_coalesced_job_keeps_birth_and_original(self):
        s=self.sender()
        s.queue_repair('BTCUSDT','1m',60000,120000,'MINUTE_STALE')
        self.clock.now+=7
        s.queue_repair('BTCUSDT','1m',0,180000,'MINUTE_RECONNECT')
        job=self.diag.jobs[('BTCUSDT','1m')]
        self.assertEqual(job['original_range'],(60000,120000))
        self.assertEqual(job['range'],(0,180000))
        self.assertEqual(self.diag.snapshot()['oldest_queue_age_seconds']['1m'],7)
        self.assertEqual(job['classifications'],['MINUTE_STALE','MINUTE_RECONNECT'])

    async def test_deferral_keeps_job_and_records_retry(self):
        s=self.sender(); s.queue_repair('BTCUSDT','1m',60000,120000)
        s.rest=AsyncMock(return_value=[])
        await s.repair_one(SimpleNamespace(send=AsyncMock()))
        self.assertIn(('BTCUSDT','1m'),s.repairs)
        self.assertIn(('BTCUSDT','1m'),self.diag.jobs)
        self.assertEqual([r for r in self.diag.records if r['kind']=='repair_cooldown'][0]['seconds'],60)

    async def test_repair_completion_actual_bars_and_queue_removal(self):
        s=self.sender(); s.ingest(fake_event('BTCUSDT',0,True))
        s.queue_repair('BTCUSDT','1m',60000,120000)
        s.rest=AsyncMock(return_value=[[60000,'10','12','9','11','0']])
        ws=SimpleNamespace(send=AsyncMock())
        await s.repair_one(ws)
        self.assertFalse(s.repairs); self.assertFalse(self.diag.jobs)
        frame=json.loads(ws.send.call_args_list[0].args[0])
        self.assertEqual(frame['bars'],[[19700101,100,10,12,9,11,0]])
        self.assertEqual([r for r in self.diag.records if r['kind']=='repair_complete'][0]['bars'],1)

    def test_disabled_or_broken_diagnostics_no_acceptance_change(self):
        plain=mod.Sender(args(),None)
        s=self.sender()
        self.diag.event=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('diagnostic only'))
        for e in [fake_event('BTCUSDT',60000),fake_event('BTCUSDT',60000,True),fake_event('BTCUSDT',120000)]:
            self.assertEqual(s.ingest(e),plain.ingest(e))
        self.assertEqual(s.buffer.pending,plain.buffer.pending)
        self.assertEqual(s.repairs,plain.repairs)
        self.assertEqual(self.diag.errors,3)

    def test_no_raw_secrets_in_diagnostic_payload(self):
        s=self.sender(); e=fake_event('BTCUSDT',60000)
        e.update(api_key='SECRET_TEST',token='SECRET_TEST',url='SECRET_TEST')
        s.ingest(e)
        self.assertNotIn('SECRET_TEST',json.dumps(self.diag.snapshot()))
        e['E']='SECRET_TEST'
        with self.assertRaises(ValueError): s.ingest(e)
        self.assertNotIn('SECRET_TEST',json.dumps(self.diag.snapshot()))

    def test_generations_ack_and_reconnect_duration(self):
        s=self.sender(); key=self.diag.shard(2,{'BTCUSDT'},False)
        self.diag.connection(key,'connected'); self.diag.connection(key,'subscribed')
        self.clock.now+=.5; self.diag.connection(key,'ack',success=True)
        self.diag.connection(key,'disconnected',reason='TimeoutError')
        self.clock.now+=4; self.diag.connection(key,'connected')
        self.assertEqual(self.diag.shards[key]['generation'],2)
        self.assertEqual(self.diag.records[-1]['reconnect_seconds'],4)
        self.assertEqual([r for r in self.diag.records if r['kind']=='shard_ack'][0]['ack_delay_seconds'],.5)

    async def test_output_delay_measured_after_send_finishes(self):
        s=self.sender()
        async def send(message): self.clock.now+=.4
        with patch.object(mod,'time',self.clock):
            await s.send(SimpleNamespace(send=send),'[]')
        self.assertAlmostEqual(self.diag.records[-1]['elapsed_seconds'],.4)

    async def test_manual_and_preload_labels(self):
        s=self.sender()
        s.history_range=AsyncMock(return_value=3)
        await s.history(None,'BTCUSDT',0,count=1)
        await s.native_history(None,'BTCUSDT')
        classes={r['classification'] for r in self.diag.records if r['kind']=='history_complete'}
        self.assertEqual(classes,{'MANUAL_HISTORY','NATIVE_PRELOAD'})

    async def test_baseline_matches_prepatch_real_sender(self):
        path=Path(__file__).parents[1]/'Tests/references/r6a_sender.py'
        spec=importlib.util.spec_from_file_location('prepatch_sender',path)
        original=importlib.util.module_from_spec(spec); spec.loader.exec_module(original)
        for scenario in ('C_TWO_DAILY_BATCHES','D_MIDNIGHT_RECHECK_500','E_LOST_FINAL','F_RECONNECT','H_429','I_418','K_MISSING_MINUTES','O_NO_OBSERVED_ADVANCE'):
            current,current_trace=await run_case(scenario)
            before,before_trace=await run_case(scenario,module=original)
            for key in ('history_digest','minute_wait','daily_wait','rest_request_count'):
                self.assertEqual(current[key],before[key],(scenario,key))
            self.assertEqual(current_trace['rest'],before_trace['rest'])

    async def test_actual_shard_reconnect_and_ack_hooks(self):
        s=self.sender(); s.args.ws='memory://market'; s.args.public_ws='memory://public'
        s.symbols=[f'S{i:03}USDT' for i in range(200)]
        symbols=set(s.symbols[100:]); subscribed=[]; generations=[]
        class Peer:
            def __init__(self): self.messages=0
            async def send(self,raw): subscribed.append(json.loads(raw))
            async def recv(self):
                self.messages+=1
                if self.messages==1: return json.dumps({'id':'fixture','result':None})
                if self.messages==2:return json.dumps(fake_event('S100USDT',60000,True))
                raise OSError('fixture transport interruption')
        class Connection:
            async def __aenter__(self):
                peer=Peer(); generations.append(peer); return peer
            async def __aexit__(self,*args): pass
        proxy=SimpleNamespace(**{n:getattr(asyncio,n) for n in dir(asyncio) if not n.startswith('__')})
        proxy.sleep=self.clock.sleep; proxy.wait_for=direct_wait
        with patch.object(mod,'time',self.clock),patch.object(mod,'asyncio',proxy), \
             patch.object(mod,'connect',return_value=Connection()),patch.object(mod.random,'random',return_value=0):
            task=asyncio.create_task(s.shard(symbols))
            try:
                self.assertTrue(await self.clock.drive([task],lambda:len(generations)>=2,limit=10))
            finally:
                task.cancel(); await asyncio.gather(task,return_exceptions=True)
        self.assertGreaterEqual(len(subscribed),2)
        self.assertEqual(subscribed[0]['params'],[symbol.lower()+'@'+stream for symbol in sorted(symbols) for stream in ['kline_1m','ticker']])
        state=self.diag.shards['market:2']
        self.assertEqual(state['symbols'],sorted(symbols))
        self.assertGreaterEqual(state['generation'],2)
        self.assertIn('ack_utc',state)
        self.assertTrue(any(r['kind']=='shard_disconnected' and r['reason']=='OSError' for r in self.diag.records))

    async def test_fake_clock_repeatability(self):
        first,_=await run_case('G_SLOW_REST','CANDIDATE_B')
        second,_=await run_case('G_SLOW_REST','CANDIDATE_B')
        self.assertEqual(first,second)

    async def test_real_output_delays_do_not_become_rest_latency(self):
        result,trace=await run_case('N_OUTPUT_DELAY')
        self.assertTrue(result['completed'])
        first=trace['rest'][0]
        delivery=trace['history_sends'][0]
        self.assertAlmostEqual(first['response']-first['start'],.075,places=5)
        self.assertGreaterEqual(delivery[0]-first['response'],.4-1e-5)

    async def test_repaired_old_bar_does_not_replace_new_live_candle(self):
        result,trace=await run_case('O_NO_OBSERVED_ADVANCE')
        self.assertTrue(result['closed_minute_completeness'])
        self.assertEqual(result['required_finalized_bars']['1m'],2)
        delivered=trace['history_sends']
        self.assertEqual(sum(row[3] for row in delivered),2)

    async def test_rest_exhaustion_is_six_attempts_and_no_job_loss(self):
        s=self.sender(); clock=self.clock
        attempts=[]
        class Response:
            status=429
            headers={'Retry-After':'2'}
            async def __aenter__(self): attempts.append(clock.time()); return self
            async def __aexit__(self,*args): pass
        s.session=SimpleNamespace(get=lambda *a,**k:Response())
        proxy=SimpleNamespace(**{n:getattr(asyncio,n) for n in dir(asyncio) if not n.startswith('__')})
        proxy.sleep=clock.sleep; proxy.wait_for=direct_wait
        s.queue_repair('BTCUSDT','1m',60000,120000)
        with patch.object(mod,'time',clock),patch.object(mod,'asyncio',proxy):
            task=asyncio.create_task(s.repair_one(SimpleNamespace(send=AsyncMock())))
            self.assertTrue(await clock.drive([task],task.done,limit=30))
        self.assertEqual(len(attempts),6)
        self.assertTrue(all(b-a>=2 for a,b in zip(attempts,attempts[1:])))
        self.assertIn(('BTCUSDT','1m'),s.repairs)
        self.assertGreater(s.retry_after[('BTCUSDT','1m')],clock.monotonic())

    async def test_retention_and_original_range_preserved(self):
        s=self.sender(); s.queue_repair('BTCUSDT','1m',0,2000*60000)
        delivered=[]
        async def history(ws,symbol,interval,start,end,strict):
            delivered.append((start,end)); return 1500
        s.history_range=history
        await s.repair_one(None)
        self.assertEqual(delivered,[(500*60000,2000*60000)])
        enqueue=next(r for r in self.diag.records if r['kind']=='repair_enqueue')
        self.assertEqual(enqueue['original'],(0,2000*60000))

    async def test_live_pump_progresses_during_418_cooldown(self):
        result,trace=await run_case('I_418')
        first=trace['rest'][0]
        self.assertTrue(any(first['response']<t<first['response']+60 for t in trace['live_sends']))
        self.assertTrue(result['checks']['cooldown'])


class EvidenceScenarioTests(unittest.TestCase):
    """Validate actual measured outcomes, not presence of diagnostic messages."""
    @classmethod
    def setUpClass(cls):
        cls.results=json.loads((Path(os.environ['RC2_OUTPUT'])/'FAIRNESS_RAW_RESULTS.json').read_text())

    def test_all_15_by_4_experiments_present(self):
        self.assertEqual({(r['scenario'],r['strategy']) for r in self.results},
                         {(s,v) for s in SCENARIOS for v in STRATEGIES})

    def test_all_completeness_budget_and_ordering_checks(self):
        for r in self.results:
            with self.subTest(scenario=r['scenario'],strategy=r['strategy']):
                self.assertTrue(all(r['checks'].values()),r['checks'])

    def test_fairness_candidates_reduce_blocked_minute_wait(self):
        rows={r['strategy']:r for r in self.results if r['scenario']=='C_TWO_DAILY_BATCHES'}
        for strategy in ('CANDIDATE_A','CANDIDATE_B'):
            self.assertLess(rows[strategy]['minute_wait']['p95'],rows['BASELINE']['minute_wait']['p95'])
            self.assertTrue(rows[strategy]['daily_eventual_completion'])
        # Candidate C's age protection can revert to the old daily queue order;
        # no assertion or report claims an improvement it did not achieve.
        self.assertGreaterEqual(rows['CANDIDATE_C']['minute_wait']['p95'],rows['CANDIDATE_A']['minute_wait']['p95'])

    def test_no_extra_requests_in_same_fixtures(self):
        for scenario in SCENARIOS:
            rows=[r for r in self.results if r['scenario']==scenario]
            # Coalescing may change request counts; candidates cannot gain their
            # latency result by increasing request pressure above this baseline.
            baseline=next(r for r in rows if r['strategy']=='BASELINE')
            for r in rows:
                self.assertLessEqual(r['rest_request_count'],baseline['rest_request_count'],scenario)

    def test_daily_progress_under_continuous_minutes(self):
        for r in self.results:
            if r['scenario']=='M_CONTINUOUS_MINUTES':
                self.assertEqual(r['jobs_completed']['1d'],500)
                self.assertTrue(r['completed'])

    def test_two_batches_not_only_single_cohort(self):
        for r in self.results:
            if r['scenario'] in ('C_TWO_DAILY_BATCHES','D_MIDNIGHT_RECHECK_500'):
                self.assertEqual(r['jobs_completed']['1d'],1000)

    def test_zero_trade_bars_preserved(self):
        for r in self.results:
            if r['scenario']=='J_ZERO_TRADE':
                self.assertTrue(r['exact_fixture_ohlcv'])
                self.assertEqual(r['required_finalized_bars']['1m'],10)

    def test_throttle_minimum_and_serialization(self):
        for r in self.results:
            if r['scenario'] in ('H_429','I_418'):
                self.assertEqual(r['retry_count'],1)
                self.assertEqual(r['rest_max_concurrency'],1)
                self.assertGreaterEqual(r['cooldowns'][0]['actual'],r['cooldowns'][0]['required']-1e-6)
