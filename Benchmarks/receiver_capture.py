"""Offline passive-observer prototype. Never imported by Sender or relay.

offer accepts small, already parsed observation metadata. It never performs
network/file I/O or waits on the data path. Export is an explicitly separate
offline operation. Upstream-only values default to unavailable (JSON null).
"""
from collections import deque
import hashlib
import json
import math
from pathlib import Path

FIELDS = {'kind', 'symbol', 'interval', 'candle_open_ms', 'ohlcv',
          'raw_received', 'parser_accepted', 'relay_receipt_utc_ms',
          'relay_receipt_monotonic_ns', 'sender_generation', 'sender_sequence',
          'shard', 'upstream_event_ms', 'upstream_close_ms', 'finalized',
          'repair_class', 'transition', 'payload_sha256'}

SCHEMA_CONTRACT = 'RC8A_CAPTURE_MINIMUM_V1'
INTEGER_FIELDS = {'candle_open_ms', 'relay_receipt_utc_ms',
                  'relay_receipt_monotonic_ns', 'sender_sequence',
                  'upstream_event_ms', 'upstream_close_ms'}
BOOLEAN_FIELDS = {'raw_received', 'parser_accepted', 'finalized'}
CANDLE_FIELDS = ('symbol', 'interval', 'candle_open_ms', 'ohlcv',
                 'raw_received', 'parser_accepted', 'relay_receipt_utc_ms',
                 'relay_receipt_monotonic_ns')
MINUTE_CLASSES = {'MINUTE_GAP', 'MINUTE_STALE', 'MINUTE_RECONNECT'}
DAILY_CLASSES = {'DAILY_ROLLOVER', 'DAILY_RECHECK'}
REPAIR_CLASSES = MINUTE_CLASSES | DAILY_CLASSES | {'MANUAL_HISTORY', 'NATIVE_PRELOAD'}


def _text_token(value):
    return (type(value) is str and 1 <= len(value) <= 128
            and all(c.isprintable() and not c.isspace() for c in value))


def _field_valid(key, value):
    # Null means unavailable. Only kind is required for admission.
    if value is None:
        return key != 'kind'
    if key in INTEGER_FIELDS:
        return type(value) is int and 0 <= value <= 2**63-1
    if key in BOOLEAN_FIELDS:
        return type(value) is bool
    if key in ('kind', 'sender_generation'):
        return _text_token(value)
    if key == 'transition':
        return False  # A1-CONSERVATIVE: no non-null vocabulary is approved.
    if key == 'ohlcv':
        if type(value) not in (list, tuple) or len(value) != 5:
            return False
        try:
            if not all(type(v) in (int, float) and math.isfinite(v) for v in value):
                return False
        except OverflowError:
            return False
        o, h, l, c, v = value
        return 0 < l <= min(o, c) <= max(o, c) <= h and v >= 0
    # Bound strings before iteration, hashing, splitting or serialization.
    if type(value) is not str or not 1 <= len(value) <= 128:
        return False
    if key == 'symbol':
        return (all(c.isalnum() or c in '_.-' for c in value)
                and any(c.isalnum() for c in value))
    if key == 'interval':
        return value in ('1m', '1d')
    if key == 'repair_class':
        return value in REPAIR_CLASSES
    if key == 'payload_sha256':
        return len(value) == 64 and all(c in '0123456789abcdefABCDEF' for c in value)
    if key == 'shard':
        prefix, separator, suffix = value.partition(':')
        return (prefix in ('market', 'public') and separator == ':'
                and 1 <= len(suffix) <= 19
                and all(c in '0123456789' for c in suffix)
                and (suffix == '0' or suffix[0] != '0')
                and int(suffix) <= 2**63-1)
    return False


def _certification_eligible(record):
    # Called only after schema validation. Admission alone is not certification.
    return (record['kind'] == 'candle'
            and all(record.get(key) is not None for key in CANDLE_FIELDS)
            and record['raw_received'] is True and record['parser_accepted'] is True)


