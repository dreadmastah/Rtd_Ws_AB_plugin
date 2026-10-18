"""Immutable artificial fixture reference, independent of sender.record.

These constants describe the existing R2 fixture, not real exchange data.
Expected frames are authorized by successful fixture REST responses. A recheck
may legitimately upsert the same bar in a later response; duplication within a
response or an extra delivery is never authorized.
"""
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class ReferenceFixture:
    zero_trade: bool = False
    ohlc: tuple = (10.0, 12.0, 9.0, 11.0)

    def bar(self, stamp, interval):
        utc = datetime.fromtimestamp(stamp // 1000, timezone.utc)
        date = utc.year * 10000 + utc.month * 100 + utc.day
        clock = utc.hour * 10000 + utc.minute * 100 + utc.second
        prefix = (date, clock) if interval == '1m' else (date,)
        return prefix + self.ohlc + (0.0 if self.zero_trade else 17.0,)

    def key(self, symbol, interval, stamp):
        return (symbol, interval, *self.bar(stamp, interval)[:2 if interval == '1m' else 1])


class DeliveryOracle:
    def __init__(self, reference):
        self.reference = reference
        self.pending = deque()
        self.expected_frames = self.validated_frames = self.rejected_frames = 0

    def authorize(self, params):
        step = {'1m': 60000, '1d': 86400000}[params['interval']]
        stamps = range(params['startTime'], params['endTime'] + 1, step)
        # Frozen tuple rows, independent of mutable REST payloads and encoder.
        bars = tuple(self.reference.bar(t, params['interval']) for t in stamps[:params['limit']])
        if not bars:
            return
        if len(self.pending) >= 2:
            raise AssertionError('Undelivered reference frames exceed fixture bound')
        self.pending.append((params['symbol'], 'dtohlcv' if params['interval']=='1m' else 'dohlcv', bars))
        self.expected_frames += 1

    def receive(self, frame):
        actual = (frame.get('hist'), frame.get('format'), tuple(tuple(b) for b in frame.get('bars', ())))
        expected = self.pending.popleft() if self.pending else None
        correct = actual == expected
        self.validated_frames += correct
        self.rejected_frames += not correct
        return correct

    @property
    def complete(self):
        return not self.pending and self.rejected_frames == 0 and self.validated_frames == self.expected_frames
