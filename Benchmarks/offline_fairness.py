"""Deterministic in-memory experiments against Sender.output/rest/history_range.

Only this harness selects candidate job order. No sockets or live endpoints.
Fixture OHLCV are explicitly artificial test values, never runtime repairs.
"""
import asyncio
from collections import Counter
import hashlib
import heapq
import importlib.util
import json
import logging
import math
from pathlib import Path
import statistics
from types import SimpleNamespace
from unittest.mock import patch

from Binance import sender as production
from Binance.diagnostics import Diagnostics
from Benchmarks.reference_oracle import ReferenceFixture, DeliveryOracle

BOUNDARY = 1791763200
STRATEGIES = ('BASELINE', 'CANDIDATE_A', 'CANDIDATE_B', 'CANDIDATE_C')
SCENARIOS = (
    'A_NORMAL_500', 'B_SHARD2_STALE_100', 'C_TWO_DAILY_BATCHES',
    'D_MIDNIGHT_RECHECK_500', 'E_LOST_FINAL', 'F_RECONNECT',
    'G_SLOW_REST', 'H_429', 'I_418', 'J_ZERO_TRADE',
    'K_MISSING_MINUTES', 'L_NATIVE_PRELOAD', 'M_CONTINUOUS_MINUTES',
    'N_OUTPUT_DELAY', 'O_NO_OBSERVED_ADVANCE',
)


class Clock:
    def __init__(self, start):
        self.now = start
        self.origin = start
        self.sleepers = []
        self.sequence = 0
        self.helpers = set()
        self.unowned = set()
        self.max_ready_turns = 100000

    def time(self):
        return self.now

    def monotonic(self):
        return self.now - self.origin + 1000

    def time_ns(self):
        return int(self.now * 1e9)

    def perf_counter_ns(self):
        # Integer API for the real sender's pacing gate; same virtual domain.
        return round(self.monotonic() * 1_000_000_000)

    async def sleep(self, delay):
        if delay <= 0:
            await asyncio.sleep(0)
            return
        future = asyncio.get_running_loop().create_future()
        self.sequence += 1
        # A positive sub-ULP delay must advance the float-backed fixture clock.
        deadline = self.now + delay
        if deadline <= self.now:
            deadline = math.nextafter(self.now, math.inf)
        heapq.heappush(self.sleepers, (deadline, self.sequence, future))
        await future

    async def drive(self, tasks, done, limit=2400):
        loop = asyncio.get_running_loop()
        previous_factory = loop.get_task_factory()
        def factory(loop, coro, **kwargs):
            task = (previous_factory(loop, coro, **kwargs) if previous_factory else
                    asyncio.Task(coro, loop=loop, **kwargs))
            self.unowned.add(task)
            return task
        loop.set_task_factory(factory)
        try:
            return await self._drive(tasks, done, limit)
        finally:
            loop.set_task_factory(previous_factory)
            # Even rejected task creation must not leak into another fixture.
            for task in self.unowned:
                if not task.done(): task.cancel()
            await asyncio.gather(*self.unowned, return_exceptions=True)
            self.unowned.clear()

    async def _drive(self, tasks, done, limit):
        # CPython asyncio's ready deque is the synchronization boundary. The
        # driver is executing (not queued) at the check. Drain callbacks, task
        # wakeups and sleep(0) chains until no other eligible work remains.
        loop = asyncio.get_running_loop()
        if not hasattr(loop, '_ready'):
            raise RuntimeError('Unsupported event loop: no ready-queue barrier')
        owner = asyncio.current_task()
        turns = 0
        while self.now - self.origin <= limit:
            while True:
                await asyncio.sleep(0)
                turns += 1
                unknown = asyncio.all_tasks() - {owner} - set(tasks) - self.helpers
                if unknown or self.unowned:
                    raise AssertionError('Unobserved tasks in virtual experiment')
                if any(not h.cancelled() for h in loop._scheduled):
                    raise AssertionError('Wall-clock timers are outside the virtual clock')
                if not any(not h.cancelled() for h in loop._ready):
                    break
                if turns > self.max_ready_turns:
                    raise AssertionError('Runnable work never reached quiescence')
            turns = 0
            for task in tasks:
                if task.done() and not task.cancelled() and task.exception():
                    raise task.exception()
            if done():
                return True
            while self.sleepers and self.sleepers[0][2].done():
                heapq.heappop(self.sleepers)
            if not self.sleepers:
                raise AssertionError('Virtual scheduler deadlock')
            self.now = self.sleepers[0][0]
            while self.sleepers and self.sleepers[0][0] <= self.now:
                _, _, future = heapq.heappop(self.sleepers)
                if not future.done():
                    future.set_result(None)
        return False

    async def wait_for(self, awaitable, timeout):
        task = asyncio.ensure_future(awaitable)
        timer = asyncio.create_task(self.sleep(timeout))
        self.helpers.update((task, timer))
        self.unowned.difference_update((task, timer))
        try:
            finished, _ = await asyncio.wait((task, timer), return_when=asyncio.FIRST_COMPLETED)
            if task in finished:
                return await task
            raise TimeoutError('Virtual delivery timeout')
        finally:
            for child in (task, timer):
                if not child.done(): child.cancel()
            await asyncio.gather(task, timer, return_exceptions=True)
            self.helpers.difference_update((task, timer))


