"""Opt-in, bounded in-memory REST observations; never an IP budget allocator.

Producer methods do no IO, await, locking, serialization or user callbacks
other than the trusted injectable clocks. Snapshots/aggregation are OFF-path.
One recorder belongs to one sender/event-loop and is not thread safe.
"""
import os
import time
import uuid

MAX_RECORDS = 4096
MAX_GENERATIONS = 32
MAX_COUNTER = 2**63 - 1
CLASSES = frozenset(('STARTUP', 'PRELOAD', 'MINUTE_REPAIR', 'DAILY_REPAIR',
                     'HISTORY', 'UNKNOWN'))
HEADER_NAMES = ('X-MBX-USED-WEIGHT-1M', 'X-MBX-USED-WEIGHT-1S',
                'X-MBX-USED-WEIGHT-1H', 'X-MBX-USED-WEIGHT-1D')


def bounded_int(value, maximum=MAX_COUNTER):
    if type(value) is int:
        return value if 0 <= value <= maximum else None
    if type(value) is str and 0 < len(value) <= 19 and value.isascii() and value.isdecimal():
        number = int(value)
        return number if number <= maximum else None
    return None


def generation_token(value):
    # UUID-only identifiers prevent arbitrary labels/command lines leaking.
    if type(value) is not str or len(value) != 36:
        return None
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


def classify(path, params):
    """Pinned R11 USD-M public endpoint table, not server charged weight.

    Unknown endpoints/limits are null. Omitted kline limit is deliberately
    unknown rather than assuming a server default. Params are never retained.
    """
    if path == '/fapi/v1/exchangeInfo':
        return 'EXCHANGE_INFO', 1
    if path == '/fapi/v1/openInterest':
        return 'OPEN_INTEREST', 1
    if path == '/fapi/v1/klines':
        limit = bounded_int(params.get('limit'), 1500)
        weight = (1 if limit < 100 else 2 if limit < 500 else 5 if limit <= 1000 else 10) if limit else None
        return 'KLINES', weight
    return 'UNKNOWN', None


class RestTelemetry:
    """Finite capture, drop-new at capacity; partial coverage stays explicit.

    Generation UUID is local recorder identity, not proof of OS start time.
    Parent PID alone is not a supervisor generation. Optional supervisor UUID
    is caller-declared and never promoted to verified supervisor ownership.
    No supervisor changes or automatic export/activation are performed here.
    """
    def __init__(self, *, capacity=MAX_RECORDS, monotonic_ns=time.perf_counter_ns,
                 utc_ns=time.time_ns, sender_generation=None,
                 supervisor_generation=None, pid=None, parent_pid=None):
        if type(capacity) is not int or not 1 <= capacity <= MAX_RECORDS:
            raise ValueError('Capacity outside bounded contract')
        self.capacity = capacity
        self._mono, self._utc = monotonic_ns, utc_ns
        self.sender_generation = generation_token(sender_generation) if sender_generation is not None else str(uuid.uuid4())
        if self.sender_generation is None:
            raise ValueError('Sender generation must be a UUID')
        self.supervisor_generation = generation_token(supervisor_generation)
        self.pid = bounded_int(os.getpid() if pid is None else pid)
        self.parent_pid = bounded_int(os.getppid() if parent_pid is None else parent_pid)
        self.records = []
        self.dropped = self.failures = self.clock_anomalies = 0
        self._active = self.maximum_concurrency = 0
        self._last_mono = self._last_utc = None
        self._previous_start = None
        self._disabled = False

    def _stamp(self):
        mono, utc = self._mono(), self._utc()
        mono, utc = bounded_int(mono), bounded_int(utc)
        if mono is None or utc is None:
            self.clock_anomalies = min(MAX_COUNTER, self.clock_anomalies + 1)
            return None, None
        if ((self._last_mono is not None and mono < self._last_mono) or
                (self._last_utc is not None and utc < self._last_utc)):
            self.clock_anomalies = min(MAX_COUNTER, self.clock_anomalies + 1)
        self._last_mono, self._last_utc = mono, utc
        return mono, utc

    def _failed(self):
        self.failures = min(MAX_COUNTER, self.failures + 1)
        self._disabled = True

    def begin(self, path, params, request_class, attempt, reconnect=False):
        try:
            if self._disabled or len(self.records) >= self.capacity:
                self.dropped = min(MAX_COUNTER, self.dropped + 1)
                return None
            endpoint, weight = classify(path, params)
            mono, utc = self._stamp()
            gap = mono - self._previous_start if mono is not None and self._previous_start is not None else None
            self._previous_start = mono
            record = dict(sequence=len(self.records)+1, method='GET', endpoint=endpoint,
                          documented_request_weight=weight, request_class=request_class if request_class in CLASSES else 'UNKNOWN',
                          attempt=bounded_int(attempt, 5), retry=type(attempt) is int and attempt > 0,
                          reconnect=reconnect is True, initiation_mono_ns=mono, initiation_utc_ns=utc,
                          initiation_gap_ns=gap, response_mono_ns=None, response_utc_ns=None,
                          finish_mono_ns=None, finish_utc_ns=None, status=None,
                          used_weight={name: None for name in HEADER_NAMES},
                          header_state={name: 'UNAVAILABLE' for name in HEADER_NAMES},
                          retry_after_seconds=None, cooldown_seconds=None,
                          response_seen=False, finished=False,
                          boundary='BEFORE_SESSION_GET_NOT_WIRE_SEND')
            self.records.append(record)
            self._active += 1
            self.maximum_concurrency = max(self.maximum_concurrency, self._active)
            return len(self.records)-1
        except Exception:
            self._failed()
            return None

    def response(self, token, status, headers, cooldown):
        try:
            if token is None or self._disabled:
                return
            record = self.records[token]
            mono, utc = self._stamp()
            record.update(response_mono_ns=mono, response_utc_ns=utc,
                          status=bounded_int(status, 599), response_seen=True)
            # Fixed allowlist: no URLs, params, body, exception text or other
            # headers enter the buffer. Malformed values are never stored raw.
            for name in HEADER_NAMES:
                value = headers.get(name)
                if value is None:
                    value = headers.get(name.lower())
                parsed = bounded_int(value)
                record['used_weight'][name] = parsed
                record['header_state'][name] = 'PRESENT' if parsed is not None else 'UNAVAILABLE' if value is None else 'INVALID'
            value = headers.get('Retry-After')
            if value is None:
                value = headers.get('retry-after')
            record['retry_after_seconds'] = bounded_int(value)
            if type(cooldown) in (int, float) and 0 <= cooldown <= MAX_COUNTER:
                record['cooldown_seconds'] = cooldown
        except Exception:
            self._failed()

    def finish(self, token):
        try:
            if token is None:
                return
            record = self.records[token]
            if not record['finished']:
                mono, utc = self._stamp()
                record.update(finish_mono_ns=mono, finish_utc_ns=utc, finished=True)
                self._active -= 1
        except Exception:
            self._failed()

    def snapshot(self):
        """Explicit OFF-path read; no export or filesystem side effects."""
        import copy
        return dict(schema='WSRTD.RestTelemetry.v1', sender_generation=self.sender_generation,
                    supervisor_generation=self.supervisor_generation,
                    supervisor_generation_confidence='CALLER_DECLARED' if self.supervisor_generation else 'UNAVAILABLE',
                    pid=self.pid, parent_pid=self.parent_pid, capacity=self.capacity,
                    dropped=self.dropped, failures=self.failures, sender_observer_failures=0,
                    clock_anomalies=self.clock_anomalies,
                    maximum_concurrency=self.maximum_concurrency,
                    records=copy.deepcopy(self.records), external_shared_ip_usage=None,
                    external_shared_ip_confidence='UNACCOUNTED_FOR')


