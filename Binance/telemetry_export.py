"""Optional finite snapshot exporter. All filesystem work runs on one daemon.

Startup only; no hot reload. Each output directory must be absent. Retention
is a finite prefix (no deletion/reuse). Snapshots are cumulative: never sum
successive snapshots of one generation. Caller clocks are trusted test hooks.
"""
import asyncio
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import queue
import threading
import time
import uuid
from dataclasses import dataclass

if __package__:
    from Binance.rest_telemetry import RestTelemetry, generation_token, MAX_COUNTER, HEADER_NAMES, CLASSES
else:
    from rest_telemetry import RestTelemetry, generation_token, MAX_COUNTER, HEADER_NAMES, CLASSES

SCHEMA = 'WSRTD.RestExport.v1'
MAX_FILE_BYTES = 16 * 1024 * 1024
RECORD_KEYS = frozenset(('sequence method endpoint documented_request_weight request_class attempt retry reconnect initiation_mono_ns initiation_utc_ns initiation_gap_ns response_mono_ns response_utc_ns finish_mono_ns finish_utc_ns status used_weight header_state retry_after_seconds cooldown_seconds response_seen finished boundary').split())
SNAPSHOT_KEYS = frozenset(('schema sender_generation supervisor_generation supervisor_generation_confidence pid parent_pid capacity dropped failures sender_observer_failures clock_anomalies maximum_concurrency records external_shared_ip_usage external_shared_ip_confidence').split())


def number(value, *, nullable=False, signed=False, floating=False):
    return ((value is None and nullable) or
            (type(value) in ((int, float) if floating else (int,)) and
             (-MAX_COUNTER if signed else 0) <= value <= MAX_COUNTER and math.isfinite(value)))


def validate_snapshot(s):
    """Strict finite whitelist. Reject rather than export unknown raw fields."""
    if type(s) is not dict or set(s) != SNAPSHOT_KEYS or s['schema'] != 'WSRTD.RestTelemetry.v1':
        raise ValueError('Invalid snapshot schema')
    if s['sender_generation'] is None or generation_token(s['sender_generation']) != s['sender_generation']:
        raise ValueError('Invalid generation')
    sup = s['supervisor_generation']
    if sup is not None and generation_token(sup) != sup:
        raise ValueError('Invalid supervisor generation')
    if s['supervisor_generation_confidence'] != ('CALLER_DECLARED' if sup else 'UNAVAILABLE'):
        raise ValueError('Invalid supervisor confidence')
    if s['external_shared_ip_usage'] is not None or s['external_shared_ip_confidence'] != 'UNACCOUNTED_FOR':
        raise ValueError('Invalid shared IP claim')
    for key in ('pid','parent_pid'):
        if not number(s[key],nullable=True): raise ValueError('Invalid process field')
    for key in ('capacity','dropped','failures','sender_observer_failures','clock_anomalies','maximum_concurrency'):
        if not number(s[key]): raise ValueError('Invalid counter')
    if not 1 <= s['capacity'] <= 4096 or type(s['records']) is not list or len(s['records']) > s['capacity']:
        raise ValueError('Snapshot bound exceeded')
    for i, r in enumerate(s['records'], 1):
        if type(r) is not dict or set(r) != RECORD_KEYS or r['sequence'] != i or type(r['sequence']) is not int:
            raise ValueError('Invalid request record')
        if r['method'] != 'GET' or r['endpoint'] not in ('KLINES','EXCHANGE_INFO','OPEN_INTEREST','UNKNOWN') or r['request_class'] not in CLASSES:
            raise ValueError('Invalid request class')
        if r['boundary'] not in ('BEFORE_SESSION_GET_NOT_WIRE_SEND','BEFORE_HTTP_HANDLER_NOT_WIRE_SEND','BEFORE_SIMULATED_RESPONSE_ENTRY'): raise ValueError('Invalid boundary')
        if r['documented_request_weight'] not in (None,1,2,5,10) or type(r['documented_request_weight']) is bool:
            raise ValueError('Invalid weight')
        for key in ('retry','reconnect','response_seen','finished'):
            if type(r[key]) is not bool: raise ValueError('Invalid flag')
        for key in ('attempt','initiation_mono_ns','initiation_utc_ns','response_mono_ns','response_utc_ns','finish_mono_ns','finish_utc_ns','status','retry_after_seconds'):
            if not number(r[key],nullable=True): raise ValueError('Invalid numeric observation')
        if not number(r['initiation_gap_ns'],nullable=True,signed=True) or not number(r['cooldown_seconds'],nullable=True,floating=True):
            raise ValueError('Invalid timing')
        if type(r['used_weight']) is not dict or type(r['header_state']) is not dict or set(r['used_weight']) != set(HEADER_NAMES) or set(r['header_state']) != set(HEADER_NAMES):
            raise ValueError('Invalid headers')
        for name in HEADER_NAMES:
            if not number(r['used_weight'][name],nullable=True) or r['header_state'][name] not in ('PRESENT','UNAVAILABLE','INVALID'):
                raise ValueError('Invalid header value')
            if (r['used_weight'][name] is not None) != (r['header_state'][name]=='PRESENT'):
                raise ValueError('Inconsistent header')
    return s