async def direct_wait(awaitable, timeout):
    # Fixtures bound delays below transport timeout. Timeout behavior is covered
    # by the existing transport tests; this does not use wall-clock timers.
    return await awaitable


def fake_event(symbol, stamp, closed=False, volume='17'):
    return dict(e='kline', s=symbol, E=stamp+1000,
                k=dict(i='1m', t=stamp, T=stamp+59999, x=closed,
                       o='10', h='12', l='9', c='11', v=volume))


def fixture_row(stamp, step, zero=False):
    return [stamp, '10', '12', '9', '11', '0' if zero else '17',
            stamp+step-1, '0' if zero else '187', 0 if zero else 3]


class FakeREST:
    def __init__(self, clock, latency=.075, throttle=None, zero=False):
        self.clock, self.latency = clock, latency
        self.throttle, self.zero = throttle, zero
        self.calls = []
        self.active = self.max_active = 0
        self.oracle = None

    def get(self, url, params):
        if url != 'memory://fixtures/fapi/v1/klines':
            raise AssertionError('Offline fixture endpoint required')
        owner = self
        call = dict(start=self.clock.time(), params=dict(params))
        self.calls.append(call)
        class Response:
            status = owner.throttle if len(owner.calls) == 1 and owner.throttle else 200
            headers = {'Retry-After': '2'}

            async def __aenter__(self):
                owner.active += 1
                owner.max_active = max(owner.active, owner.max_active)
                await owner.clock.sleep(owner.latency)
                call['response'] = owner.clock.time()
                call['status'] = self.status
                return self

            async def __aexit__(self, *args):
                call['end'] = owner.clock.time()
                owner.active -= 1

            def raise_for_status(self):
                if self.status != 200:
                    raise RuntimeError('Fixture failure')

            async def json(self):
                if owner.oracle is not None:
                    owner.oracle.authorize(params)
                step = 60000 if params['interval'] == '1m' else 86400000
                return [fixture_row(t, step, owner.zero) for t in
                        list(range(params['startTime'], params['endTime']+1, step))[:params['limit']]]
        return Response()


class FakeRelay:
    def __init__(self, clock, delay=0, zero=False):
        self.clock, self.delay = clock, delay
        self.history = {}
        self.expected = {}
        self.live = {}
        self.history_sends = []
        self.live_sends = []
        self.ordered = True
        self.exact = True
        self.duplicates = 0
        self.oracle = DeliveryOracle(ReferenceFixture(zero))

    async def send(self, raw):
        data = json.loads(raw)
        if self.delay:
            await self.clock.sleep(self.delay)
        now = self.clock.time()
        if isinstance(data, list):
            for row in data:
                self.live[row['n']] = (now, row)
            self.live_sends.append(now)
        elif 'hist' in data:
            self.exact &= self.oracle.receive(data)
            interval = '1m' if data['format'] == 'dtohlcv' else '1d'
            previous = None
            for bar in data['bars']:
                key = (data['hist'], interval, *bar[:2 if interval == '1m' else 1])
                timestamp = tuple(bar[:2 if interval == '1m' else 1])
                self.ordered &= previous is None or timestamp > previous
                previous = timestamp
                if key in self.history:
                    self.duplicates += 1  # repeated upserts, not duplicate stored candles
                self.history[key] = bar
            self.history_sends.append((now, data['hist'], interval, len(data['bars'])))


