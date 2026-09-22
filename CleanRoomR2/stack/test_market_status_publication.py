"""Isolated publication tests: never touch the running stack's runtime files."""
import asyncio
import inspect
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

import binance_usdm_server as server


class MarketStatusTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "market_status.v1.json"
        self.path.write_text('{"old": true}\n', encoding="utf-8")
        self.old = self.path.read_bytes()
        self.app = object.__new__(server.App)
        self.app.autotrader_market_status = lambda: {"new": True}
        for name, value in (("AUTOTRADER_STATUS_PATH", self.path),
                            ("AUTOTRADER_STATUS_ENABLED", True)):
            patch = mock.patch.object(server, name, value)
            patch.start()
            self.addCleanup(patch.stop)

    async def publish(self):
        result = self.app.save_autotrader_market_status()
        if inspect.isawaitable(result):
            await result

    @unittest.skipUnless(os.name == "nt", "Windows reader-sharing reproduction")
    async def test_real_python_reader_blocks_baseline_replace(self):
        # Same open/read sharing behavior as identity_bridge.Path.read_text.
        with self.path.open("r", encoding="utf-8"):
            with self.assertRaises(PermissionError) as error:
                await self.publish()
        self.assertIn(error.exception.winerror, (5, 32))
        self.assertEqual(self.path.read_bytes(), self.old)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    async def test_normal_publication(self):
        await self.publish()
        self.assertEqual(json.loads(self.path.read_text()), {"new": True})
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    async def test_transient_denial_preserves_old_then_publishes(self):
        replace = os.replace
        calls = []

        def flaky(src, dst):
            calls.append(src)
            self.assertEqual(self.path.read_bytes(), self.old)
            self.assertEqual(json.loads(Path(src).read_text()), {"new": True})
            if len(calls) < 3:
                raise PermissionError("reader lock")
            replace(src, dst)

        with mock.patch.object(server.os, "replace", side_effect=flaky):
            with self.assertLogs(server.LOG, level="INFO") as logs:
                await self.publish()
        self.assertEqual(len(calls), 3)
        self.assertTrue(any("recovered retries=2" in line for line in logs.output))
        self.assertEqual(json.loads(self.path.read_text()), {"new": True})
        self.assertFalse(list(self.path.parent.glob("*.tmp")))

    async def test_persistent_denial_is_bounded(self):
        with mock.patch.object(server.os, "replace", side_effect=PermissionError("locked")) as replace:
            with self.assertLogs(server.LOG, level="ERROR") as logs:
                with self.assertRaises(PermissionError):
                    await asyncio.wait_for(self.publish(), timeout=2)
        self.assertEqual(replace.call_count, 5)
        self.assertIn("exhausted attempts=5", logs.output[-1])
        self.assertEqual(self.path.read_bytes(), self.old)
        self.assertFalse(list(self.path.parent.glob("*.tmp")))

    @unittest.skipUnless(os.name == "nt", "Windows reader-sharing reproduction")
    async def test_reader_release_recovers_without_blocking_event_loop(self):
        reader = self.path.open("r")
        progressed = asyncio.Event()

        async def release():
            await asyncio.sleep(0.04)
            self.assertEqual(self.path.read_bytes(), self.old)
            reader.close()
            progressed.set()

        try:
            await asyncio.gather(self.publish(), release())
        finally:
            reader.close()
        self.assertTrue(progressed.is_set())
        self.assertEqual(json.loads(self.path.read_text()), {"new": True})

    async def test_duplicate_writers_have_distinct_staging_paths(self):
        replace = os.replace
        seen = set()
        attempts = {}

        def overlap(src, dst):
            seen.add(src)
            attempts[src] = attempts.get(src, 0) + 1
            if attempts[src] == 1:
                raise PermissionError("force overlap during async wait")
            replace(src, dst)

        with mock.patch.object(server.os, "replace", side_effect=overlap):
            await asyncio.gather(self.publish(), self.publish())
        self.assertEqual(len(seen), 2)
        self.assertEqual(json.loads(self.path.read_text()), {"new": True})
        self.assertFalse(list(self.path.parent.glob("*.tmp")))

    async def test_cancellation_removes_staging_and_preserves_old(self):
        with mock.patch.object(server.os, "replace", side_effect=PermissionError("locked")):
            task = asyncio.create_task(self.publish())
            await asyncio.sleep(0)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(self.path.read_bytes(), self.old)
        self.assertFalse(list(self.path.parent.glob("*.tmp")))

    async def test_other_io_failure_is_not_retried(self):
        with mock.patch.object(server.os, "replace", side_effect=OSError("disk failure")) as replace:
            with self.assertRaises(OSError):
                await self.publish()
        self.assertEqual(replace.call_count, 1)
        self.assertEqual(self.path.read_bytes(), self.old)
        self.assertFalse(list(self.path.parent.glob("*.tmp")))


