import asyncio,importlib.util,json,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from Binance import sender as mod

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('frozen_r5_pacing',ROOT/'Tests/references/r5_sender.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)

class ExactClock:
    def __init__(self,start=1_000_000_000_000,early=15_000_000):self.ns=start;self.early=early;self.sleeps=[]
    def perf_counter_ns(self):return self.ns
    def monotonic_ns(self):return self.ns
    def monotonic(self):return self.ns/1e9
    def time(self):return 1791800000+self.ns/1e9
    async def sleep(self,delay):
        requested=max(0,round(delay*1e9));advance=max(1,requested-self.early) if requested>self.early else requested
        self.sleeps.append(dict(requested_ns=requested,advanced_ns=advance));self.ns+=advance;await asyncio.sleep(0)

class Response:
    def __init__(self,session,status,params):self.s=session;self.status=status;self.params=params;self.headers={'Retry-After':str(session.retry_after)}
    async def __aenter__(self):
        self.s.entries.append(dict(index=len(self.s.entries)+1,ns=self.s.clock.perf_counter_ns(),params=self.params))
        self.s.concurrent+=1;self.s.max_concurrent=max(self.s.max_concurrent,self.s.concurrent)
        if self.s.enter_exception:
            exc=self.s.enter_exception;self.s.enter_exception=None;self.s.concurrent-=1;raise exc
        if self.s.latency:await self.s.clock.sleep(self.s.latency)
        return self
    async def __aexit__(self,*args):self.s.concurrent-=1
    def raise_for_status(self):
        if self.status>=400:raise RuntimeError('fixture HTTP error')
    async def json(self):
        p=self.params
        if 'startTime' not in p:return []
        step=86400000 if p.get('interval')=='1d' else 60000
        start=p['startTime'];end=p['endTime']+1
        return [[t,'10','12','9','11','0' if self.s.zero else '17',t+step-1,'0',0] for t in range(start,min(end,start+step*p.get('limit',499)),step)]

class Session:
    def __init__(self,clock,statuses=(),retry_after=1,latency=0):self.clock=clock;self.statuses=list(statuses);self.retry_after=retry_after;self.latency=latency;self.entries=[];self.concurrent=0;self.max_concurrent=0;self.enter_exception=None;self.zero=False
    def get(self,url,params):
        return Response(self,self.statuses.pop(0) if self.statuses else 200,params)

class PacingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):asyncio.get_running_loop().set_debug(False)
    def setup_sender(self,module=mod,clock=None,statuses=(),retry_after=1,latency=0):
        c=clock or ExactClock();session=Session(c,statuses,retry_after,latency)
        s=module.Sender(SimpleNamespace(rest='http://127.0.0.1:1',native_history=True,history_days=1,batch_size=100,flush_ms=50),session)
        s.symbols=[f'S{i:03}USDT' for i in range(500)]
        proxy=SimpleNamespace(Lock=asyncio.Lock,Queue=asyncio.Queue,sleep=c.sleep,wait_for=asyncio.wait_for)
        return c,session,s,patch.object(module,'time',c),patch.object(module,'asyncio',proxy)
    def assert_paced(self,session):
        self.assertGreater(len(session.entries),1)
        self.assertTrue(all(b['ns']-a['ns']>=250_000_000 for a,b in zip(session.entries,session.entries[1:])),session.entries[:5])
        self.assertLessEqual(session.max_concurrent,1)
    async def test_original_short_spacing_red_and_corrected_green(self):
        results=[]
        for module in (old,mod):
            c,session,s,p,q=self.setup_sender(module)
            with p,q:
                for _ in range(3):await s.rest('/fixture')
            gaps=[b['ns']-a['ns'] for a,b in zip(session.entries,session.entries[1:])];results.append(gaps)
        self.assertEqual(results[0],[235_000_000,235_000_000])
        self.assertTrue(all(g>=250_000_000 for g in results[1]),results)
    async def test_serial_minute_repairs(self):await self.exercise_repairs(['1m']*8)
    async def test_serial_daily_repairs(self):await self.exercise_repairs(['1d']*8)
    async def test_alternating_repairs(self):await self.exercise_repairs(['1m','1d']*8)
    async def exercise_repairs(self,intervals):
        c,session,s,p,q=self.setup_sender();frames=[]
        class WS:
            async def send(self,message):frames.append(json.loads(message))
        with p,q:
            for index,interval in enumerate(intervals):
                step=60000 if interval=='1m' else 86400000;s.queue_repair(s.symbols[index],interval,step,step*2,'MINUTE_GAP' if interval=='1m' else 'DAILY_ROLLOVER')
            while s.repairs:await s.repair_step(WS())
        self.assertEqual(len(frames),len(intervals));self.assert_paced(session)
    async def test_concurrent_tasks_share_one_gate(self):
        c,session,s,p,q=self.setup_sender(latency=.01)
        with p,q:await asyncio.gather(*(s.rest('/fixture',symbol=s.symbols[i],interval='1m' if i%2 else '1d') for i in range(40)))
        self.assertEqual(len(session.entries),40);self.assert_paced(session)
    async def test_429_cooldown(self):await self.retry_case([429,200],1,1_000_000_000)
    async def test_418_cooldown(self):await self.retry_case([418,200],2,60_000_000_000)
    async def test_5xx_retry(self):await self.retry_case([500,502,200],1,1_000_000_000)
    async def retry_case(self,statuses,retry_after,minimum):
        c,session,s,p,q=self.setup_sender(statuses=statuses,retry_after=retry_after)
        with p,q:await s.rest('/fixture')
        self.assertEqual(len(session.entries),len(statuses));self.assert_paced(session)
        # Existing cooldown sleep may also wake early; correction must preserve actual cooldown floor.
        self.assertGreaterEqual(session.entries[1]['ns']-session.entries[0]['ns'],minimum)
    async def test_retry_bounds(self):
        c,session,s,p,q=self.setup_sender(statuses=[500]*8)
        with p,q:
            with self.assertRaisesRegex(RuntimeError,'REST retries exhausted'):await s.rest('/fixture')
        self.assertEqual(len(session.entries),6);self.assert_paced(session)
    async def test_connection_timeout_followup_uses_gate(self):
        c,session,s,p,q=self.setup_sender();session.enter_exception=TimeoutError('fixture')
        with p,q:
            with self.assertRaises(TimeoutError):await s.rest('/fixture')
            await s.rest('/fixture')
        self.assert_paced(session)
    async def test_cancelled_request_followup_uses_gate(self):
        c,session,s,p,q=self.setup_sender();session.enter_exception=asyncio.CancelledError()
        with p,q:
            with self.assertRaises(asyncio.CancelledError):await s.rest('/fixture')
            await s.rest('/fixture')
        self.assert_paced(session)
    async def test_monotonic_large_integer_boundary(self):
        c,session,s,p,q=self.setup_sender(clock=ExactClock(start=2**62,early=1))
        with p,q:
            await s.rest('/fixture');await s.rest('/fixture')
        self.assert_paced(session)
    async def test_delayed_event_loop_does_not_catch_up_burst(self):
        c,session,s,p,q=self.setup_sender()
        with p,q:
            await s.rest('/fixture');c.ns+=10_000_000_000
            await s.rest('/fixture');await s.rest('/fixture')
        self.assert_paced(session)
    async def test_diagnostic_failure_cannot_bypass_gate(self):
        class Broken:
            errors=0
            def emit(self,*args,**kwargs):raise RuntimeError('observer failed')
        c,session,s,p,q=self.setup_sender();s.diagnostics=Broken()
        with p,q:
            for _ in range(8):await s.rest('/fixture')
        self.assertGreater(s._diagnostic_failures,0);self.assert_paced(session)
    async def test_observer_delay_cannot_shorten_dispatch_gap(self):
        c,session,s,p,q=self.setup_sender()
        class Delayed:
            errors=0
            calls=0
            def emit(self,kind,**fields):
                if kind=='rest_start' and not self.calls:c.ns+=300_000_000;self.calls+=1
        s.diagnostics=Delayed()
        with p,q:
            await s.rest('/fixture');await s.rest('/fixture')
        self.assert_paced(session)
    async def test_two_500_symbol_repair_workloads(self):
        c,session,s,p,q=self.setup_sender();counts=[]
        class WS:
            async def send(self,message):counts.append(len(json.loads(message)['bars']))
        with p,q:
            for batch in range(2):
                for sym in s.symbols:s.queue_repair(sym,'1m',60000,120000,'MINUTE_GAP')
                while s.repairs:await s.repair_step(WS())
        self.assertEqual(len(session.entries),1000);self.assertEqual(counts,[1]*1000);self.assert_paced(session)
    async def test_multiple_pages_partial_resume_and_preload_contention(self):
        c,session,s,p,q=self.setup_sender();frames=[]
        class WS:
            async def send(self,message):frames.append(json.loads(message))
        with p,q:
            for i in range(8):s.queue_repair(s.symbols[i],'1m' if i%2 else '1d',60000 if i%2 else 86400000,120000 if i%2 else 172800000,'MINUTE_GAP' if i%2 else 'DAILY_ROLLOVER')
            await s.native_history(WS(),s.symbols[20])
            while s.repairs:await s.repair_step(WS())
        self.assert_paced(session);self.assertFalse(s._native_history_cycles);self.assertFalse(s.repairs)
    async def test_synchronous_get_failure_reserves_deadline(self):
        c,session,s,p,q=self.setup_sender();original=session.get
        def broken(*args,**kwargs):original(*args,**kwargs);raise RuntimeError('sync dispatch failure')
        with p,q:
            session.get=broken
            with self.assertRaises(RuntimeError):await s.rest('/fixture')
            session.get=original;await s.rest('/fixture')
        self.assertEqual(len(session.entries),1)
        self.assertGreaterEqual(session.entries[0]['ns'],1_000_250_000_000)

    async def test_cancelled_cooldown_remains_global(self):
        for status,delay in ((429,60),(418,60),(500,1)):
            c,session,s,p,q=self.setup_sender(statuses=[status,200],retry_after=delay)
            cancelled=False
            async def cancel_wait(wait):
                nonlocal cancelled
                if not cancelled:cancelled=True;raise asyncio.CancelledError()
                await c.sleep(wait)
            with p,q,patch.object(mod.asyncio,'sleep',cancel_wait):
                with self.assertRaises(asyncio.CancelledError):await s.rest('/fixture')
                await s.rest('/fixture')
            self.assertGreaterEqual(session.entries[1]['ns']-session.entries[0]['ns'],delay*1_000_000_000)

    async def test_cooldown_observer_cancellation_cannot_erase_deadline(self):
        c,session,s,p,q=self.setup_sender(statuses=[429,200],retry_after=60)
        class Cancel:
            errors=0
            def emit(self,kind,**fields):
                if kind=='rest_status' and fields['status']==429:raise asyncio.CancelledError()
        s.diagnostics=Cancel()
        with p,q:
            with self.assertRaises(asyncio.CancelledError):await s.rest('/fixture')
            await s.rest('/fixture')
        self.assertGreaterEqual(session.entries[1]['ns']-session.entries[0]['ns'],60_000_000_000)

    async def test_redirect_client_policy_preserved(self):
        import aiohttp
        async with aiohttp.ClientSession() as session:
            s=mod.Sender(SimpleNamespace(rest='http://127.0.0.1:1'),session)
            self.assertNotIn('allow_redirects',s._rest_options)
            self.assertTrue(session._retry_connection)
            self.assertIn(s._paced_rest_attempt,s._rest_options['middlewares'])

    async def test_paced_middleware_and_unknown_contract_rejected(self):
        import aiohttp
        async with aiohttp.ClientSession() as session:
            s=mod.Sender(SimpleNamespace(rest='http://127.0.0.1:1'),session)
            self.assertTrue(session._retry_connection)
            self.assertIn(s._paced_rest_attempt,s._rest_options['middlewares'])
            del session._middlewares
            with self.assertRaisesRegex(RuntimeError,'Unsupported aiohttp'):mod.Sender(s.args,session)

    async def test_load_sender_early_wake_does_not_send_before_interval(self):
        from Benchmarks import load_sender as load
        c=ExactClock(early=15_000_000);sent=[]
        class WS:
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            async def send(self,msg):sent.append((c.ns,msg))
            def __aiter__(self):return self
            async def __anext__(self):await asyncio.Future()
        timer=SimpleNamespace(perf_counter=lambda:c.ns/1e9,time_ns=lambda:c.ns)
        proxy=SimpleNamespace(sleep=c.sleep,create_task=asyncio.create_task,gather=asyncio.gather)
        args=SimpleNamespace(symbols_file=None,symbols=1,relay='unused',seconds=.1,interval=60)
        with patch.object(load,'connect',lambda *a,**kw:WS()),patch.object(load,'time',timer),patch.object(load,'asyncio',proxy):
            await load.run(args)
        self.assertEqual(len(sent),2) # rolesend and one initial cycle
