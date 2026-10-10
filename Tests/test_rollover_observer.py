import unittest
from Benchmarks.observe_rollover import assess


class RolloverAcceptanceTests(unittest.TestCase):
    def test_pass_requires_each_independent_acceptance_check(self):
        expected = {'BTCUSDT', 'ETHUSDT', 'XRPUSDT'}
        daily = dict.fromkeys(expected, [])
        samples = dict.fromkeys(expected, True)
        self.assertEqual(assess(expected, expected, expected, daily, samples,
                                True, True, expected)['status'], 'PASS')
        for pre, post, history, matches, connected, stable, fresh in (
            (set(), expected, daily, samples, True, True, expected),
            (expected, set(), daily, samples, True, True, expected),
            (expected, expected, {}, samples, True, True, expected),
            (expected, expected, daily, {'BTCUSDT': False}, True, True, expected),
            (expected, expected, daily, samples, False, True, expected),
            (expected, expected, daily, samples, True, False, expected),
            (expected, expected, daily, samples, True, True, set()),
        ):
            self.assertEqual(assess(expected, pre, post, history, matches,
                                    connected, stable, fresh)['status'], 'FAIL')

    def test_empty_rest_validation_cannot_pass(self):
        expected = {'BTCUSDT'}
        self.assertEqual(assess(expected, expected, expected, dict.fromkeys(expected), {},
                                True, True, expected)['status'], 'FAIL')

    def test_partial_rest_validation_cannot_pass(self):
        expected = {'BTCUSDT', 'ETHUSDT', 'XRPUSDT'}
        self.assertEqual(assess(expected, expected, expected, dict.fromkeys(expected),
                                {'BTCUSDT': True}, True, True, expected)['status'], 'FAIL')

class RolloverWindowTests(unittest.IsolatedAsyncioTestCase):
    async def test_early_or_late_start_fails_without_connecting(self):
        from datetime import datetime, timedelta, timezone
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from types import SimpleNamespace
        from unittest.mock import patch
        from Benchmarks.observe_rollover import observe
        with TemporaryDirectory() as directory:
            root = Path(directory)
            symbols = root / 'symbols.txt'
            symbols.write_text('\n'.join(f'S{i}' for i in range(500)))
            for hours in (-1, 1):
                args = SimpleNamespace(output=root / str(hours), symbols=symbols, runtime=root)
                with patch('Benchmarks.observe_rollover.connect') as connect:
                    result = await observe(args, datetime.now(timezone.utc) + timedelta(hours=hours))
                self.assertEqual(result['status'], 'FAIL')
                self.assertIn('Observer started', result['error'])
                self.assertFalse(result['actual_boundary_observed'])
                connect.assert_not_called()
