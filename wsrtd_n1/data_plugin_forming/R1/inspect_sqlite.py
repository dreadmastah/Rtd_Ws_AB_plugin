"""Read bytes only from installed SQLite; query an in-memory image, never the original."""
import pathlib, sqlite3, hashlib, json, datetime
root=pathlib.Path(__file__).parent
p=pathlib.Path(r'D:\Amibroker_myDATA\N1\.wsrtd-n1\feed.sqlite')
for suffix in ('-wal','-journal'):
    if pathlib.Path(str(p)+suffix).exists():
        raise SystemExit('BLOCKED: active journal; no consistent image assumption')
before=p.stat(); raw=p.read_bytes(); after=p.stat()
assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
db=sqlite3.connect(':memory:'); db.deserialize(raw); db.execute('PRAGMA query_only=ON')
def rows(sql): return [list(r) for r in db.execute(sql)]
result={'captured_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'path':str(p),'sha256':hashlib.sha256(raw).hexdigest(),'size':len(raw),
 'method':'read bytes; deserialize into memory; no on-disk SQLite connection',
 'limitation':'stable observed file image, not exclusive-writer or application-consistency proof',
 'schema':rows("SELECT name,sql FROM sqlite_master WHERE type='table'"),
 'application_id':rows('PRAGMA application_id'),'user_version':rows('PRAGMA user_version')}
tables={r[0] for r in result['schema']}
for t in ('database_context','symbol_registry'):
    if t in tables: result[t]=rows('SELECT * FROM '+t+' LIMIT 1050')
if 'bars' in tables:
    result['coverage']=rows('SELECT symbol,interval,finalized,count(*),min(ts_ms),max(ts_ms) FROM bars GROUP BY symbol,interval,finalized')
    result['btc_eth_tail']=rows("SELECT * FROM bars WHERE symbol IN ('BTCUSDT','ETHUSDT') ORDER BY ts_ms DESC LIMIT 8")
assert p.read_bytes()==raw, 'File changed during observation'
result['original_bytes_unchanged']=True
(root/'SQLITE_IMAGE_EVIDENCE.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ('schema','btc_eth_tail')},indent=2))
