import asyncio,ast,importlib.util,json,math,os,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from Binance import sender as mod
from Binance.telemetry_sender import TelemetrySender
from Binance.rest_telemetry import RestTelemetry
import test_pacing_r15b as base

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('rc4_original',ROOT/'Tests/references/rc2_sender.py')
original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)

async def defect(module):
    c,s,a,p,q=base.fixture(module,statuses=[418,200],retry_after='broken')
    error=None
    with p,q:
        try:await a.rest('/fapi/v1/klines',symbol='BTCUSDT')
        except ValueError as exc:error=type(exc).__name__
        await a.rest('/fapi/v1/klines',symbol='ETHUSDT')
    return {'error':error,'gap_ns':base.gaps(s)[0],'cooldown_required_ns':60_000_000_000,'bypass':base.gaps(s)[0]<60_000_000_000}

class RetryAfterTests(unittest.IsolatedAsyncioTestCase):
    async def test_original_defect_red_corrected_green(self):
        old=await defect(original);new=await defect(mod)
        self.assertTrue(old['bypass']);self.assertEqual(old['gap_ns'],250_000_000)
        self.assertFalse(new['bypass']);self.assertIsNone(new['error'])

    async def exercise(self,status,header,minimum,telemetry=False):
        c,s,a,p,q=base.fixture(statuses=[status,200],retry_after=header)
        if telemetry:
            a=TelemetrySender(a.args,s,RestTelemetry());a.symbols=['BTCUSDT','ETHUSDT']
        with p,q:await a.rest('/fapi/v1/klines',symbol='BTCUSDT')
        self.assertGreaterEqual(base.gaps(s)[0],minimum)
        self.assertEqual(len(s.entries),2);self.assertEqual(s.maximum,1)

    async def test_cancel_invalid_then_independent_caller(self):
        for status in (418,429):
            c,s,a,p,q=base.fixture(statuses=[status,200],retry_after='broken');c.cancel_at=0
            with p,q:
                with self.assertRaises(asyncio.CancelledError):await a.rest('/repair')
                await a.rest('/preload')
            self.assertGreaterEqual(base.gaps(s)[0],60_000_000_000)

    async def test_header_access_exception_preserves_fallback(self):
        for exc in (RuntimeError('header failure'),asyncio.CancelledError()):
            class Headers:
                def get(self,*args):raise exc
            class Response(base.Response):
                def __init__(self,s,status):super().__init__(s,status);self.headers=Headers() if status==429 else {}
            c,s,a,p,q=base.fixture(statuses=[429,200])
            def get(path,params,**kwargs):s.path=path;s.params=params;return Response(s,s.statuses.pop(0))
            s.get=get
            with p,q:
                with self.assertRaises(type(exc)):await a.rest('/repair')
                await a.rest('/preload')
            self.assertGreaterEqual(base.gaps(s)[0],60_000_000_000)

    async def test_observer_exception_preserves_deadline(self):
        c,s,a,p,q=base.fixture(statuses=[418,200],retry_after='broken')
        def diagnostic(method,event,**kwargs):
            if event=='rest_status':raise RuntimeError('observer')
        a.diagnostic=diagnostic
        with p,q:
            with self.assertRaises(RuntimeError):await a.rest('/repair')
            a.diagnostic=lambda *a,**k:None
            await a.rest('/preload')
        self.assertGreaterEqual(base.gaps(s)[0],60_000_000_000)

    async def test_concurrent_callers_and_consecutive_statuses(self):
        c,s,a,p,q=base.fixture(statuses=[418,429,200,200],retry_after='broken')
        with p,q:await asyncio.gather(a.rest('/repair'),a.rest('/preload'))
        self.assertGreaterEqual(base.gaps(s)[0],60_000_000_000)
        self.assertGreaterEqual(base.gaps(s)[1],60_000_000_000)
        self.assertGreaterEqual(base.gaps(s)[2],250_000_000);self.assertEqual(s.maximum,1)

    async def test_repair_competes_with_native_history(self):
        c,s,a,p,q=base.fixture(statuses=[429,200],retry_after='broken')
        class WS:
            async def send(self,msg):pass
        a.queue_repair('BTCUSDT','1m',60000,120000)
        with p,q:await asyncio.gather(a.repair_step(WS()),a.native_history(WS(),'ETHUSDT'))
        self.assertGreaterEqual(base.gaps(s)[0],60_000_000_000);self.assertEqual(s.maximum,1)

    async def test_extreme_finite_deadline_not_shortened_or_overflowed(self):
        c,s,a,p,q=base.fixture(statuses=[429,200],retry_after='1e308')
        waits=[]
        async def cancel(seconds):waits.append(seconds);raise asyncio.CancelledError()
        with p,q,patch.object(mod.asyncio,'sleep',cancel):
            with self.assertRaises(asyncio.CancelledError):await a.rest('/repair')
        self.assertEqual(waits,[60]);self.assertEqual(len(s.entries),1)
        self.assertGreater(a._rest_next_ns,10**316)
        prior=a._rest_next_ns
        with p,q,patch.object(mod.asyncio,'sleep',cancel):
            with self.assertRaises(asyncio.CancelledError):await a.rest('/preload')
        self.assertEqual(a._rest_next_ns,prior);self.assertEqual(len(s.entries),1)

    async def test_six_invalid_status_retries_remain_bounded(self):
        c,s,a,p,q=base.fixture(statuses=[429]*8,retry_after='broken')
        with p,q:
            with self.assertRaisesRegex(RuntimeError,'retries exhausted'):await a.rest('/repair')
        self.assertEqual(len(s.entries),6);self.assertTrue(all(g>=60_000_000_000 for g in base.gaps(s)))

    async def test_actual_clock_local_http_cooldown_and_pacing(self):
        import aiohttp
        seen=[]
        async def handler(reader,writer):
            await reader.readuntil(b'\r\n\r\n');seen.append(time.perf_counter_ns())
            status='429 Too Many Requests' if len(seen)==1 else '200 OK'
            writer.write(('HTTP/1.1 '+status+'\r\nRetry-After: 1\r\nContent-Type: application/json\r\nContent-Length: 2\r\nConnection: close\r\n\r\n[]').encode());await writer.drain();writer.close();await writer.wait_closed()
        server=await asyncio.start_server(handler,'127.0.0.1',0)
        try:
            async with aiohttp.ClientSession() as session:
                a=mod.Sender(SimpleNamespace(rest='http://127.0.0.1:'+str(server.sockets[0].getsockname()[1]),native_history=False),session)
                await asyncio.gather(a.rest('/repair'),a.rest('/preload'))
        finally:server.close();await server.wait_closed()
        self.assertEqual(len(seen),3)
        self.assertGreaterEqual(seen[1]-seen[0],1_000_000_000)
        self.assertGreaterEqual(seen[2]-seen[1],250_000_000)

    def test_only_cooldown_methods_changed_and_fairness_exact(self):
        def methods(path):
            cls=next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.ClassDef) and n.name=='Sender')
            return {n.name:ast.dump(n,include_attributes=False) for n in cls.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
        old=methods(ROOT/'Tests/references/rc2_sender.py');new=methods(ROOT/'Binance/sender.py')
        self.assertEqual({k for k in old if old[k]!=new[k]},{'rest','_rest_wait'})
        self.assertEqual(set(new)-set(old),{'_retry_after_seconds'})

CASES=[('numeric','2.75',2.75),('missing',None,60),('empty','',60),('text','invalid',60),('negative','-3',60),('zero','0',0),('nan','NaN',60),('infinity','inf',60),('negative_inf','-inf',60),('overflow','1e9999',60),('large','3600',3600),('http_date','Wed, 21 Oct 2015 07:28:00 GMT',60),('bad_date','Wed, nonsense',60)]
for label,header,seconds in CASES:
    for status in (418,429):
        async def test(self,header=header,status=status,seconds=seconds):
            await self.exercise(status,header,math.ceil(max(60 if status==418 else 1,seconds)*1e9))
        setattr(RetryAfterTests,'test_'+str(status)+'_'+label,test)
    async def observed(self,header=header,seconds=seconds):await self.exercise(429,header,math.ceil(max(1,seconds)*1e9),True)
    setattr(RetryAfterTests,'test_telemetry_'+label,observed)