@dataclass(frozen=True)
class ExportConfig:
    output: Path
    capacity: int = 4096
    queue_capacity: int = 2
    max_file_bytes: int = 8 * 1024 * 1024
    max_files: int = 32
    cadence: float = 60.0
    drain_seconds: float = 2.0
    duration_seconds: float = 900.0
    sender_generation: str | None = None
    supervisor_generation: str | None = None

    def validate(self):
        for value, lo, hi in ((self.capacity,1,4096),(self.queue_capacity,1,4),(self.max_file_bytes,4096,MAX_FILE_BYTES),(self.max_files,4,32)):
            if type(value) is not int or not lo <= value <= hi: raise ValueError('Invalid telemetry resource bound')
        for value,lo,hi in ((self.cadence,.05,60),(self.drain_seconds,0,10),(self.duration_seconds,.05,900)):
            if type(value) not in (int,float) or not math.isfinite(value) or not lo <= value <= hi: raise ValueError('Invalid telemetry deadline')
        if not self.output.is_absolute(): raise ValueError('Telemetry output must be absolute')
        for value in (self.sender_generation,self.supervisor_generation):
            if value is not None and generation_token(value) != value: raise ValueError('Invalid generation UUID')
        return self


def add_arguments(parser):
    group=parser.add_argument_group('Optional offline-reviewed REST telemetry (startup only)')
    group.add_argument('--rest-telemetry',action='store_true',help='Enable bounded telemetry at startup; disabled by default')
    group.add_argument('--telemetry-output',type=Path)
    group.add_argument('--telemetry-capacity',type=int,default=4096)
    group.add_argument('--telemetry-queue-capacity',type=int,default=2)
    group.add_argument('--telemetry-max-file-bytes',type=int,default=8*1024*1024)
    group.add_argument('--telemetry-max-files',type=int,default=32)
    group.add_argument('--telemetry-flush-seconds',type=float,default=60)
    group.add_argument('--telemetry-drain-seconds',type=float,default=2)
    group.add_argument('--telemetry-duration-seconds',type=float,default=900)
    group.add_argument('--telemetry-generation')
    group.add_argument('--telemetry-supervisor-generation')


def config_from_args(args):
    if not getattr(args,'rest_telemetry',False): return None
    if args.telemetry_output is None: raise ValueError('--telemetry-output required when enabled')
    return ExportConfig(args.telemetry_output,args.telemetry_capacity,args.telemetry_queue_capacity,
                        args.telemetry_max_file_bytes,args.telemetry_max_files,args.telemetry_flush_seconds,
                        args.telemetry_drain_seconds,args.telemetry_duration_seconds,args.telemetry_generation,
                        args.telemetry_supervisor_generation).validate()