def experiment_sender(module, strategy, clock, rest, relay, diag, native=False):
    class Experiment(module.Sender):
        def __init__(self):
            args = SimpleNamespace(batch_size=100, flush_ms=250, native_history=native,
                                   history_days=1, rest='memory://fixtures', quotes=True,
                                   shard_size=100)
            if module is production:
                super().__init__(args, rest, diagnostics=diag)
            else:
                super().__init__(args, rest)
            self.births = {}
            self.waits = {'1m': [], '1d': []}
            self.jobs_completed = Counter()
            self.queue_max = 0
            self.oldest = 0
            self.minute_streak = 0
            self.dispatches = []
            self.injection_done = False
            self.required = set()
            self.bar_cap_count = 0
            self.oldest_by_interval = {'1m': 0, '1d': 0}
            self.first_wait = {}

        def select_repair(self, eligible):
            if strategy == 'IMPLEMENTED':
                return super().select_repair(eligible)
            # Reference candidates choose order in the harness. IMPLEMENTED
            # calls the actual sender's policy without reordering its queue.
            return eligible[0] if eligible else None

        def queue_repair(self, symbol, interval, start, end, classification=None):
            key = symbol, interval
            new = key not in self.repairs and start < end
            if module is production:
                super().queue_repair(symbol, interval, start, end, classification)
            else:
                super().queue_repair(symbol, interval, start, end)
            if new:
                self.births[key] = clock.monotonic()
            self.queue_max = max(self.queue_max, len(self.repairs))
            if len(self.repairs) > 1000:
                raise AssertionError('500-symbol two-interval queue bound exceeded')
            step = 60000 if interval == '1m' else 86400000
            # Record actual bounded obligations, not invented historical deliveries.
            count = 300 if interval == '1d' else 1500 if native else self.args.history_days*1440
            bounded_start = max(start, end-count*step)
            if start < bounded_start:
                self.bar_cap_count += 1
            self.required.update((symbol, interval, t) for t in range(bounded_start, end, step))

        async def repair_one(self, ws):
            return await self.measured_dispatch(ws, super().repair_one)

        async def repair_step(self, ws):
            return await self.measured_dispatch(ws, super().repair_step)

        async def measured_dispatch(self, ws, dispatch):
            now = clock.monotonic()
            for key, born in self.births.items():
                self.oldest_by_interval[key[1]] = max(self.oldest_by_interval[key[1]], now-born)
            eligible = [k for k in self.repairs if self.retry_after.get(k, 0) <= clock.monotonic()]
            if not eligible:
                return await dispatch(ws)
            self.oldest = max(self.oldest, *(now-self.births[k] for k in self.births))
            minutes = [k for k in eligible if k[1] == '1m']
            days = [k for k in eligible if k[1] == '1d']
            if strategy == 'BASELINE':
                chosen = eligible[0]
            elif strategy == 'IMPLEMENTED':
                chosen = super().select_repair(eligible)
            elif strategy == 'CANDIDATE_A':
                chosen = (days[0] if days and self.minute_streak >= 8 else
                          minutes[0] if minutes else days[0])
            elif strategy == 'CANDIDATE_B':
                chosen = (days[0] if days and self.minute_streak >= 3 else
                          minutes[0] if minutes else days[0])
            else:
                aged = [k for k in eligible if now-self.births[k] >= 30]
                chosen = min(aged, key=lambda k:self.births[k]) if aged else (minutes or days)[0]
            if strategy not in ('BASELINE', 'IMPLEMENTED'):
                # Experimental order only, in the harness subclass. Underlying
                # production selection, REST, history and output remain intact.
                self.repairs = {chosen:self.repairs[chosen],
                                **{k:v for k,v in self.repairs.items() if k != chosen}}
            self.minute_streak = self.minute_streak+1 if chosen[1] == '1m' else 0
            wait = now-self.births[chosen]
            self.first_wait.setdefault(chosen, wait)
            self.dispatches.append((clock.time(), chosen, self.repairs[chosen]))
            result = await dispatch(ws)
            if chosen not in self.repairs:
                self.waits[chosen[1]].append(self.first_wait.pop(chosen))
                self.births.pop(chosen, None)
                self.jobs_completed[chosen[1]] += 1
            return result
    return Experiment()