class MarketStatusReadinessTests(unittest.TestCase):
    """Per-symbol readiness must match the public websocket task partition."""

    def make_app(self, public_up, connections=3):
        patch = mock.patch.object(server, "PUBLIC_WS_CONNECTIONS", connections)
        patch.start()
        self.addCleanup(patch.stop)
        app = object.__new__(server.App)
        app.bootstrap = ["BTCUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
        app.active = set(app.bootstrap)
        app.public_up = list(public_up)
        app.market_up = True
        app.receiver_count = 1
        app.hydrated_symbols = set(app.bootstrap)
        now_ms = int(time.time() * 1000)
        app.state = {
            symbol: server.SymbolState(symbol, have_kline=True, last_market_event_unix_ms=now_ms)
            for symbol in app.bootstrap
        }
        return app

    @staticmethod
    def btc_status(app):
        return app.autotrader_market_status()["symbols"]["BTCUSDT"]

    def test_unrelated_group_down_keeps_btc_live_and_fresh(self):
        app = self.make_app([True, False, True])
        status = app.autotrader_market_status()
        self.assertFalse(status["publicUp"])
        self.assertTrue(self.btc_status(app)["live"])
        self.assertTrue(self.btc_status(app)["fresh"])

    def test_btc_own_group_down_is_not_live_or_fresh(self):
        app = self.make_app([False, True, True])
        status = app.autotrader_market_status()
        self.assertFalse(status["publicUp"])
        self.assertFalse(self.btc_status(app)["live"])
        self.assertFalse(self.btc_status(app)["fresh"])

    def test_all_groups_up_keeps_global_and_btc_ready(self):
        app = self.make_app([True, True, True])
        status = app.autotrader_market_status()
        self.assertTrue(status["publicUp"])
        self.assertTrue(self.btc_status(app)["live"])
        self.assertTrue(self.btc_status(app)["fresh"])

    def test_all_groups_down_is_not_live_or_fresh(self):
        app = self.make_app([False, False, False])
        status = app.autotrader_market_status()
        self.assertFalse(status["publicUp"])
        self.assertFalse(self.btc_status(app)["live"])
        self.assertFalse(self.btc_status(app)["fresh"])

    def test_stale_btc_remains_live_but_not_fresh(self):
        app = self.make_app([True, True, True])
        app.state["BTCUSDT"].last_market_event_unix_ms = (
            int(time.time() * 1000) - server.AUTOTRADER_STATUS_FRESH_MS - 1
        )
        status = self.btc_status(app)
        self.assertTrue(status["live"])
        self.assertFalse(status["fresh"])

    def test_missing_required_market_data_is_not_live_or_fresh(self):
        app = self.make_app([True, True, True])
        app.state["BTCUSDT"].have_kline = False
        status = self.btc_status(app)
        self.assertFalse(status["live"])
        self.assertFalse(status["fresh"])

    def test_unmapped_symbol_fails_closed(self):
        app = self.make_app([True, True, True])
        self.assertIsNone(app.active_public_group_index("UNKNOWNUSDT"))
        self.assertFalse(app.symbol_public_up("UNKNOWNUSDT"))
        unknown = server.SymbolState(
            "UNKNOWNUSDT", have_kline=True, last_market_event_unix_ms=int(time.time() * 1000)
        )
        self.assertEqual(app.symbol_readiness("UNKNOWNUSDT", unknown, 0), (False, False))

    def test_market_down_is_not_live_or_fresh(self):
        app = self.make_app([True, True, True])
        app.market_up = False
        status = self.btc_status(app)
        self.assertFalse(status["live"])
        self.assertFalse(status["fresh"])

    def test_one_public_group_agrees_globally_and_per_symbol(self):
        app = self.make_app([True], connections=1)
        self.assertEqual(app.active_public_group_index("BTCUSDT"), 0)
        self.assertTrue(app.autotrader_market_status()["publicUp"])
        self.assertTrue(self.btc_status(app)["live"])
        app.public_up = [False]
        self.assertFalse(app.autotrader_market_status()["publicUp"])
        self.assertFalse(self.btc_status(app)["live"])

    def test_group_mapping_matches_public_websocket_partition(self):
        app = self.make_app([True, True, True])
        self.assertEqual(app.active_public_group_index("BTCUSDT"), 0)
        self.assertEqual(app.active_public_group_index("SOLUSDT"), 1)
        self.assertEqual(app.active_public_group_index("BNBUSDT"), 2)
        self.assertEqual(app.active_public_group_index("XRPUSDT"), 0)
        for group_index in range(3):
            self.assertEqual(
                app.public_group_symbols(group_index),
                [symbol for symbol in sorted(app.active)
                 if app.active_public_group_index(symbol) == group_index],
            )

    def test_global_public_up_remains_all_groups_aggregation(self):
        app = self.make_app([True, False, True])
        self.assertFalse(app.public_all_up())
        self.assertFalse(app.autotrader_market_status()["publicUp"])


if __name__ == "__main__":
    unittest.main()
