from pathlib import Path
import sys,secrets,time,json,hashlib,unittest
from unittest.mock import patch
R=Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'src'),str(R/'dependencies/r3')]
import relay_client
from transport import Receiver,envelope,signed
from pipeline import Pipeline
from durable import Store
class Tests(unittest.TestCase):
 def test_second_peer_cleanup(self):
  store=Store(R/'dependencies/disposable'/('ind_'+secrets.token_hex(5)+'.sqlite'),'fixture');p=Pipeline(store,secrets.token_hex(16),b'a'*32,['BTCUSDT'],'a'*64,lambda:time.time_ns()//1000000)
  real=relay_client.Peer;held=[]
  def acquire(*a,**k):
   if held:raise ValueError('injected second-peer failure')
   peer=real(*a,**k);held.append(peer);return peer
  try:
   with patch.object(relay_client,'Peer',acquire):
    with self.assertRaises(ValueError):relay_client.RelayClient(p,R/'disposable')
   self.assertEqual(len(held),1);self.assertIsNone(held[0].handle)
  finally:store.close()
 def test_final_duplicate_receipt_only(self):
  now=time.time_ns()//1000000;t=now//60000*60000-60000;key=b'a'*32;session='a'*32
  raw=dict(e='kline',s='BTCUSDT',E=now,st='UM',k=dict(s='BTCUSDT',i='1m',t=t,T=t+59999,o='100',h='103',l='99',c='102',v='3',x=True))
  r=Receiver(session,key,['BTCUSDT'],lambda:now+100);e=envelope(raw,session,now,{'BTCUSDT':('UM','PERPETUAL')})
  self.assertEqual(r.ingest(signed(e,key)),'ACCEPTED');original=dict(r.buckets['BTCUSDT',t])
  self.assertEqual(r.ingest(signed(dict(e,local_receipt_time_utc=now+1),key)),'DUPLICATE');self.assertEqual(r.buckets['BTCUSDT',t],original)
  for field,value in [('close','101'),('base_volume','4'),('exchange_event_time_utc',now+1),('quote_volume_if_available','306')]:
   self.assertTrue(r.ingest(signed(dict(e,**{field:value}),key)).startswith('INVALID'))
   self.assertEqual(r.buckets['BTCUSDT',t],original)
if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 paths=list((R/'src').glob('*.py'))+list((R/'dependencies/r3').glob('*.py'))
 (R/'independent/final_results.json').write_text(json.dumps(dict(passed=result.wasSuccessful(),tests=result.testsRun,failures=[(str(t),e) for t,e in result.failures+result.errors],hashes={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},external_requests=0,production_changes=0),indent=2));sys.exit(not result.wasSuccessful())
