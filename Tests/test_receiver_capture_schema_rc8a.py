"""RC8A approved schema: offline admission, certification and export tests."""
import builtins
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from Benchmarks.receiver_capture import PassiveCapture


LIMIT = 2**63-1
CORE = ('symbol', 'interval', 'candle_open_ms', 'ohlcv', 'raw_received',
        'parser_accepted', 'relay_receipt_utc_ms', 'relay_receipt_monotonic_ns')
SIDE = ('sender_generation', 'sender_sequence', 'shard', 'upstream_event_ms',
        'upstream_close_ms', 'finalized', 'repair_class')
INTEGERS = ('candle_open_ms', 'relay_receipt_utc_ms', 'relay_receipt_monotonic_ns',
            'sender_sequence', 'upstream_event_ms', 'upstream_close_ms')


def candle():
    return dict(kind='candle', symbol='BTCUSDT', interval='1m', candle_open_ms=60000,
                ohlcv=[10., 12., 9., 11., 0.], raw_received=True, parser_accepted=True,
                relay_receipt_utc_ms=120001, relay_receipt_monotonic_ns=1234)


class SchemaTests(unittest.TestCase):
    def capture(self, **kwargs):
        return PassiveCapture('rc8a-test', **kwargs)

    def exported(self, capture):
        with tempfile.TemporaryDirectory(dir=os.environ['RC2_OUTPUT']) as tmp:
            root = Path(tmp)/'fresh'
            self.assertTrue(capture.export(root))
            manifest = json.loads((root/'capture-manifest.json').read_text())
            rows = []
            for entry in manifest['segments']:
                data = (root/entry['path']).read_bytes()
                self.assertEqual(len(data), entry['bytes'])
                self.assertEqual(hashlib.sha256(data).hexdigest(), entry['sha256'])
                rows.extend(json.loads(line) for line in data.splitlines())
            return manifest, rows

    def rejected(self, record):
        cap = self.capture()
        self.assertIs(cap.offer(record), False)
        self.assertEqual(cap.counts['offered'], 1)
        self.assertEqual(cap.sequence, 1)
        self.assertEqual(cap.counts['invalid'], 1)
        self.assertEqual(cap.counts['accepted'], 0)
        self.assertEqual(cap.counts['uncertified'], 0)
        self.assertEqual(cap.observer_failures, 0)
        self.assertEqual(len(cap.records), 0)
        self.assertEqual(cap.bytes, 0)
        self.assertFalse(cap.health()['evidence_complete'])
        manifest, rows = self.exported(cap)
        self.assertFalse(manifest['health']['evidence_complete'])
        self.assertEqual(rows, [])

    def diagnostic(self, record):
        cap = self.capture()
        self.assertIs(cap.offer(record), True)
        self.assertEqual(cap.counts['accepted'], 1)
        self.assertEqual(cap.counts['invalid'], 0)
        self.assertEqual(cap.counts['uncertified'], 1)
        self.assertFalse(cap.health()['evidence_complete'])
        manifest, rows = self.exported(cap)
        self.assertFalse(manifest['health']['evidence_complete'])
        self.assertEqual(len(rows), 1)
        return rows[0]

    def certified(self, record):
        cap = self.capture()
        self.assertTrue(cap.offer(record))
        self.assertTrue(cap.health()['evidence_complete'])
        self.assertEqual(cap.counts['uncertified'], 0)
        manifest, rows = self.exported(cap)
        self.assertTrue(manifest['health']['evidence_complete'])
        self.assertEqual(manifest['health']['schema_contract'], 'RC8A_CAPTURE_MINIMUM_V1')
        self.assertEqual(manifest['health']['native_storage_acceptance'], 'NOT_PROVEN')
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_p2_symbol_number(self):
        self.rejected(dict(candle(), symbol=42))

    def test_p2_ohlcv_string(self):
        self.rejected(dict(candle(), ohlcv='not-a-vector'))

    def test_p2_raw_received_string(self):
        self.rejected(dict(candle(), raw_received='yes'))

    def test_full_candle_and_original_envelope(self):
        row = self.certified(candle())
        self.assertEqual(set(row), set(candle()) | set(SIDE) |
                         {'receiver_generation', 'capture_sequence', 'schema_version'})
        self.assertEqual(row['schema_version'], 1)
        self.assertEqual(row['capture_sequence'], 1)
        for key in SIDE:
            self.assertIsNone(row[key])

    def test_all_populated_optional_fields_and_preservation(self):
        record = dict(candle(), sender_generation='sender-A', sender_sequence=2,
                      shard='market:2', upstream_event_ms=61000, upstream_close_ms=119999,
                      finalized=True, repair_class='MINUTE_STALE', transition=None,
                      payload_sha256='A'*64)
        row = self.certified(record)
        for key, value in record.items():
            self.assertEqual(row[key], value)

    def test_each_core_omission_is_diagnostic_not_invalid(self):
        for key in CORE:
            with self.subTest(field=key):
                record = candle(); del record[key]
                self.assertNotIn(key, self.diagnostic(record))

    def test_each_core_null_is_diagnostic(self):
        for key in CORE:
            with self.subTest(field=key):
                self.assertIsNone(self.diagnostic(dict(candle(), **{key: None}))[key])

    def test_optional_absence_and_null_do_not_taint_candle(self):
        for key in (*SIDE, 'transition', 'payload_sha256'):
            with self.subTest(field=key):
                self.assertIsNone(self.certified(dict(candle(), **{key: None}))[key])

    def test_raw_frame_unknown_and_partial_kind_observations(self):
        for kind in ('raw_frame', 'history', 'live', 'parser_acceptance', 'gap_transition', 'future:v2', 'candle'):
            with self.subTest(kind=kind):
                self.diagnostic(dict(kind=kind))
        self.diagnostic(dict(kind='raw_frame', raw_received=True))

    def test_unknown_kind_cannot_certify_even_with_complete_fields(self):
        for kind in ('raw_frame', 'unknown', 'CANDLE', 'x'*128, '\u5e01'):
            with self.subTest(kind=kind):
                self.diagnostic(dict(candle(), kind=kind))

    def test_false_receipt_or_parser_flags_are_diagnostic(self):
        for key in ('raw_received', 'parser_accepted'):
            self.diagnostic(dict(candle(), **{key: False}))
        self.certified(dict(candle(), finalized=False))

    def test_kind_mandatory_nonnull_and_token_limits(self):
        record = candle(); del record['kind']; self.rejected(record)
        for value in (None, '', 1, True, 'a b', 'x\n', '\x00', 'x'*129):
            with self.subTest(value=value): self.rejected(dict(candle(), kind=value))

    def test_symbol_approved_unicode_case_and_punctuation(self):
        for value in ('BTCUSDT', 'abc-usdt', 'A.B', 'ABC_DEF', '\u5e01USDT', 'a'*128, '1'):
            with self.subTest(value=value): self.certified(dict(candle(), symbol=value))
        for value in ('', '---', 'a b', 'BTC/USDT', 'BTC\n', '\x00', 'a'*129, True, [], 1.5):
            with self.subTest(value=value): self.rejected(dict(candle(), symbol=value))

    def test_interval_enumeration(self):
        self.certified(dict(candle(), interval='1d'))
        for value in ('1h', '1M', '', True, 1): self.rejected(dict(candle(), interval=value))

    def test_integer_boundaries_no_alignment_or_order_inference(self):
        for key in INTEGERS:
            for value in (0, 1, LIMIT):
                with self.subTest(field=key, value=value): self.certified(dict(candle(), **{key: value}))
        self.certified(dict(candle(), candle_open_ms=123, relay_receipt_utc_ms=0,
                            upstream_event_ms=LIMIT, upstream_close_ms=0, sender_sequence=0))

    def test_invalid_integer_types_ranges_and_nonfinite(self):
        for key in INTEGERS:
            for value in (-1, LIMIT+1, True, False, 1.0, '1', math.nan, math.inf, -math.inf):
                with self.subTest(field=key, value=value): self.rejected(dict(candle(), **{key: value}))

    def test_boolean_fields_use_exact_bool(self):
        for key in ('raw_received', 'parser_accepted', 'finalized'):
            for value in (0, 1, 'true', '', 1.0):
                with self.subTest(field=key, value=value): self.rejected(dict(candle(), **{key: value}))

    def test_ohlcv_tuple_zero_volume_and_large_finite_integer(self):
        for vector in ([10, 12, 9, 11, 0], (10., 12., 9., 11., 0.),
                       [2**64, 2**64, 2**64, 2**64, 0], [1, 1, 1, 1, -0.0]):
            self.certified(dict(candle(), ohlcv=vector))

    def test_ohlcv_invalid_container_length_and_elements(self):
        for value in ('not-a-vector', {}, 42, True, [], [1]*4, [1]*6,
                      [1, 1, 1, 1, True], [1, 1, 1, 1, '0'], [1, 1, 1, 1, None],
                      [1, 1, 1, 1, 10**400]):
            with self.subTest(value=str(value)[:50]): self.rejected(dict(candle(), ohlcv=value))

    def test_ohlcv_nonfinite_in_each_position(self):
        for pos in range(5):
            for bad in (math.nan, math.inf, -math.inf):
                vector = [10, 12, 9, 11, 0]; vector[pos] = bad
                with self.subTest(position=pos, value=bad): self.rejected(dict(candle(), ohlcv=vector))

    def test_ohlcv_price_and_volume_constraints(self):
        for vector in ([10,12,9,11,-1], [0,1,0,1,0], [10,12,-1,11,0],
                       [8,12,9,11,0], [13,12,9,11,0], [10,12,9,13,0], [10,8,9,11,0]):
            self.rejected(dict(candle(), ohlcv=vector))

    def test_generation_bounded_opaque_token(self):
        for value in ('sender-A', 'generation:1', '\u5e01', 'x'*128):
            self.certified(dict(candle(), sender_generation=value))
        for value in ('', 'a b', 'a\t', 'x'*129, 42, True):
            self.rejected(dict(candle(), sender_generation=value))

    def test_shard_canonical_namespace_and_boundary(self):
        for value in ('market:0', 'market:2', 'public:5', 'market:'+str(LIMIT)):
            self.certified(dict(candle(), shard=value))
        for value in ('market:02', 'market:-1', 'market:', 'market:+1', 'market:1 ',
                      'other:1', 'public:1:2', 'public:\u0661', 'market:'+str(LIMIT+1),
                      'market:'+'1'*20, 2, True): self.rejected(dict(candle(), shard=value))

    def test_repair_classes_and_conditional_interval_pairing(self):
        groups = {'1m': ('MINUTE_GAP','MINUTE_STALE','MINUTE_RECONNECT'),
                  '1d': ('DAILY_ROLLOVER','DAILY_RECHECK')}
        for interval, classes in groups.items():
            for value in classes:
                self.certified(dict(candle(), interval=interval, repair_class=value))
                self.rejected(dict(candle(), interval='1d' if interval=='1m' else '1m', repair_class=value))
                self.diagnostic(dict(kind='raw_frame', repair_class=value))
                self.diagnostic(dict(kind='raw_frame', interval=None, repair_class=value))
        for value in ('MANUAL_HISTORY','NATIVE_PRELOAD'):
            for interval in ('1m','1d'): self.certified(dict(candle(), interval=interval, repair_class=value))
        for value in ('UNKNOWN', [], 3, 'MINUTE_GAP,MINUTE_STALE'):
            self.rejected(dict(candle(), repair_class=value))

    def test_sha256_exact_format_and_no_normalization(self):
        for value in ('a'*64, 'A'*64, '0123456789abcdef'*4):
            self.assertEqual(self.certified(dict(candle(), payload_sha256=value))['payload_sha256'], value)
        for value in ('a'*63, 'a'*65, 'g'*64, '0x'+'a'*64, ' '*64, b'a'*64, 42):
            self.rejected(dict(candle(), payload_sha256=value))

    def test_transition_omitted_null_and_all_nonnull_rejected(self):
        self.assertNotIn('transition', self.certified(candle()))
        self.certified(dict(candle(), transition=None))
        for kind in ('candle','raw_frame','gap_transition'):
            for value in ('gap_opened','gap_closed','',0,False,[],{}):
                self.rejected(dict(candle(), kind=kind, transition=value))

    def test_unexpected_keys_oversized_mapping_and_non_dict(self):
        for value in (dict(candle(), secret='ignored'), {'x'*10000:None},
                      {str(i):None for i in range(100)}, [], None): self.rejected(value)

    def test_builtin_only_no_subclass_callbacks(self):
        class D(dict):
            def __len__(self): raise AssertionError('must not call')
        class S(str): pass
        class L(list): pass
        class T(tuple): pass
        class N(int): pass
        self.rejected(D(candle()))
        for key,value in [('kind',S('candle')),('symbol',S('BTCUSDT')),
                          ('ohlcv',L([10,12,9,11,0])),('ohlcv',T([10,12,9,11,0])),
                          ('sender_sequence',N(1)),('ohlcv',[10,12,9,11,N(0)])]:
            self.rejected(dict(candle(), **{key:value}))
        self.rejected({S('kind'):'candle'})

    def test_empty_health_and_empty_exports_never_complete(self):
        cap=self.capture();self.assertFalse(cap.health()['evidence_complete'])
        self.assertFalse(self.exported(cap)[0]['health']['evidence_complete'])
        cap.offer(candle());self.assertTrue(self.exported(cap)[0]['health']['evidence_complete'])
        self.assertTrue(cap.health()['evidence_complete'])  # lifetime health after drain
        self.assertFalse(self.exported(cap)[0]['health']['evidence_complete'])

    def test_diagnostic_taint_sticky_across_drain_and_valid_records(self):
        cap=self.capture();cap.offer(dict(kind='future'))
        self.assertFalse(self.exported(cap)[0]['health']['evidence_complete'])
        cap.offer(candle());manifest,rows=self.exported(cap)
        self.assertFalse(manifest['health']['evidence_complete']);self.assertEqual(len(rows),1)
        self.assertEqual(manifest['health']['counts']['uncertified'],1)

    def test_invalid_taint_sticky_after_valid_record(self):
        cap=self.capture();self.assertFalse(cap.offer(dict(candle(),symbol=42)))
        cap.offer(candle());manifest,rows=self.exported(cap)
        self.assertFalse(manifest['health']['evidence_complete'])
        self.assertEqual([r['symbol'] for r in rows],['BTCUSDT'])

    def test_capacity_overflow_does_not_count_unenqueued_diagnostic(self):
        cap=self.capture(capacity=1);cap.offer(candle())
        self.assertFalse(cap.offer(dict(kind='future')))
        self.assertEqual(cap.counts['accepted'],1);self.assertEqual(cap.counts['overflow'],1)
        self.assertEqual(cap.counts['uncertified'],0)
        self.assertFalse(self.exported(cap)[0]['health']['evidence_complete'])

    def test_byte_capacity_and_record_limit_preserved(self):
        cap=self.capture(record_limit=512,byte_capacity=512)
        self.assertTrue(cap.offer(candle()));self.assertFalse(cap.offer(candle()))
        self.assertEqual(cap.counts['overflow'],1);self.assertLessEqual(cap.bytes,512)
        cap=self.capture(record_limit=128,byte_capacity=128)
        self.assertFalse(cap.offer(candle()));self.assertEqual(cap.counts['invalid'],1)

    def test_retention_loss_including_diagnostic_outside_retained_segments(self):
        cap=self.capture(record_limit=1024,artifact_limit=1024,retained_artifacts=1)
        for _ in range(6): self.assertTrue(cap.offer(candle()))
        self.assertTrue(cap.offer(dict(kind='future')))
        manifest,rows=self.exported(cap)
        self.assertTrue(all(row['kind']=='candle' for row in rows))
        self.assertGreater(manifest['health']['counts']['retention_loss'],0)
        self.assertEqual(manifest['health']['counts']['uncertified'],1)
        self.assertFalse(manifest['health']['evidence_complete'])

    def test_export_error_retry_preserves_records_and_incomplete(self):
        cap=self.capture();cap.offer(candle())
        with tempfile.TemporaryDirectory(dir=os.environ['RC2_OUTPUT']) as tmp:
            self.assertFalse(cap.export(tmp));self.assertEqual(len(cap.records),1)
        manifest,rows=self.exported(cap)
        self.assertEqual(len(rows),1);self.assertFalse(manifest['health']['evidence_complete'])
        self.assertEqual(manifest['health']['counts']['export_errors'],1)

    def test_observer_exception_isolated_and_memoryerror_propagates(self):
        cap=self.capture();cap.records=None
        self.assertFalse(cap.offer(dict(kind='raw_frame',raw_received=True)))
        self.assertEqual(cap.observer_failures,1)
        self.assertEqual(cap.counts['accepted'],0);self.assertFalse(cap.health()['evidence_complete'])
        cap=self.capture()
        with patch('Benchmarks.receiver_capture.json.dumps',side_effect=MemoryError):
            with self.assertRaises(MemoryError): cap.offer(candle())
        self.assertEqual(cap.counts['invalid'],0)

    def test_offer_has_no_file_io_and_never_mutates_input(self):
        cap=self.capture();record=candle();before=json.dumps(record,sort_keys=True)
        with patch.object(builtins,'open',side_effect=AssertionError('offer file IO')):
            self.assertTrue(cap.offer(record))
        self.assertEqual(json.dumps(record,sort_keys=True),before)

    def test_uncertified_saturation_sequence_exhaustion_and_closed(self):
        cap=self.capture();cap.counts['uncertified']=LIMIT
        self.assertTrue(cap.offer(dict(kind='future')));self.assertEqual(cap.counts['uncertified'],LIMIT)
        cap=self.capture();cap.sequence=LIMIT
        self.assertFalse(cap.offer(candle()));self.assertEqual(cap.counts['invalid'],1)
        self.assertEqual(cap.counts['offered'],0)
        cap=self.capture();cap.close();self.assertFalse(cap.offer(dict(kind='future')))
        self.assertEqual(cap.counts['closed'],1);self.assertEqual(cap.counts['uncertified'],0)


if __name__ == '__main__':
    unittest.main()
