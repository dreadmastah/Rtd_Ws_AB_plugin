import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from Binance import sender as mod
from Binance.telemetry_sender import TelemetrySender
from Binance.rest_telemetry import RestTelemetry, classify, summarize, MAX_RECORDS
from test_rest_pacing_r6a import ExactClock, Session


class TelemetryTests(unittest.TestCase):
    def recorder(self, **kwargs):
        return RestTelemetry(monotonic_ns=lambda: 1000000000,
                             utc_ns=lambda: 1791849600000000000, **kwargs)

    def request(self, recorder, path='/fapi/v1/klines', params=None, headers=None):
        token = recorder.begin(path, params or {'limit':499}, 'PRELOAD', 0)
        recorder.response(token, 200, headers or {}, None)
        recorder.finish(token)
        return token

    def test_endpoint_classification_and_exact_weight_edges(self):
        self.assertEqual(classify('/fapi/v1/exchangeInfo', {}), ('EXCHANGE_INFO',1))
        self.assertEqual(classify('/fapi/v1/openInterest', {}), ('OPEN_INTEREST',1))
        for limit, weight in [(1,1),(99,1),(100,2),(499,2),(500,5),(1000,5),(1001,10),(1500,10)]:
            self.assertEqual(classify('/fapi/v1/klines', {'limit':limit}), ('KLINES',weight))

    def test_unknown_limits_and_endpoints_are_not_zero(self):
        for limit in [None,0,-1,1501,True,499.0,'secret']:
            self.assertIsNone(classify('/fapi/v1/klines', {'limit':limit})[1])
        self.assertEqual(classify('/secret?apiKey=private',{}), ('UNKNOWN',None))
        r=self.recorder();self.request(r,path='/unknown')
        result=summarize([r.snapshot()])
        self.assertEqual(result['confidence'],'INCOMPLETE_LOCAL_CAPTURE')
        self.assertEqual(result['generations'][0]['unknown_weight_requests'],1)

    def test_missing_headers_are_null_and_counted(self):
        r=self.recorder();self.request(r)
        s=r.snapshot();self.assertIsNone(s['records'][0]['used_weight']['X-MBX-USED-WEIGHT-1M'])
        report=summarize([s]);self.assertEqual(report['generations'][0]['missing_used_weight_1m_count'],1)
        self.assertIsNone(report['external_shared_ip_usage'])
        self.assertIsNone(report['safe_remaining_headroom'])
        self.assertFalse(report['concurrent_test_readiness'])

    def test_response_headers_are_samples_not_summed(self):
        r=self.recorder()
        self.request(r,headers={'X-MBX-USED-WEIGHT-1M':'217','X-MBX-USED-WEIGHT-1H':'901'})
        self.request(r,headers={'X-MBX-USED-WEIGHT-1M':'240'})
        result=summarize([r.snapshot()])
        self.assertEqual(result['known_documented_weight'],4)
        self.assertIsNone(result['measured_charged_request_weight'])
        self.assertEqual(r.records[0]['used_weight']['X-MBX-USED-WEIGHT-1H'],901)

    def test_lowercase_headers_and_invalid_values(self):
        r=self.recorder();self.request(r,headers={'x-mbx-used-weight-1m':'0','X-MBX-USED-WEIGHT-1H':'secret'})
        self.assertEqual(r.records[0]['used_weight']['X-MBX-USED-WEIGHT-1M'],0)
        self.assertEqual(r.records[0]['header_state']['X-MBX-USED-WEIGHT-1H'],'INVALID')

    def test_multiple_sender_and_supervisor_generations(self):
        sup='10000000-0000-0000-0000-000000000001'
        a=self.recorder(sender_generation='20000000-0000-0000-0000-000000000001',supervisor_generation=sup,pid=99)
        b=self.recorder(sender_generation='20000000-0000-0000-0000-000000000002',supervisor_generation=sup,pid=99)
        self.request(a);self.request(b);self.request(b)
        result=summarize([a.snapshot(),b.snapshot()])
        self.assertEqual(result['known_documented_weight'],6)
        self.assertEqual([g['requests_recorded'] for g in result['generations']],[1,2])
        self.assertEqual(a.snapshot()['supervisor_generation_confidence'],'CALLER_DECLARED')
        self.assertIsNone(result['maximum_concurrency_across_processes'])

    def test_unknown_supervisor_is_not_inferred_from_parent_pid(self):
        r=self.recorder(parent_pid=123)
        self.assertIsNone(r.snapshot()['supervisor_generation'])
        self.assertEqual(r.snapshot()['supervisor_generation_confidence'],'UNAVAILABLE')

    def test_duplicate_generation_is_rejected(self):
        r=self.recorder()
        with self.assertRaises(ValueError):summarize([r.snapshot(),r.snapshot()])

    def test_generation_and_aggregation_bounds(self):
        for size in (0,-1,MAX_RECORDS+1,True):
            with self.assertRaises(ValueError):self.recorder(capacity=size)
        with self.assertRaises(ValueError):summarize([{}]*33)
        with self.assertRaises(ValueError):self.recorder(sender_generation='secret')

    def test_concurrent_request_detection(self):
        r=self.recorder()
        a=r.begin('/fapi/v1/exchangeInfo',{},'STARTUP',0)
        b=r.begin('/fapi/v1/klines',{'limit':499},'PRELOAD',0)
        r.finish(b);r.finish(a);r.finish(a)
        self.assertEqual(r.maximum_concurrency,2);self.assertEqual(r._active,0)

    def test_capacity_exhaustion_is_bounded_and_incomplete(self):
        r=self.recorder(capacity=2)
        for _ in range(1000):self.request(r)
        self.assertEqual(len(r.records),2);self.assertEqual(r.dropped,998)
        self.assertEqual(summarize([r.snapshot()])['confidence'],'INCOMPLETE_LOCAL_CAPTURE')

    def test_clock_exception_is_contained_and_disables_observer(self):
        def broken():raise OSError('secret clock error')
        r=RestTelemetry(monotonic_ns=broken)
        self.assertIsNone(r.begin('/fapi/v1/klines',{},'HISTORY',0))
        self.assertEqual(r.failures,1)
        self.assertIsNone(r.begin('/fapi/v1/klines',{},'HISTORY',0))
        self.assertEqual(r.dropped,1)

    def test_backwards_clocks_invalidate_interval_alignment(self):
        ticks=iter([100,90,80]);r=RestTelemetry(monotonic_ns=lambda:next(ticks),utc_ns=lambda:1000)
        self.request(r)
        result=summarize([r.snapshot()])
        self.assertIsNone(result['utc_minute_buckets'])
        self.assertEqual(result['confidence'],'INCOMPLETE_LOCAL_CAPTURE')

    def test_invalid_clock_values(self):
        r=RestTelemetry(monotonic_ns=lambda:float('nan'),utc_ns=lambda:-1)
        self.request(r)
        self.assertIsNone(r.records[0]['initiation_mono_ns'])
        self.assertGreater(r.clock_anomalies,0)

    def test_forward_utc_jump_does_not_become_monotonic_gap(self):
        ticks=iter([1,2,3,4,5,6]);walls=iter([100,100,100,10**18,10**18,10**18])
        r=RestTelemetry(monotonic_ns=lambda:next(ticks),utc_ns=lambda:next(walls))
        self.request(r);self.request(r)
        self.assertEqual(r.records[1]['initiation_gap_ns'],3)
        self.assertEqual(summarize([r.snapshot()])['bucket_alignment'],'LOCAL_UTC_NOT_VERIFIED_EXCHANGE_CLOCK')

    def test_no_secret_leakage(self):
        r=self.recorder(supervisor_generation='SECRET')
        self.request(r,path='/private?apiKey=SECRET',params={'limit':'SECRET','signature':'SECRET'},
                     headers={'Authorization':'SECRET','X-MBX-USED-WEIGHT-1M':'SECRET','Retry-After':'SECRET'})
        self.assertNotIn('SECRET',json.dumps(r.snapshot()))

    def test_open_requests_are_incomplete(self):
        r=self.recorder();r.begin('/fapi/v1/exchangeInfo',{},'STARTUP',0)
        self.assertEqual(summarize([r.snapshot()])['confidence'],'INCOMPLETE_LOCAL_CAPTURE')

    def test_no_producer_io_or_wait(self):
        r=self.recorder()
        with patch('builtins.open',side_effect=AssertionError('IO')),patch('time.sleep',side_effect=AssertionError('blocking')):
            self.request(r)
        self.assertEqual(r.failures,0)


class SenderTelemetryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):asyncio.get_running_loop().set_debug(False)

    def setup_sender(self, statuses=(), enabled=True, **options):
        clock=ExactClock();session=Session(clock,statuses)
        recorder=RestTelemetry(monotonic_ns=clock.perf_counter_ns,utc_ns=lambda:int(clock.time()*1e9),**options) if enabled else None
        sender=TelemetrySender(SimpleNamespace(rest='unused',native_history=True,history_days=1,batch_size=100,flush_ms=50),session,rest_telemetry=recorder)
        sender.symbols=['BTCUSDT','ETHUSDT']
        proxy=SimpleNamespace(Lock=asyncio.Lock,Queue=asyncio.Queue,sleep=clock.sleep,wait_for=asyncio.wait_for)
        return clock,session,sender,recorder,patch.object(mod,'time',clock),patch.object(mod,'asyncio',proxy)

    async def test_disabled_default_compatibility(self):
        s=TelemetrySender(SimpleNamespace(rest='unused'),None)
        self.assertIsNone(s.rest_telemetry);self.assertIsNone(s.rest_telemetry_snapshot())
        c,http,s,r,p,q=self.setup_sender(enabled=False)
        with p,q,patch.object(s,'_begin',side_effect=AssertionError('disabled hook called')):
            await s.rest('/fapi/v1/exchangeInfo')
        self.assertEqual(len(http.entries),1)

    async def test_enabled_and_disabled_pacing_and_results_identical(self):
        runs=[]
        for enabled in (False,True):
            c,http,s,r,p,q=self.setup_sender(statuses=[429,500,200,200],enabled=enabled)
            with p,q:
                a=await s.rest('/fapi/v1/klines',limit=499)
                b=await s.rest('/fapi/v1/exchangeInfo')
            runs.append((http.entries,c.sleeps,a,b,s._rest_next_ns))
        self.assertEqual(runs[0],runs[1])

    async def test_retry_bursts_and_cooldown_accounting(self):
        c,http,s,r,p,q=self.setup_sender(statuses=[429,418,500,200])
        with p,q:await s.rest('/fapi/v1/klines',limit=499)
        self.assertEqual([x['status'] for x in r.records],[429,418,500,200])
        self.assertEqual([x['attempt'] for x in r.records],[0,1,2,3])
        # C observer reports exchange cooldowns; 5xx backoff isn't a header observation.
        self.assertEqual([x['cooldown_seconds'] for x in r.records],[1,60,None,None])
        self.assertEqual(summarize([s.rest_telemetry_snapshot()])['known_documented_weight'],8)
        self.assertTrue(all(x['retry'] for x in r.records[1:]))

    async def test_exhausted_retries_all_counted(self):
        c,http,s,r,p,q=self.setup_sender(statuses=[500]*6)
        with p,q:
            with self.assertRaises(RuntimeError):await s.rest('/fapi/v1/klines',limit=499)
        self.assertEqual(len(r.records),6)
        self.assertEqual(summarize([s.rest_telemetry_snapshot()])['known_documented_weight'],12)

    async def test_startup_and_history_classes(self):
        c,http,s,r,p,q=self.setup_sender()
        with p,q:
            await s.rest('/fapi/v1/exchangeInfo')
            await s.rest('/fapi/v1/klines',limit=499)
        self.assertEqual([x['request_class'] for x in r.records],['STARTUP','HISTORY'])

    async def test_preload_minute_daily_and_reconnect_bursts(self):
        c,http,s,r,p,q=self.setup_sender();frames=[]
        class WS:
            async def send(self,message):frames.append(message)
        with p,q:
            await s.native_history(WS(),'BTCUSDT')
            s.queue_repair('BTCUSDT','1m',60000,120000,'MINUTE_RECONNECT')
            s.queue_repair('ETHUSDT','1d',86400000,172800000,'DAILY_ROLLOVER')
            while s.repairs:await s.repair_step(WS())
        self.assertEqual([x['request_class'] for x in r.records],['PRELOAD']*5+['MINUTE_REPAIR','DAILY_REPAIR'])
        # C adapter does not infer a reconnect cause from generic repair execution.
        self.assertFalse(r.records[-2]['reconnect'])
        self.assertEqual(summarize([s.rest_telemetry_snapshot()])['known_documented_weight'],14)
        self.assertTrue(frames)

    async def test_actual_sender_concurrency_stays_one(self):
        c,http,s,r,p,q=self.setup_sender()
        with p,q:await asyncio.gather(*(s.rest('/fapi/v1/exchangeInfo') for _ in range(15)))
        self.assertEqual(r.maximum_concurrency,1);self.assertEqual(http.max_concurrent,1)
        self.assertTrue(all(x['initiation_gap_ns']>=250000000 for x in r.records[1:]))

    async def test_buffer_exhaustion_does_not_drop_market_delivery(self):
        c,http,s,r,p,q=self.setup_sender(capacity=1)
        with p,q:
            results=[await s.rest('/fapi/v1/exchangeInfo') for _ in range(10)]
        self.assertEqual(results,[[]]*10);self.assertEqual(len(http.entries),10)
        self.assertEqual(r.dropped,9)

    async def test_observer_errors_including_memory_failure_are_contained(self):
        for exception in (OSError('SECRET'),MemoryError('SECRET')):
            c,http,s,r,p,q=self.setup_sender()
            with p,q,patch.object(r,'begin',side_effect=exception):
                self.assertEqual(await s.rest('/fapi/v1/exchangeInfo'),[])
            self.assertEqual(s._rest_telemetry_failures,1)
            result=summarize([s.rest_telemetry_snapshot()])
            self.assertEqual(result['confidence'],'INCOMPLETE_LOCAL_CAPTURE')
            self.assertNotIn('SECRET',json.dumps(result))

    async def test_transport_exception_keeps_unknown_status(self):
        c,http,s,r,p,q=self.setup_sender();http.enter_exception=TimeoutError('SECRET')
        with p,q:
            with self.assertRaises(TimeoutError):await s.rest('/fapi/v1/exchangeInfo')
        self.assertIsNone(r.records[0]['status']);self.assertTrue(r.records[0]['finished'])
        self.assertEqual(summarize([s.rest_telemetry_snapshot()])['generations'][0]['missing_response_count'],1)

    async def test_cancelled_request_preserves_pacing_and_finishes_observation(self):
        c,http,s,r,p,q=self.setup_sender();http.enter_exception=asyncio.CancelledError()
        with p,q:
            with self.assertRaises(asyncio.CancelledError):await s.rest('/fapi/v1/exchangeInfo')
            await s.rest('/fapi/v1/exchangeInfo')
        self.assertTrue(all(x['finished'] for x in r.records));self.assertEqual(r._active,0)
        self.assertGreaterEqual(r.records[1]['initiation_gap_ns'],250000000)

    async def test_unbounded_observer_rejected_before_use(self):
        with self.assertRaises(TypeError):TelemetrySender(SimpleNamespace(),None,rest_telemetry=object())
