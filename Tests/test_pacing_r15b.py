import asyncio, ast, importlib.util, json, time, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from Binance import sender as mod

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('original_r15b',ROOT/'Tests/references/pr3_sender.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
OBS=[]
class Clock:
    def __init__(self,early=0,stall=False):
        self.ns=1_000_000_000_000;self.early=early;self.stall=stall;self.calls=0;self.cancel_at=None;self.rollback=False
    def perf_counter_ns(self):return self.ns
    def monotonic(self):return self.ns/1e9
    def time(self):return 1791800000+self.ns/1e9
    async def sleep(self,seconds):
        self.calls+=1
        # Yield before completing the modeled wait. Cancellation at this point
        # does not advance the clock; requested delay is never elapsed evidence.
        await asyncio.sleep(0)
        if self.cancel_at is not None:
            offset=self.cancel_at;self.cancel_at=None
            if offset is not False:self.ns+=offset
            raise asyncio.CancelledError()
        if self.rollback:self.ns-=1;return
        if self.stall:return
        requested=max(0,round(seconds*1e9))
        self.ns+=requested-self.early if requested>self.early else requested
class Response:
    def __init__(self,s,status):self.s=s;self.status=status;self.headers={} if s.retry_after is None else {'Retry-After':str(s.retry_after)}
    async def __aenter__(self):
        if self.s.delay:self.s.clock.ns+=self.s.delay
        self.s.entries.append(dict(ns=self.s.clock.ns,path=self.s.path,params=self.s.params.copy()))
        if self.s.exception:
            exc=self.s.exception;self.s.exception=None;raise exc
        self.s.active+=1;self.s.maximum=max(self.s.maximum,self.s.active);return self
    async def __aexit__(self,*args):self.s.active-=1
    def raise_for_status(self):
        if self.status>=400:raise RuntimeError('simulated HTTP failure')
    async def json(self):
        await asyncio.sleep(0)
        p=self.s.params
        if 'startTime' not in p:return []
        step=86400000 if p.get('interval')=='1d' else 60000
        return [[t,'10','12','9','11','0'] for t in range(p['startTime'],min(p['endTime']+1,p['startTime']+step*p.get('limit',499)),step)]
class Session:
    def __init__(self,c,statuses=(),retry_after=60):self.clock=c;self.statuses=list(statuses);self.retry_after=retry_after;self.entries=[];self.active=0;self.maximum=0;self.delay=0;self.exception=None
    def get(self,path,params,**kwargs):self.path=path;self.params=params;return Response(self,self.statuses.pop(0) if self.statuses else 200)
def fixture(module=mod,clock=None,statuses=(),retry_after=60):
    c=clock or Clock();s=Session(c,statuses,retry_after)
    sender=module.Sender(SimpleNamespace(rest='http://fixture.invalid',native_history=True,history_days=1,batch_size=100,flush_ms=50),s)
    sender.symbols=['BTCUSDT','ETHUSDT']
    proxy=SimpleNamespace(Lock=asyncio.Lock,Queue=asyncio.Queue,sleep=c.sleep,wait_for=asyncio.wait_for)
    return c,s,sender,patch.object(module,'time',c),patch.object(module,'asyncio',proxy)
def gaps(s):return [b['ns']-a['ns'] for a,b in zip(s.entries,s.entries[1:])]
class PacingTests(unittest.IsolatedAsyncioTestCase):
    def paced(self,s):
        self.assertTrue(all(x>=250000000 for x in gaps(s)),gaps(s));self.assertLessEqual(s.maximum,1)
        OBS.append(dict(test=self.id(),gaps_ns=gaps(s),concurrency=s.maximum))
    async def ordinary(self,clock=None):
        c,s,a,p,q=fixture(clock=clock)
        with p,q:
            for _ in range(4):await a.rest('/fapi/v1/klines',symbol='BTCUSDT')
        self.paced(s);return c,s
    async def test_01_ordinary_spacing(self):await self.ordinary()
    async def test_02_early_wake_235ms(self):await self.ordinary(Clock(early=15000000))
    async def test_03_repeated_early_wakes(self):
        c,s=await self.ordinary(Clock(early=200000000));self.assertGreater(c.calls,4)
    async def cancelled(self,offset,status=429,shutdown=False):
        c,s,a,p,q=fixture(statuses=[status,200]);c.cancel_at=offset
        with p,q:
            with self.assertRaises(asyncio.CancelledError):await a.rest('/fixture')
            self.assertEqual(len(s.entries),1)
            if not shutdown:await a.rest('/fixture')
        if not shutdown:self.assertGreaterEqual(s.entries[1]['ns']-s.entries[0]['ns'],60000000000);self.paced(s)
        return s
    async def test_04_cancel_cooldown(self):await self.cancelled(0)
    async def test_05_cancel_before_expiry(self):await self.cancelled(59999999999)
    async def test_06_cancel_after_expiry(self):await self.cancelled(60000000001)
    async def test_07_shutdown_cooldown(self):await self.cancelled(0,shutdown=True)
    async def test_08_shutdown_pacing(self):
        c,s,a,p,q=fixture()
        with p,q:
            await a.rest('/fixture');c.cancel_at=0
            with self.assertRaises(asyncio.CancelledError):await a.rest('/fixture')
        self.assertEqual(len(s.entries),1)
    async def retry(self,status,header,minimum):
        c,s,a,p,q=fixture(statuses=[status,200],retry_after=header)
        with p,q:await a.rest('/fixture')
        self.assertGreaterEqual(gaps(s)[0],minimum);self.paced(s)
    async def test_09_429(self):await self.retry(429,1,1000000000)
    async def test_10_418(self):await self.retry(418,1,60000000000)
    async def test_418_cancelled_cooldown(self):await self.cancelled(0,status=418)
    async def test_418_long_retry_after(self):await self.retry(418,75,75000000000)
    async def test_11_valid_retry_after(self):await self.retry(429,2.75,2750000000)
    async def test_12_missing_retry_after(self):await self.retry(429,None,60000000000)
    async def test_13_connection_failure_followup(self):
        c,s,a,p,q=fixture();s.exception=ConnectionError('fixture')
        with p,q:
            with self.assertRaises(ConnectionError):await a.rest('/fixture')
            await a.rest('/fixture')
        self.paced(s)
    async def repairs(self,intervals):
        c,s,a,p,q=fixture();frames=[]
        class WS:
            async def send(self,msg):frames.append(json.loads(msg))
        with p,q:
            for symbol,interval in zip(a.symbols,intervals):
                step=86400000 if interval=='1d' else 60000;a.queue_repair(symbol,interval,step,step*2)
            while a.repairs:await a.repair_one(WS())
        self.assertEqual([x['params']['interval'] for x in s.entries],intervals);self.paced(s)
        return frames
    async def test_14_back_to_back_minute(self):await self.repairs(['1m','1m'])
    async def test_15_minute_then_daily(self):await self.repairs(['1m','1d'])
    async def test_16_idle_active(self):
        c,s,a,p,q=fixture()
        with p,q:
            await a.rest('/fixture');c.ns+=100000000000;await a.rest('/fixture');await a.rest('/fixture')
        self.paced(s)
    async def test_17_clock_stall_bounded(self):
        c,s,a,p,q=fixture(clock=Clock(stall=True))
        with p,q:
            await a.rest('/fixture')
            with self.assertRaisesRegex(RuntimeError,'stalled'):await a.rest('/fixture')
        self.assertEqual(c.calls,16);self.assertEqual(len(s.entries),1)
    async def test_18_clock_backward_fails_closed(self):
        c,s,a,p,q=fixture()
        with p,q:
            await a.rest('/fixture');c.rollback=True
            with self.assertRaisesRegex(RuntimeError,'anomaly'):await a.rest('/fixture')
            c.rollback=False;c.ns+=10000000000
            with self.assertRaisesRegex(RuntimeError,'anomaly'):await a.rest('/fixture')
        self.assertEqual(len(s.entries),1)
    async def test_19_concurrency_one(self):
        c,s,a,p,q=fixture()
        with p,q:await asyncio.gather(*(a.rest('/fixture',n=i) for i in range(20)))
        self.assertEqual(len(s.entries),20);self.paced(s)
    async def test_20_zero_volume(self):
        frames=await self.repairs(['1m','1d'])
        self.assertTrue(frames)
        self.assertTrue(all(float(bar[-1])==0 for frame in frames for bar in frame['bars']))
    async def test_21_restart_generation_model(self):
        c,s,a,p,q=fixture();c.cancel_at=0
        with p,q:
            await a.rest('/fixture')
            with self.assertRaises(asyncio.CancelledError):await a.rest('/fixture')
        # Old task has terminated before fresh sender construction; this model
        # does not prove live supervisor fencing or cross-process cooldown.
        c2,s2,b,p2,q2=fixture()
        with p2,q2:await b.rest('/fixture')
        self.assertEqual((len(s.entries),len(s2.entries)),(1,1))
    async def test_22_actual_entry_after_delayed_get(self):
        c,s,a,p,q=fixture();s.delay=300000000
        with p,q:
            await a.rest('/fixture');s.delay=0;await a.rest('/fixture')
        self.assertEqual(gaps(s),[250000000]);self.paced(s)
    async def test_cancel_pacing_then_resume(self):
        c,s,a,p,q=fixture()
        with p,q:
            await a.rest('/fixture');c.cancel_at=0
            with self.assertRaises(asyncio.CancelledError):await a.rest('/fixture')
            await a.rest('/fixture')
        self.paced(s)
    async def test_six_5xx_retries_unchanged(self):
        c,s,a,p,q=fixture(statuses=[500]*6)
        with p,q:
            with self.assertRaisesRegex(RuntimeError,'REST retries exhausted'):await a.rest('/fixture')
        self.assertEqual(len(s.entries),6);self.paced(s)
    async def test_cancelled_5xx_deadline_preserved_from_r6a(self):
        results={}
        for label,module in [('original',old),('candidate',mod)]:
            c,s,a,p,q=fixture(module,statuses=[500,200])
            cancelled=False
            async def cancel_backoff(seconds):
                nonlocal cancelled
                if seconds>=1 and not cancelled:
                    cancelled=True
                    raise asyncio.CancelledError()
                await c.sleep(seconds)
            with p,q,patch.object(module.asyncio,'sleep',cancel_backoff):
                with self.assertRaises(asyncio.CancelledError):await a.rest('/fixture')
                self.assertEqual(len(s.entries),1)
                await a.rest('/fixture')
            results[label]=gaps(s)
        self.assertEqual(results,dict(original=[250000000],candidate=[1000000000]))
        OBS.append(dict(test=self.id(),approved_r6a_5xx_cancelled_backoff_gaps_ns=results))
    async def test_invalid_clock_value(self):
        c,s,a,p,q=fixture();c.ns=float('nan')
        with p,q:
            with self.assertRaisesRegex(RuntimeError,'anomaly'):await a.rest('/fixture')
        self.assertFalse(s.entries)
    async def test_cancel_and_clock_rollback_does_not_mask_cancel(self):
        c,s,a,p,q=fixture();s.exception=asyncio.CancelledError();s.delay=-1
        with p,q:
            with self.assertRaises(asyncio.CancelledError):await a.rest('/fixture')
        self.assertTrue(a._rest_clock_failed)
    async def test_original_defects_and_corrected_distinct(self):
        results={}
        for label,module in [('original',old),('candidate',mod)]:
            c,s,a,p,q=fixture(module,Clock(early=15000000))
            with p,q:
                await a.rest('/fixture');await a.rest('/fixture')
            results[label]=gaps(s)
        self.assertEqual(results['original'],[235000000]);self.assertEqual(results['candidate'],[250000000])
        OBS.append(dict(test=self.id(),defect='early_wake',results=results))
    async def test_original_cancelled_cooldown_reproduced(self):
        c,s,a,p,q=fixture(old,statuses=[429,200])
        async def cancel_long(seconds):
            if seconds>=1:raise asyncio.CancelledError()
            await c.sleep(seconds)
        with p,q,patch.object(old.asyncio,'sleep',cancel_long):
            with self.assertRaises(asyncio.CancelledError):await a.rest('/fixture')
            await a.rest('/fixture')
        self.assertEqual(gaps(s),[250000000]);OBS.append(dict(test=self.id(),defect='cooldown',original_gap_ns=gaps(s)[0]))
    def test_ast_only_authorized_methods_changed(self):
        def methods(path):
            t=ast.parse(path.read_text());cls=next(n for n in t.body if isinstance(n,ast.ClassDef) and n.name=='Sender')
            return {n.name:ast.dump(n,include_attributes=False) for n in cls.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
        baseline=methods(ROOT/'Tests/references/r15b_sender.py');candidate=methods(ROOT/'Binance/sender.py')
        # RC4 bounds each sleep to 60s while retaining the absolute deadline;
        # its dedicated adversarial tests bind this sole wait-helper change.
        for name in ('_rest_now','_rest_finish','_paced_rest_attempt'):
            self.assertEqual(baseline[name],candidate[name],name)
        fairness=methods(ROOT/'Tests/references/r6a_sender.py')
        for name in ('select_repair','repair_step','repair_span','confirm_repair_page','queue_repair','repair_one','native_history','history','history_range','output'):
            self.assertEqual(fairness[name],candidate[name],name)

class HttpAttemptTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self,mode,timeout=3):
        import aiohttp
        from aiohttp.http_writer import StreamWriter
        records=[];requests=[];middleware_calls=[]
        original=StreamWriter._write
        def write(writer,data):
            if data.startswith(b'GET '):records.append(time.perf_counter_ns())
            return original(writer,data)
        async def server(reader,writer):
            try:
                data=await reader.readuntil(b'\r\n\r\n');requests.append(data.split(b'\r\n')[0].decode())
                if mode=='retry' and len(requests)==1:return
                payload=(b'HTTP/1.1 302 Found\r\nLocation: /next\r\nContent-Length: 0\r\nConnection: close\r\n\r\n' if mode=='redirect' and len(requests)==1 else b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\nConnection: close\r\n\r\n[]')
                writer.write(payload);await writer.drain()
            finally:writer.close();await writer.wait_closed()
        async def existing(request,handler):middleware_calls.append(str(request.url));return await handler(request)
        srv=await asyncio.start_server(server,'127.0.0.1',0);port=srv.sockets[0].getsockname()[1]
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout),middlewares=(existing,)) as session:
                sender=mod.Sender(SimpleNamespace(rest=f'http://127.0.0.1:{port}'),session)
                self.assertTrue(session._retry_connection)
                with patch.object(StreamWriter,'_write',write):
                    if timeout<.25:
                        with self.assertRaises(asyncio.TimeoutError):await sender.rest('/start')
                    else:await sender.rest('/start')
        finally:srv.close();await srv.wait_closed()
        self.assertTrue(records)
        if timeout>=.25:
            self.assertEqual(len(records),2);self.assertEqual(len(middleware_calls),2)
            self.assertGreaterEqual(records[1]-records[0],250000000)
        else:self.assertEqual(len(records),1)
        OBS.append(dict(test=self.id(),actual_client_header_write_ns=records,gaps_ns=[b-a for a,b in zip(records,records[1:])],requests=requests,boundary='aiohttp StreamWriter._write GET bytes to localhost transport, not Binance wire'))
    async def test_redirect_preserved_and_paced(self):await self.exercise('redirect')
    async def test_internal_retry_preserved_and_paced(self):await self.exercise('retry')
    async def test_safety_wait_consumes_unchanged_timeout(self):await self.exercise('redirect',timeout=.05)
