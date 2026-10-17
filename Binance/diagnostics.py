"""Opt-in in-memory diagnostics. No logging thread, network, or file writer.

Records use a fixed ring; callers explicitly export snapshots. Raw payloads,
URLs, headers, acknowledgments and exception messages are never retained.
"""
from collections import Counter, deque
from copy import deepcopy
import time


def timestamp(value):
    # Only numeric protocol timestamps, never malformed raw text.
    try:
        number = int(value)
        return number if 0 <= number <= 2**63-1 else None
    except (TypeError, ValueError, OverflowError):
        return None


class Diagnostics:
    def __init__(self, capacity=2048, clock=None):
        if not 16 <= capacity <= 65536:
            raise ValueError('Diagnostic capacity outside bounds')
        self.clock = clock or time
        self.records = deque(maxlen=capacity)
        self.overwritten = 0
        self.shards = {}
        self.symbols = {}
        self.jobs = {}
        self.counts = Counter()
        self.errors = 0

    def emit(self, kind, **fields):
        if len(self.records) == self.records.maxlen:
            self.overwritten += 1
        self.records.append(dict(kind=kind, utc=self.clock.time(),
                                 monotonic=self.clock.monotonic(), **fields))
        self.counts[kind] += 1

    def shard(self, shard_id, symbols, public):
        key = ('public' if public else 'market') + ':' + str(shard_id)
        if key not in self.shards:
            if len(self.shards) >= 10:
                return None
            self.shards[key] = dict(symbols=sorted(symbols)[:100], generation=0,
                                    events=0, kline_events=0, quote_events=0)
        return key

    def connection(self, key, phase, **fields):
        if key not in self.shards:
            return
        state = self.shards[key]
        now = self.clock.time()
        if phase == 'connected':
            state['generation'] += 1
            if 'disconnected_utc' in state:
                fields['reconnect_seconds'] = now - state['disconnected_utc']
        state[phase + '_utc'] = now
        if phase == 'ack' and 'subscribed_utc' in state:
            fields['ack_delay_seconds'] = now - state['subscribed_utc']
        self.emit('shard_' + phase, shard=key, generation=state['generation'], **fields)

    def event(self, payload, accepted, reason, shard_key=None):
        symbol = payload.get('s')
        if not isinstance(symbol, str) or len(symbol) > 32:
            return
        if symbol not in self.symbols and len(self.symbols) >= 500:
            return
        now = self.clock.time()
        state = self.symbols.setdefault(symbol, {})
        if shard_key in self.shards:
            shard = self.shards[shard_key]
            shard['events'] += 1
            if 'last_event_utc' in shard:
                shard['max_gap_seconds'] = max(shard.get('max_gap_seconds', 0),
                                                now-shard['last_event_utc'])
            shard['last_event_utc'] = now
        if payload.get('e') == 'kline':
            if shard_key in self.shards:
                self.shards[shard_key]['kline_events'] += 1
            k = payload.get('k', {})
            if 'raw_kline_utc' in state:
                state['interarrival_seconds'] = now-state['raw_kline_utc']
                state['max_interarrival_seconds'] = max(state.get('max_interarrival_seconds', 0),
                                                        state['interarrival_seconds'])
            state['raw_kline_utc'] = now
            if accepted:
                state.update(accepted_utc=now, accepted_event_ms=timestamp(payload.get('E')),
                             accepted_open_ms=timestamp(k.get('t')))
                if k.get('x'):
                    state.update(final_open_ms=timestamp(k.get('t')), final_close_ms=timestamp(k.get('T')),
                                 finalized_event_ms=timestamp(payload.get('E')))
            self.emit('kline', symbol=symbol, shard=shard_key, accepted=accepted,
                      generation=self.shards.get(shard_key, {}).get('generation'),
                      reason=reason, event_ms=timestamp(payload.get('E')), open_ms=timestamp(k.get('t')),
                      close_ms=timestamp(k.get('T')), finalized=bool(k.get('x')))
        else:
            if shard_key in self.shards:
                self.shards[shard_key]['quote_events'] += 1
            state['quote_utc'] = now
            self.counts['quote_activity'] += 1

    def enqueue(self, key, requested, coalesced, classification):
        now = self.clock.monotonic()
        if key not in self.jobs:
            if len(self.jobs) >= 1000:
                self.counts['job_tracking_capacity'] += 1
                return
            self.jobs[key] = dict(enqueued=now, enqueue_utc=self.clock.time(),
                                  original_range=requested, classifications=[])
        state = self.jobs[key]
        if classification not in state['classifications']:
            state['classifications'].append(classification)
        state['range'] = coalesced
        self.emit('repair_enqueue', symbol=key[0], interval=key[1],
                  classification=classification, requested=requested,
                  coalesced=coalesced, original=state['original_range'])

    def started(self, key, bounds):
        state = self.jobs.get(key)
        self.emit('repair_start', symbol=key[0], interval=key[1], bounds=bounds,
                  queue_wait_seconds=None if state is None else self.clock.monotonic()-state['enqueued'],
                  classifications=[] if state is None else state['classifications'])

    def complete(self, key, bars, removed):
        self.emit('repair_complete', symbol=key[0], interval=key[1], bars=bars,
                  removed=removed)
        if removed:
            self.jobs.pop(key, None)

    def snapshot(self):
        now = self.clock.time()
        mono = self.clock.monotonic()
        depths = {interval: sum(key[1] == interval for key in self.jobs)
                  for interval in ('1m', '1d')}
        oldest = {interval: max((mono-state['enqueued'] for key, state in self.jobs.items()
                                if key[1] == interval), default=0)
                  for interval in ('1m', '1d')}
        symbols = deepcopy(self.symbols)
        for state in symbols.values():
            for field in ('raw_kline_utc', 'accepted_utc', 'quote_utc'):
                state[field + '_age_seconds'] = None if field not in state else now-state[field]
        runs = {}
        for key, shard in self.shards.items():
            run, longest = [], []
            for symbol in shard['symbols']:
                opened = symbols.get(symbol, {}).get('accepted_open_ms')
                if opened is not None and now-opened/1000 > 90:
                    run.append(symbol)
                    if len(run) > len(longest):
                        longest = list(run)
                else:
                    run = []
            runs[key] = longest
        return dict(records=list(self.records), overwritten=self.overwritten,
                    records_complete=self.overwritten == 0 and self.errors == 0,
                    counts=dict(self.counts), shards=deepcopy(self.shards), symbols=symbols,
                    queue_depth=depths, oldest_queue_age_seconds=oldest,
                    consecutive_stale_symbols=runs, instrumentation_errors=self.errors)