class SnapshotExporter:
    def __init__(self, config, recorder, *, wall_ns=time.time_ns, monotonic=time.monotonic):
        self.config=config.validate()
        self.generation=recorder.sender_generation
        self.session=str(uuid.uuid4())
        self.startup_utc_ns=wall_ns()
        self._clock=monotonic
        self._queue=queue.Queue(maxsize=config.queue_capacity)
        self._closing=threading.Event();self._done=threading.Event();self._abort=threading.Event()
        self._thread=None;self._final=None;self._deadline=None
        self.dropped=self.errors=self.retention_dropped=0
        self._files=[];self._bytes=0;self.ack=None
        self._inventory=[]

    def start(self):
        try:
            self._thread=threading.Thread(target=self._worker,name='rest-telemetry-export',daemon=True)
            self._thread.start()
        except Exception:
            self.errors=min(MAX_COUNTER,self.errors+1);self._done.set()

    def submit(self, snapshot):
        # Called by cadence task, never by request initiation/response hooks.
        if self._closing.is_set() or self._done.is_set():
            self.dropped=min(MAX_COUNTER,self.dropped+1);return False
        try:
            self._queue.put_nowait(snapshot);return True
        except queue.Full:
            self.dropped=min(MAX_COUNTER,self.dropped+1);return False
        except Exception:
            self.errors=min(MAX_COUNTER,self.errors+1);return False

    def _write(self, name, value):
        # Only the daemon calls this method; bounded serialization and writes.
        data=(json.dumps(value,separators=(',',':'),allow_nan=False)+'\n').encode('utf-8')
        if len(data)>self.config.max_file_bytes: raise ValueError('Export file bound exceeded')
        target=self.config.output/name;partial=target.with_suffix('.part')
        if target.exists() or partial.exists(): raise FileExistsError('Export collision')
        entries=list(self.config.output.iterdir())
        if len(entries)>=self.config.max_files:raise ValueError('Export file count bound')
        if sum(p.stat().st_size for p in entries)+len(data)>536870912:raise ValueError('Session byte bound')
        if self._abort.is_set():raise RuntimeError('Export aborted')
        with partial.open('xb') as f:
            if f.write(data)!=len(data):raise OSError('Short export write')
            f.flush()
            os.fsync(f.fileno())
        if partial.read_bytes()!=data:raise OSError('Export verification failed')
        if self._abort.is_set() or (name=='ack.json' and self._clock()>=self._deadline):
            raise RuntimeError('Export deadline exceeded')
        # One owned absent destination. Interrupted .part remains evidence.
        partial.rename(target)
        self._bytes+=len(data)
        result=dict(name=name,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
        self._inventory.append(result)
        return result

    def _envelope(self, snapshot):
        validate_snapshot(snapshot)
        if snapshot['sender_generation']!=self.generation: raise ValueError('Generation mismatch')
        return dict(schema=SCHEMA,kind='snapshot',session=self.session,startup_utc_ns=self.startup_utc_ns,
                    weight_provenance='R11_PINNED_DOCUMENTED_ENDPOINT_MODEL_NOT_EXCHANGE_CHARGE',
                    spacing_violations=sum(r['initiation_gap_ns'] is not None and r['initiation_gap_ns']<250000000 for r in snapshot['records'][1:]),
                    queue_loss=self.dropped,export_errors=self.errors,retention_dropped=self.retention_dropped,
                    snapshot=snapshot)

    def _save_snapshot(self,snapshot,final=False):
        # Session, final manifest, ack, and one final snapshot are reserved.
        if len(self._files)>=self.config.max_files-(3 if final else 4):
            self.retention_dropped=min(MAX_COUNTER,self.retention_dropped+1);return
        item=self._write(f'{len(self._files)+1:04d}.json',self._envelope(snapshot));self._files.append(item)

    def _worker(self):
        try:
            # Root exclusive creation prevents every repeat-generation/session
            # invocation from overwriting previous evidence. No mkdir parents.
            self.config.output.mkdir(exist_ok=False)
            self._write('session.json',dict(schema=SCHEMA,kind='session',session=self.session,
                 sender_generation=self.generation,startup_utc_ns=self.startup_utc_ns,
                 status='OPEN_UNACKNOWLEDGED',max_files=self.config.max_files,max_file_bytes=self.config.max_file_bytes))
            while not self._abort.is_set():
                try: snapshot=self._queue.get(timeout=.05)
                except queue.Empty:
                    if self._closing.is_set(): break
                    continue
                self._save_snapshot(snapshot)
                if self._closing.is_set() and self._clock()>=self._deadline: return
            if self._abort.is_set() or self._deadline is None or self._clock()>=self._deadline: return
            self._save_snapshot(self._final,final=True)
            receipt=dict(schema=SCHEMA,kind='final',session=self.session,generation=self.generation,
                         status='WRITER_FINALIZED_REQUIRES_CALLER_ACK',files=self._files,
                         queue_loss=self.dropped,export_errors=self.errors,retention_dropped=self.retention_dropped,
                         final_snapshot_sha256=hashlib.sha256(json.dumps(self._final,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                         capture_incomplete=bool(self._final['dropped'] or self._final['failures'] or self._final['sender_observer_failures'] or self._final['clock_anomalies'] or any(not x['finished'] for x in self._final['records'])),
                         shared_ip_headroom=None)
            final=self._write('final.json',receipt)
            # Authorize publication only while the drain lease remains valid.
            # Filesystem publication already in flight is not cancellable.
            if not self._abort.is_set() and self._clock()<self._deadline:
                for item in self._inventory:
                    if sha_file(self.config.output/item['name'])!=item['sha256']:raise OSError('Readback mismatch')
                complete=not any((receipt['queue_loss'],receipt['export_errors'],receipt['retention_dropped'],receipt['capture_incomplete']))
                ack=dict(EXPORT_GENERATION_ID=self.generation,EXPORT_SESSION_ID=self.session,
                    EXPORT_SCHEMA_VERSION='WSRTD.PersistentAck.v1',EXPORT_FILE_MANIFEST=list(self._inventory),
                    EXPORT_FILE_SHA256=final['sha256'],EXPORTED_RECORD_COUNT=len(self._final['records']),
                    DROPPED_RECORD_COUNT=self._final['dropped'],EXPORT_ERROR_COUNT=self.errors,
                    QUEUE_LOSS_COUNT=self.dropped,RETENTION_DROPPED_COUNT=self.retention_dropped,
                    FILE_WRITE_STATUS='SUCCESS',FILE_CLOSE_STATUS='SUCCESS',OS_FLUSH_STATUS='SUCCESS',
                    CONTENT_VERIFICATION_STATUS='SUCCESS',ACK_PERSISTENCE_STATUS='PUBLISHED_RECORD_REQUIRES_READER_VERIFICATION',
                    EXPORT_COMPLETENESS='COMPLETE' if complete else 'INCOMPLETE',
                    COMPLETION_TIMESTAMP=time.time_ns(),
                    PUBLICATION_AUTHORIZATION_MONOTONIC=self._clock(),SHUTDOWN_DEADLINE_MONOTONIC=self._deadline,
                    COMPLETION_BOUNDARY='VERIFIED_CONTENT_THEN_ATOMIC_ACK_PUBLICATION',
                    DRAIN_SEMANTICS='CALLER_WAIT_BOUND_ONLY_INFLIGHT_FILESYSTEM_OPERATION_NOT_CANCELLABLE',
                    physical_power_loss_durability='NOT_PROVEN')
                self._write('ack.json',ack)
                # Publication is the persistent commit. Never erase a valid
                # commit merely because the caller missed observing it. An OS
                # rename already in flight cannot be atomically cancelled.
                self.ack=dict(session=self.session,generation=self.generation,final_sha256=final['sha256'],acknowledged=True)
        except Exception:
            self.errors=min(MAX_COUNTER,self.errors+1)
        finally:
            self._done.set()

    async def close(self, final_snapshot):
        if not self._closing.is_set():
            self._final=final_snapshot
            self._deadline=self._clock()+self.config.drain_seconds
            self._closing.set()
        try:
            while not self._done.is_set() and self._clock()<self._deadline:
                await asyncio.sleep(min(.01,max(0,self._deadline-self._clock())))
        except BaseException:
            self._abort.set();raise
        if not self._done.is_set(): self._abort.set()
        return dict(ack=self.ack if self._done.is_set() and not self._abort.is_set() else None,
                    complete=bool(self.ack and self._done.is_set() and not self._abort.is_set() and
                                  not (self.dropped or self.errors or self.retention_dropped or
                                       any(self._final[k] for k in ('dropped','failures','sender_observer_failures','clock_anomalies')) or
                                       any(not r['finished'] for r in self._final['records']))),
                    drain_status='OBSERVED_WRITER_EXIT' if self._done.is_set() else 'TIMED_OUT_COMPLETION_UNOBSERVED',
                    persistent_completion='READ_ACK_FROM_DISK_INDEPENDENTLY',
                    errors=self.errors,queue_loss=self.dropped,retention_dropped=self.retention_dropped)


async def run_with_telemetry(sender_class, args, session):
    """Enabled startup integration. Never used by the disabled main branch."""
    config=config_from_args(args)
    try:
        recorder=RestTelemetry(capacity=config.capacity,sender_generation=config.sender_generation,
                               supervisor_generation=config.supervisor_generation)
        exporter=SnapshotExporter(config,recorder)
    except Exception:
        logging.getLogger('binance').warning('REST telemetry initialization failed; capture unavailable')
        return await sender_class(args,session).run()
    sender=sender_class(args,session,rest_telemetry=recorder)
    exporter.start()
    async def observe():
        deadline=time.monotonic()+config.duration_seconds
        try:
            while time.monotonic()<deadline:
                exporter.submit(sender.rest_telemetry_snapshot())
                await asyncio.sleep(min(config.cadence,max(0,deadline-time.monotonic())))
            sender.telemetry_export_receipt=await exporter.close(sender.rest_telemetry_snapshot())
        except Exception:
            exporter.errors=min(MAX_COUNTER,exporter.errors+1)
    coroutine=observe()
    try:
        observer=asyncio.create_task(coroutine)
    except Exception:
        coroutine.close()
        exporter.errors=min(MAX_COUNTER,exporter.errors+1)
        observer=None
    try:
        return await sender.run()
    finally:
        if observer is not None and not exporter._closing.is_set():
            observer.cancel()
        # If the finite observation is already draining, preserve its single
        # bounded deadline instead of cancelling it halfway through final IO.
        if observer is not None:
            await asyncio.gather(observer,return_exceptions=True)
        try:
            sender.telemetry_export_receipt=await exporter.close(sender.rest_telemetry_snapshot())
        except Exception:
            # Telemetry shutdown failure cannot replace feed's result/error.
            sender.telemetry_export_receipt=dict(complete=False,ack=None,errors=1)


def _inspect_legacy_export(directory, acknowledgement=None):
    """Offline bounded verifier. No final file/ack means incomplete, not success."""
    directory=Path(directory)
    result=dict(status='INCOMPLETE',complete=False,shared_ip_headroom=None)
    try:
        def read(name):
            p=directory/name
            if p.is_symlink() or p.stat().st_size>MAX_FILE_BYTES: raise ValueError('Invalid file')
            return json.loads(p.read_text(encoding='utf-8'))
        start=read('session.json');final=read('final.json')
        if start['schema']!=SCHEMA or final['schema']!=SCHEMA or final['session']!=start['session'] or final['generation']!=start['sender_generation']: raise ValueError('Session mismatch')
        files=final['files']
        if type(files) is not list or len(files)>30: raise ValueError('File bound')
        last_snapshot=None
        for i,item in enumerate(files,1):
            if item['name']!=f'{i:04d}.json': raise ValueError('Invalid order/path')
            payload=read(item['name'])
            if sha_file(directory/item['name'])!=item['sha256'] or (directory/item['name']).stat().st_size!=item['bytes']: raise ValueError('File digest mismatch')
            if payload['schema']!=SCHEMA or payload['session']!=start['session']: raise ValueError('Envelope mismatch')
            validate_snapshot(payload['snapshot'])
            if payload['snapshot']['sender_generation']!=final['generation']:raise ValueError('Snapshot generation mismatch')
            last_snapshot=payload['snapshot']
        ack=acknowledgement or {}
        matched=(ack.get('acknowledged') is True and ack.get('session')==final['session'] and ack.get('generation')==final['generation'] and ack.get('final_sha256')==sha_file(directory/'final.json'))
        result['status']='ACKNOWLEDGED_WITH_LOSS' if matched else 'UNACKNOWLEDGED'
        final_present=(last_snapshot is not None and hashlib.sha256(json.dumps(last_snapshot,sort_keys=True,separators=(',',':')).encode()).hexdigest()==final['final_snapshot_sha256'])
        result['complete']=bool(matched and final_present and not any(final[k] for k in ('queue_loss','export_errors','retention_dropped','capture_incomplete')))
        if result['complete']: result['status']='COMPLETE_LOCAL_EXPORT_ONLY'
        return result
    except (OSError,ValueError,KeyError,TypeError): return result


def inspect_export(directory, acknowledgement=None):
    """Read durable acknowledgement after writer exit; never trust caller ack.

    All payloads, metadata and partials count in the resource envelope. The
    receipt attests OS flush calls, not power-loss or native database durability.
    """
    directory=Path(directory)
    bad=dict(status='INCOMPLETE',complete=False,shared_ip_headroom=None)
    try:
        entries=list(directory.iterdir())
        if directory.is_symlink() or not 4<=len(entries)<=32:return bad
        if any(p.is_symlink() or not p.is_file() or p.stat().st_nlink!=1 or
               p.suffix=='.part' or p.stat().st_size>MAX_FILE_BYTES for p in entries):return bad
        if sum(p.stat().st_size for p in entries)>536870912:return bad
        def read(name):return json.loads((directory/name).read_text(encoding='utf-8'))
        ack=read('ack.json');start=read('session.json');final=read('final.json')
        if ack['EXPORT_SCHEMA_VERSION']!='WSRTD.PersistentAck.v1':return bad
        if type(ack['COMPLETION_TIMESTAMP']) is not int or not 0<ack['COMPLETION_TIMESTAMP']<=MAX_COUNTER:return bad
        auth,deadline=ack['PUBLICATION_AUTHORIZATION_MONOTONIC'],ack['SHUTDOWN_DEADLINE_MONOTONIC']
        if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in (auth,deadline)) or auth>=deadline:return bad
        if ack['COMPLETION_BOUNDARY']!='VERIFIED_CONTENT_THEN_ATOMIC_ACK_PUBLICATION':return bad
        if ack['DRAIN_SEMANTICS']!='CALLER_WAIT_BOUND_ONLY_INFLIGHT_FILESYSTEM_OPERATION_NOT_CANCELLABLE':return bad
        if ack['EXPORT_GENERATION_ID']!=start['sender_generation'] or ack['EXPORT_SESSION_ID']!=start['session']:return bad
        files=ack['EXPORT_FILE_MANIFEST']
        if type(files) is not list or not 3<=len(files)<=31:return bad
        names=[f['name'] for f in files]
        expected=['session.json',*[f'{i:04d}.json' for i in range(1,len(files)-1)],'final.json']
        if names!=expected or set(p.name for p in entries)!=set(names+['ack.json']):return bad
        for item in files:
            if sha_file(directory/item['name'])!=item['sha256'] or (directory/item['name']).stat().st_size!=item['bytes']:return bad
        if len(entries)>start['max_files'] or any(p.stat().st_size>start['max_file_bytes'] for p in entries):return bad
        if ack['EXPORT_FILE_SHA256']!=sha_file(directory/'final.json'):return bad
        expected_fields=('FILE_WRITE_STATUS','FILE_CLOSE_STATUS','OS_FLUSH_STATUS','CONTENT_VERIFICATION_STATUS')
        if any(ack.get(k)!='SUCCESS' for k in expected_fields):return bad
        if ack.get('ACK_PERSISTENCE_STATUS')!='PUBLISHED_RECORD_REQUIRES_READER_VERIFICATION':return bad
        last=read(names[-2])['snapshot']
        counts=dict(EXPORTED_RECORD_COUNT=len(last['records']),DROPPED_RECORD_COUNT=last['dropped'],
                    EXPORT_ERROR_COUNT=final['export_errors'],QUEUE_LOSS_COUNT=final['queue_loss'],RETENTION_DROPPED_COUNT=final['retention_dropped'])
        if any(type(ack[k]) is not int or ack[k]!=v for k,v in counts.items()):return bad
        legacy=_inspect_legacy_export(directory,dict(acknowledged=True,session=start['session'],
                     generation=start['sender_generation'],final_sha256=ack['EXPORT_FILE_SHA256']))
        complete=legacy['complete'] and ack['EXPORT_COMPLETENESS']=='COMPLETE'
        return dict(status='COMPLETE_LOCAL_EXPORT_ONLY' if complete else 'ACKNOWLEDGED_WITH_LOSS',
                    complete=complete,shared_ip_headroom=None,ack_persistence_status='READBACK_VERIFIED',
                    os_flush_status='WRITER_REPORTED_SUCCESS',physical_power_loss_durability='NOT_PROVEN',
                    exported_unique_records=counts['EXPORTED_RECORD_COUNT'])
    except (OSError,ValueError,KeyError,TypeError,IndexError):return bad


def sha_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_sessions(directories):
    """Offline identity inventory; repeated UUIDs are never silently merged."""
    if type(directories) not in (list,tuple) or len(directories)>32:
        raise ValueError('Session inspection bound exceeded')
    seen=set();items=[]
    for directory in directories:
        p=Path(directory)/'session.json'
        if p.is_symlink() or p.stat().st_size>MAX_FILE_BYTES:raise ValueError('Invalid session file')
        entry=json.loads(p.read_text(encoding='utf-8'))
        generation=entry.get('sender_generation')
        if generation is None or generation_token(generation)!=generation:raise ValueError('Invalid sender generation')
        duplicate=generation in seen;seen.add(generation)
        items.append(dict(sender_generation=generation,export_session=entry.get('session'),duplicate_generation=duplicate))
    return dict(sessions=items,duplicate_generation_detected=any(x['duplicate_generation'] for x in items),
                aggregate_public_ip_acceptance=False)
