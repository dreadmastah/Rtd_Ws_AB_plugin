import asyncio,ast,hashlib,json,sys,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
from Binance import sender
from Binance.telemetry_sender import TelemetrySender
from Binance.rest_telemetry import RestTelemetry
import test_pacing_r15b as fixtures
ROOT=Path(__file__).resolve().parents[1]

class RC2Integration(unittest.IsolatedAsyncioTestCase):
    async def test_exact_500_market_symbols_in_five_shards(self):
        engine=sender.Sender(SimpleNamespace(shard_size=100,quotes=False),None)
        universe=[f'S{i:03}USDT' for i in range(500)];calls=[]
        async def discover():engine.symbols=universe
        async def shard(symbols,public=False):calls.append((symbols,public))
        engine.discover=discover;engine.shard=shard
        engine.relay=AsyncMock();engine.metrics=AsyncMock()
        await engine.run()
        self.assertEqual(len(calls),5);self.assertTrue(all(len(s)==100 and not public for s,public in calls))
        self.assertEqual(set.union(*(s for s,_ in calls)),set(universe))
        self.assertEqual(sum(map(len,(s for s,_ in calls))),500)

    async def test_nested_preload_repairs_have_accurate_roles_and_restore_context(self):
        clock=fixtures.Clock();session=fixtures.Session(clock)
        recorder=RestTelemetry(monotonic_ns=clock.perf_counter_ns,utc_ns=lambda:1791800000000000000+clock.ns)
        engine=TelemetrySender(SimpleNamespace(rest='unused',native_history=True,history_days=1,batch_size=100,flush_ms=50),session,recorder)
        engine.symbols=['BTCUSDT','ETHUSDT'];frames=[]
        class WS:
            async def send(self,x):frames.append(json.loads(x))
        engine.queue_repair('ETHUSDT','1m',60000,120000,'MINUTE_RECONNECT')
        with patch.object(sender,'time',clock),patch.object(sender,'asyncio',SimpleNamespace(sleep=clock.sleep,wait_for=asyncio.wait_for)):
            await engine.native_history(WS(),'BTCUSDT')
        roles=[r['request_class'] for r in recorder.records]
        self.assertIn('MINUTE_REPAIR',roles);self.assertIn('PRELOAD',roles)
        self.assertEqual(engine._role.get(),'HISTORY');self.assertFalse(engine.repairs)
        self.assertEqual(len(frames),len(session.entries))

    async def test_repair_role_resets_on_cancellation_and_retains_job(self):
        engine=TelemetrySender(SimpleNamespace(history_days=1),None,RestTelemetry())
        engine.symbols=['BTCUSDT'];engine.queue_repair('BTCUSDT','1m',60000,120000)
        async def cancelled(*a,**kw):
            self.assertEqual(engine._role.get(),'REPAIR');raise asyncio.CancelledError()
        engine.history_range=cancelled
        with self.assertRaises(asyncio.CancelledError):await engine.repair_step(None)
        self.assertEqual(engine._role.get(),'HISTORY');self.assertIn(('BTCUSDT','1m'),engine.repairs)

    def test_default_cli_preserves_protocol_and_telemetry_off(self):
        with patch.object(sys,'argv',['sender.py']):args=sender.arguments()
        self.assertFalse(args.rest_telemetry);self.assertEqual(args.limit,500);self.assertEqual(args.shard_size,100)
        self.assertFalse(args.quotes);self.assertFalse(args.native_history)

    def test_supervisor_byte_identity_and_no_maintenance_import(self):
        data=(ROOT/'Benchmarks/supervise_test_feed.py').read_bytes()
        # Exact SHA256 of the PR3 Git blob retained by the candidate.
        expected=json.loads((ROOT/'Tests/references/identity.json').read_text())['supervisor_sha256']
        self.assertEqual(hashlib.sha256(data).hexdigest(),expected)
        self.assertNotIn(b'supervisor_maintenance',data)
        self.assertFalse((ROOT/'Benchmarks/windows_fixture_adapter.py').exists())

    def test_dependency_versions_match_recorded_pins(self):
        import importlib.metadata
        for line in (ROOT/'requirements-rc2.lock').read_text().splitlines():
            name,version=line.split('==');self.assertEqual(importlib.metadata.version(name),version)

    def test_no_order_endpoint_or_private_auth_added(self):
        for name in ['sender.py','telemetry_sender.py','telemetry_export.py','rest_telemetry.py']:
            tree=ast.parse((ROOT/'Binance'/name).read_text())
            values=[n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str)]
            self.assertFalse(any('/fapi/v1/order' in v or '/fapi/v1/listenKey' in v for v in values),name)
