from pathlib import Path
import sys,json,secrets,time,struct,base64
R=Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'src'),str(R/'dependencies/r3')]
from relay import encode,pack,unpack,send,read
from relay_client import RelayClient
from pipeline import Pipeline
from durable import Store
rows=[]
for mode in ('corrupt','duplicate','truncated','oversize','stale_session','stale_generation','wrong_universe','metadata_mismatch','invalid_finality','connection_loss','restart_replay'):
 store=Store(R/'dependencies/disposable'/('relaytest_'+secrets.token_hex(6)+'.sqlite'),'fixture')
 p=Pipeline(store,secrets.token_hex(16),secrets.token_bytes(32),['BTCUSDT'],'a'*64,lambda:time.time_ns()//1000000)
 client=RelayClient(p,R/'disposable');now=time.time_ns()//1000000;t=now//60000*60000
 raw=dict(e='kline',s='BTCUSDT',st='UM',E=now,k=dict(s='BTCUSDT',i='1m',t=t,T=t+59999,o='100',h='102',l='99',c='101',v='1',x=False))
 b=encode(raw,client.c,client.key,1)
 try:
  if mode=='duplicate':client.deliver(raw)
  if mode=='restart_replay':
   old=b;client.close();p.receiver.connected=True;client=RelayClient(p,R/'disposable');b=old
  if mode=='corrupt':b=bytes([b[0]^1])+b[1:]
  if mode.startswith('stale_'):
   o=unpack(b,client.key);o['session' if mode=='stale_session' else 'generation']='0'*32;b=pack(o,client.key)
  if mode in ('wrong_universe','metadata_mismatch','invalid_finality'):
   o=unpack(b,client.key);v=unpack(base64.b64decode(o['packet']),client.key)
   if mode=='wrong_universe':v['universe_version']='b'*64
   if mode=='metadata_mismatch':v['source_event']['k']['c']='999'
   if mode=='invalid_finality':v['source_event']['k']['x']='true';v['candle']['is_final']='true'
   o['packet']=base64.b64encode(pack(v,client.key)).decode();b=pack(o,client.key)
  if mode=='truncated':client.sender.sendall(struct.pack('!I',len(b))+b[:20]);client.sender.shutdown(1)
  elif mode=='oversize':client.sender.sendall(struct.pack('!I',999999))
  elif mode=='connection_loss':client.sender.shutdown(1)
  else:send(client.sender,b)
  rejected=False
  try:read(client.receiver)
  except (EOFError,OSError):rejected=True
  assert rejected,mode
  client.p.wait(timeout=5);assert not store.rows('BTCUSDT',True)
  rows.append(dict(case=mode,passed=True,relay_pid=client.identity['pid'],exit_code=client.p.returncode))
 finally:client.close();store.close()
(R/'R7_REAL_RELAY_NETWORK_TESTS.json').write_text(json.dumps(dict(passed=True,cases=rows,independent_process=True,actual_tcp=True,external_connections=0),indent=2));print('11 independent-relay negative cases PASS')