class PassiveCapture:
    def __init__(self, generation, capacity=128, byte_capacity=512*1024,
                 record_limit=4096, artifact_limit=1024*1024, retained_artifacts=4):
        if not isinstance(generation,str) or not 1 <= len(generation) <= 64:
            raise ValueError('Bounded receiver generation required')
        if not (1 <= capacity <= 128 and 128 <= record_limit <= 4096 and
                record_limit <= byte_capacity <= 512*1024 and
                record_limit <= artifact_limit <= 1024*1024 and
                1 <= retained_artifacts <= 4):
            raise ValueError('Capture bounds invalid')
        self.generation=generation; self.capacity=capacity; self.byte_capacity=byte_capacity
        self.record_limit=record_limit;self.artifact_limit=artifact_limit;self.retained_artifacts=retained_artifacts
        self.records=deque();self.bytes=0;self.closed=False;self.sequence=0
        self.observer_failures=0
        self.counts=dict(offered=0,accepted=0,overflow=0,invalid=0,closed=0,export_errors=0,retention_loss=0,exported=0,uncertified=0)

    def count(self, kind, amount=1):
        self.counts[kind]=min(2**63-1,self.counts[kind]+amount)

    def offer(self, record):
        try:
            return self._offer(record)
        except MemoryError:
            raise
        except Exception:
            # Failure reporting is observer-owned and never invokes its sink.
            self.observer_failures=min(2**63-1,self.observer_failures+1)
            return False

    def _offer(self, record):
        if self.sequence >= 2**63-1:
            self.count('invalid');return False
        self.sequence+=1;self.count('offered')
        if self.closed:
            self.count('closed');return False
        try:
            if type(record) is not dict or len(record)>len(FIELDS):
                raise ValueError('Invalid observer schema')
            if any(type(key) is not str or len(key)>128 or key not in FIELDS for key in record):
                raise ValueError('Unknown observer field')
            if 'kind' not in record:
                raise ValueError('Observer kind required')
            for key,value in record.items():
                if not _field_valid(key,value):
                    raise ValueError('Invalid observer field value')
            interval=record.get('interval');repair=record.get('repair_class')
            if interval is not None and ((repair in MINUTE_CLASSES and interval!='1m')
                                         or (repair in DAILY_CLASSES and interval!='1d')):
                raise ValueError('Repair classification does not match interval')
            eligible=_certification_eligible(record)
            row=dict(sender_generation=None,sender_sequence=None,shard=None,
                     upstream_event_ms=None,upstream_close_ms=None,finalized=None,
                     repair_class=None)
            row.update(record)
            row.update(receiver_generation=self.generation,capture_sequence=self.sequence,schema_version=1)
            encoded=json.dumps(row,separators=(',',':'),allow_nan=False).encode()+b'\n'
            if len(encoded)>self.record_limit:
                raise ValueError('Oversize observer record')
        except MemoryError:
            raise
        except Exception:
            self.count('invalid');return False
        if len(self.records)>=self.capacity or self.bytes+len(encoded)>self.byte_capacity:
            self.count('overflow');return False
        self.records.append(encoded);self.bytes+=len(encoded);self.count('accepted')
        if not eligible:self.count('uncertified')
        return True

    def health(self):
        try:
            pending=len(self.records);counts=dict(self.counts)
            complete=(self.counts['accepted']>0 and self.observer_failures==0
                      and not any(self.counts[k] for k in ('overflow','invalid','closed','export_errors','retention_loss','uncertified')))
        except MemoryError:
            raise
        except Exception:
            pending=None;counts=None;complete=False
        return dict(receiver_generation=self.generation,schema_contract=SCHEMA_CONTRACT,pending=pending,pending_bytes=self.bytes,
                    counts=counts,observer_failures=self.observer_failures,evidence_complete=complete,
                    native_storage_acceptance='NOT_PROVEN')

    def close(self): self.closed=True

    def export(self, directory):
        """Finite snapshot export; caller supplies a new isolated output root.

        Byte limits apply to data segments. Health/manifest overhead is fixed
        and bounded (at most four entries). No namespace reuse/overwrite.
        Failed exports leave queued records for a separately named retry.
        """
        parts=[];current=bytearray();retention_loss=0;retained=0
        for encoded in self.records:
            if len(current)+len(encoded)>self.artifact_limit:
                parts.append(bytes(current));current.clear()
            if len(parts)>=self.retained_artifacts:
                retention_loss+=1;continue
            current.extend(encoded);retained+=1
        if current:parts.append(bytes(current))
        try:
            directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
            manifest=[]
            for index,data in enumerate(parts):
                path=directory/f'capture-{index+1:03}.jsonl'
                with path.open('xb') as out: out.write(data)
                manifest.append(dict(path=path.name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
            health=self.health()
            health['counts']['retention_loss']=min(2**63-1,health['counts']['retention_loss']+retention_loss)
            health['counts']['exported']=min(2**63-1,health['counts']['exported']+retained)
            health['pending']=health['pending_bytes']=0
            health['evidence_complete']=health['evidence_complete'] and retained>0 and retention_loss==0
            with (directory/'capture-manifest.json').open('x',encoding='utf-8') as out:
                json.dump(dict(health=health,segments=manifest),out,indent=2)
        except MemoryError:
            raise
        except Exception:
            self.count('export_errors');return False
        self.count('retention_loss',retention_loss);self.count('exported',retained)
        self.records.clear();self.bytes=0;return True