def summarize(snapshots):
    """OFF-path finite-generation observed accounting; no capacity verdict.

    Uses UTC minute buckets only if clocks are sound. Arrival headers are
    samples and are never summed or subtracted to estimate outside consumers.
    Rolling intervals across processes are deliberately NOT_PROVEN.
    """
    if type(snapshots) not in (list, tuple) or len(snapshots) > MAX_GENERATIONS:
        raise ValueError('At most 32 finite snapshots per aggregation')
    generations, all_records, seen = [], [], set()
    complete = True
    clocks_valid = True
    for snapshot in snapshots:
        generation = snapshot['sender_generation']
        if generation in seen:
            raise ValueError('Duplicate generation would double count requests')
        seen.add(generation)
        records = snapshot['records']
        if len(records) > MAX_RECORDS:
            raise ValueError('Record bound exceeded')
        known = [r['documented_request_weight'] for r in records if r['documented_request_weight'] is not None]
        missing = len(records)-len(known)
        good = not any(snapshot[k] for k in ('dropped', 'failures', 'sender_observer_failures', 'clock_anomalies')) and not missing and all(r['finished'] for r in records)
        complete = complete and good
        clocks_valid = clocks_valid and not snapshot['clock_anomalies']
        generations.append(dict(sender_generation=generation, supervisor_generation=snapshot['supervisor_generation'],
                                requests_recorded=len(records), known_documented_weight=sum(known),
                                unknown_weight_requests=missing, dropped=snapshot['dropped'],
                                failures=snapshot['failures'], clock_anomalies=snapshot['clock_anomalies'],
                                sender_observer_failures=snapshot['sender_observer_failures'],
                                missing_response_count=sum(not r['response_seen'] for r in records),
                                missing_used_weight_1m_count=sum(r['used_weight']['X-MBX-USED-WEIGHT-1M'] is None for r in records),
                                maximum_concurrency=snapshot['maximum_concurrency'],
                                confidence='COMPLETE_LOCAL_CAPTURE' if good else 'INCOMPLETE_LOCAL_CAPTURE'))
        all_records.extend(records)
    buckets = None
    if clocks_valid and all(r['initiation_utc_ns'] is not None for r in all_records):
        buckets = {}
        for r in all_records:
            key = str(r['initiation_utc_ns']//60_000_000_000)
            bucket = buckets.setdefault(key, dict(requests_recorded=0, known_documented_weight=0, unknown_weight_requests=0))
            bucket['requests_recorded'] += 1
            if r['documented_request_weight'] is None:
                bucket['unknown_weight_requests'] += 1
            else:
                bucket['known_documented_weight'] += r['documented_request_weight']
    return dict(generations=generations, requests_recorded=len(all_records),
                known_documented_weight=sum(g['known_documented_weight'] for g in generations),
                confidence='COMPLETE_LOCAL_CAPTURE' if complete and snapshots else 'INCOMPLETE_LOCAL_CAPTURE',
                utc_minute_buckets=buckets, bucket_alignment='LOCAL_UTC_NOT_VERIFIED_EXCHANGE_CLOCK',
                aggregate_rolling_peak=None, maximum_concurrency_across_processes=None,
                measured_charged_request_weight=None, effective_ip_limit=None,
                external_shared_ip_usage=None, external_shared_ip_confidence='UNACCOUNTED_FOR',
                safe_remaining_headroom=None, concurrent_test_readiness=False,
                limitations='Counts describe captured API initiations, not wire arrivals, complete process lifetimes, or external IP usage.')