def distribution(values):
    if not values:
        return dict(count=0, median=None, p95=None, max=None)
    ordered = sorted(values)
    return dict(count=len(values), median=statistics.median(values),
                p95=ordered[math.ceil(.95*len(ordered))-1], max=max(values))


async def run_case(scenario, strategy='BASELINE', module=production):
    clock = Clock(BOUNDARY+59 if scenario == 'D_MIDNIGHT_RECHECK_500' else BOUNDARY+600)
    native = scenario in ('B_SHARD2_STALE_100', 'D_MIDNIGHT_RECHECK_500', 'L_NATIVE_PRELOAD')
    rest = FakeREST(clock, latency=2 if scenario == 'G_SLOW_REST' else .075,
                    throttle=429 if scenario == 'H_429' else 418 if scenario == 'I_418' else None,
                    zero=scenario == 'J_ZERO_TRADE')
    relay = FakeRelay(clock, delay=.4 if scenario == 'N_OUTPUT_DELAY' else 0, zero=rest.zero)
    rest.oracle = relay.oracle
    diag = Diagnostics(65536, clock)
    proxy = SimpleNamespace(**{name:getattr(asyncio, name) for name in dir(asyncio) if not name.startswith('__')})
    proxy.sleep, proxy.wait_for = clock.sleep, clock.wait_for
    symbols = [f'S{i:03}USDT' for i in range(500)]
    with patch.object(module, 'time', clock), patch.object(module, 'asyncio', proxy):
        sender = experiment_sender(module, strategy, clock, rest, relay, diag, native)
        # Only preload scenario exercises output's startup queue. Other native
        # scenarios enter output with no symbols, then install the already-loaded
        # fixture universe after its initial iteration.
        sender.symbols = symbols[:1] if scenario == 'L_NATIVE_PRELOAD' else []
        last_closed = int(clock.time()//60)*60000-60000
        for s in symbols:
            sender.buffer.ingest(fake_event(s, last_closed+60000))
        shard_keys = {s: diag.shard(i//100+1, set(symbols[i//100*100:(i//100+1)*100]), False)
                      for i,s in enumerate(symbols)}
        output = asyncio.create_task(sender.output(relay))
        live = asyncio.create_task(sender.live_output(relay))

        async def healthy_events():
            # Maintain the explicitly healthy shards in long-running fixtures.
            # Omitting this would accidentally turn midnight contention into an
            # unlimited all-500 market outage, a different overload experiment.
            while True:
                await clock.sleep(10)
                opened = int(clock.time()//60)*60000
                for s in symbols:
                    if scenario == 'B_SHARD2_STALE_100' and s in symbols[100:200]:
                        continue
                    old = sender.buffer.seen.get(s)
                    if old and old[0] < opened:
                        final = fake_event(s, old[0], True)
                        final['E'] = old[0]+59999
                        sender.ingest(final, shard_keys[s]) if module is production else sender.ingest(final)
                    event = fake_event(s, opened)
                    sender.ingest(event, shard_keys[s]) if module is production else sender.ingest(event)

        def queue(s, interval='1m', count=1, classification='MINUTE_GAP'):
            step = 60000 if interval == '1m' else 86400000
            stop = int(clock.time()*1000)//step*step
            sender.queue_repair(s, interval, stop-count*step, stop, classification)

        async def inject():
            await clock.sleep(.01)
            sender.symbols = symbols
            sender.daily_through = {s:BOUNDARY*1000 for s in symbols}
            sender.daily_rechecked = dict(sender.daily_through)
            if scenario == 'A_NORMAL_500':
                for s in symbols:
                    sender.ingest(fake_event(s, last_closed+60000, True))
                await clock.sleep(65)
            elif scenario == 'B_SHARD2_STALE_100':
                for s in symbols[100:200]:
                    sender.buffer.seen.pop(s, None)
                    sender.buffer.ingest(fake_event(s,last_closed-120000,True))
                # Actual per-symbol stale scheduler, not a hand-written queue.
                sender.schedule_stale_repairs()
            elif scenario in ('C_TWO_DAILY_BATCHES', 'M_CONTINUOUS_MINUTES'):
                for s in symbols:
                    queue(s, '1d', classification='DAILY_ROLLOVER')
                if scenario == 'C_TWO_DAILY_BATCHES':
                    await clock.sleep(1)
                    for s in symbols[100:200]: queue(s)
                    await clock.sleep(300)
                    for s in symbols: queue(s, '1d', classification='DAILY_RECHECK')
                    await clock.sleep(1)
                    for s in symbols[100:200]: queue(s)
                else:
                    for cycle in range(120):
                        # Distinct symbols give equal required jobs across
                        # schedulers; repeatedly requesting the same completed
                        # candle would measure redundant requests/coalescing.
                        for s in symbols[cycle*4:(cycle+1)*4]: queue(s)
                        await clock.sleep(1)
            elif scenario == 'D_MIDNIGHT_RECHECK_500':
                sender.daily_through = {s:(BOUNDARY-86400)*1000 for s in symbols}
                sender.daily_rechecked = dict(sender.daily_through)
                await clock.sleep(2)
                for s in symbols[100:200]: queue(s)
                await clock.sleep(245)
            elif scenario == 'E_LOST_FINAL':
                sender.ingest(fake_event(symbols[0], last_closed+120000))
            elif scenario == 'F_RECONNECT':
                for s in symbols[100:200]:
                    sender.buffer.seen[s] = (last_closed-60000, 1, False)
                sender.repair_shard(symbols[100:200])
            elif scenario == 'K_MISSING_MINUTES':
                queue(symbols[0], count=5)
            elif scenario == 'L_NATIVE_PRELOAD':
                for s in symbols[100:110]: queue(s)
            elif scenario == 'O_NO_OBSERVED_ADVANCE':
                # Sender already holds a newer live bar. Historical repair
                # must not replace it or emit an older live snapshot.
                sender.buffer.ingest(fake_event(symbols[0], last_closed+60000))
                queue(symbols[0], count=2)
            else:
                for s in symbols[100:110]: queue(s)
            sender.injection_done = True

        injection = asyncio.create_task(inject())
        def done():
            preload_done = scenario != 'L_NATIVE_PRELOAD' or any(
                i == '1d' and n == 300 for _, _, i, n in relay.history_sends)
            recheck_done = scenario != 'D_MIDNIGHT_RECHECK_500' or all(
                sender.daily_rechecked.get(s) == BOUNDARY*1000 for s in symbols)
            return sender.injection_done and not sender.repairs and preload_done and recheck_done
        producer = asyncio.create_task(healthy_events())
        tasks = [output, live, injection, producer]
        try:
            completed = await clock.drive(tasks, done)
            # Drain any last real finalized live snapshot without advancing time.
            if not relay.delay:
                await sender.flush(relay)
        finally:
            for task in tasks: task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if clock.helpers or (asyncio.all_tasks() - {asyncio.current_task()}):
                raise AssertionError('Unaccounted tasks after fixture shutdown')
        # Reconstruct expected OHLCV keys using the same public protocol encoder,
        # but compare every value against the independent fixed REST fixture.
        expected_keys = set()
        for symbol, interval, stamp in sender.required:
            key = relay.oracle.reference.key(symbol, interval, stamp)
            expected_keys.add(key)
        spacing = [b['start']-a['start'] for a,b in zip(rest.calls, rest.calls[1:])]
        cooldown = []
        for i,c in enumerate(rest.calls[:-1]):
            if c['status'] in (429,418):
                cooldown.append(dict(status=c['status'], required=60 if c['status']==418 else 2,
                                     actual=rest.calls[i+1]['start']-c['response']))
        obligations = {i:sum(k[1]==i for k in expected_keys) for i in ('1m','1d')}
        missing = expected_keys-set(relay.history)
        snapshot = diag.snapshot()
        details = {'scenario':scenario, 'strategy':strategy, 'completed':completed,
            'virtual_seconds':clock.now-clock.origin, 'minute_wait':distribution(sender.waits['1m']),
            'daily_wait':distribution(sender.waits['1d']), 'max_queue_depth':sender.queue_max,
            'oldest_dispatched_queue_age':sender.oldest, 'rest_request_count':len(rest.calls),
            'rest_min_spacing':min(spacing) if spacing else None, 'rest_max_concurrency':rest.max_active,
            'cooldowns':cooldown, 'retry_count':sum(c['status']!=200 for c in rest.calls),
            'required_finalized_bars':obligations, 'missing_finalized_bars':len(missing),
            'daily_eventual_completion':completed and not any(k[1]=='1d' for k in missing),
            'closed_minute_completeness':not any(k[1]=='1m' for k in missing),
            'stored_unique_bars':len(relay.history), 'repeated_history_upserts':relay.duplicates,
            'within_page_ordering':relay.ordered, 'exact_fixture_ohlcv':relay.exact,
            'retention_clamps':sender.bar_cap_count, 'jobs_completed':dict(sender.jobs_completed),
            'diagnostic_errors':diag.errors, 'diagnostic_records_overwritten':diag.overwritten,
            'history_digest':hashlib.sha256(json.dumps(sorted(relay.history.items()),sort_keys=True).encode()).hexdigest(),
            'rest_trace_digest':hashlib.sha256(json.dumps(rest.calls,sort_keys=True).encode()).hexdigest(),
            'first_minute_dispatch_utc':next((t for t,k,_ in sender.dispatches if k[1]=='1m'),None),
            'first_daily_dispatch_utc':next((t for t,k,_ in sender.dispatches if k[1]=='1d'),None),
            'diagnostic_classifications':sorted({c for rec in snapshot['records'] for c in rec.get('classifications',[])})}
        details['oracle'] = dict(expected_frames=relay.oracle.expected_frames,
                                validated_frames=relay.oracle.validated_frames,
                                rejected_frames=relay.oracle.rejected_frames,
                                pending_frames=len(relay.oracle.pending))
        details['pending_tasks_after_shutdown'] = 0
        details['max_pending_age_by_interval'] = sender.oldest_by_interval
        details['pending_jobs_at_test_end'] = len(sender.repairs)
        checks = dict(completed=completed, bounded_queue=sender.queue_max<=1000,
                      single_rest=rest.max_active<=1, spacing=not spacing or min(spacing)>=.25-1e-6,
                      cooldown=all(c['actual']>=c['required']-1e-6 for c in cooldown),
                      complete=not missing, daily_progress=details['daily_eventual_completion'],
                      ordering=relay.ordered, exact_ohlcv=relay.exact and relay.oracle.complete, diagnostics=diag.errors==0)
        details['checks']=checks
        details['verdict']='PASS' if all(checks.values()) else 'FAIL'
        # Detailed traces are per finite fixture and saved explicitly by the runner.
        trace = dict(rest=rest.calls, dispatches=sender.dispatches,
                     history_sends=relay.history_sends, live_sends=relay.live_sends,
                     diagnostic_snapshot=snapshot)
        return details, trace


async def compare(output):
    output.mkdir(parents=True, exist_ok=True)
    results=[]
    for scenario in SCENARIOS:
        for strategy in STRATEGIES:
            result, trace=await run_case(scenario,strategy)
            results.append(result)
            (output/(scenario+'-'+strategy+'.json')).write_text(json.dumps(trace,indent=2)+'\n')
    return results


if __name__ == '__main__':
    import sys
    from Benchmarks.run_offline_tests import network_audit
    sys.addaudithook(network_audit)
    logging.disable(logging.CRITICAL)
    output=Path(__file__).parents[1]/'evidence'/'offline-traces'
    results=asyncio.run(compare(output))
    (output.parent/'FAIRNESS_RAW_RESULTS.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps({'experiments':len(results),'passed':sum(r['verdict']=='PASS' for r in results),
                      'failed':[r['scenario']+':'+r['strategy'] for r in results if r['verdict']!='PASS']}))
    raise SystemExit(0 if all(r['verdict']=='PASS' for r in results) else 1)
