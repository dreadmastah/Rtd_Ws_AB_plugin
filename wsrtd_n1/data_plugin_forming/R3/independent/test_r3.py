import sys,pathlib,tempfile,unittest,json,hashlib,sqlite3,hmac,math
R=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from durable import Store,exact
from pipeline import Pipeline,Budget,plan
from transport import canonical
T=1800057600000
def raw(t,E,final=True):
 return {'e':'kline','s':'BTCUSDT','E':E,'st':'UM','k':{'s':'BTCUSDT','i':'1m','t':t,'T':t+59999,'o':'10','h':'12','l':'9','c':'11','v':'2','q':'22','n':2,'x':final,'f':123,'L':124}}
class Tests(unittest.TestCase):
 def setUp(self):
  self.path=pathlib.Path(tempfile.mkdtemp(prefix='independent_',dir=R/'disposable'))/'history.sqlite'
  self.store=Store(self.path,'fixture');self.now=[T+61000];self.session='1'*32;self.key=b'k'*32
  self.p=Pipeline(self.store,self.session,self.key,['BTCUSDT'],'a'*64,lambda:self.now[0])
 def tearDown(self):self.store.close()
 def commit(self,e=None):return self.p.receive(self.p.encode(e or raw(T,self.now[0])))
 def test_decimal_no_context_rounding(self):
  s='12345678901234567890.123456789123456789';self.assertEqual(exact(s),s)
 def test_wrong_scope_no_write(self):
  self.store.close();self.store=Store(self.path,'fixture');self.store.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
  before=self.path.read_bytes()
  with self.assertRaises(ValueError):Store(self.path,'other')
  self.assertEqual(before,self.path.read_bytes())
 def test_forming_never_durable(self):
  self.now[0]=T+1000;self.assertEqual(self.commit(raw(T,self.now[0],False)),'ACCEPTED');self.assertFalse(self.store.rows('BTCUSDT'))
 def test_late_final_and_gap(self):
  self.assertEqual(self.commit(),'DURABLE_FINALIZED:COMMITTED')
  self.now[0]=T+181000;self.commit(raw(T+120000,self.now[0]))
  c=self.store.coverage('BTCUSDT',T,T+180000);self.assertFalse(c['structural_complete']);self.assertFalse(c['full_prefix_qualified'])
 def test_same_final_idempotent(self):
  b=self.p.encode(raw(T,self.now[0]));self.assertEqual(self.p.receive(b),'DURABLE_FINALIZED:COMMITTED');self.assertEqual(self.p.receive(b),'DURABLE_FINALIZED:IDEMPOTENT');self.assertEqual(len(self.store.rows('BTCUSDT')),1)
 def test_conflict_immutable(self):
  self.commit();bad=raw(T,self.now[0]);bad['k']['c']='10'
  self.assertNotEqual(self.commit(bad),'DURABLE_FINALIZED:COMMITTED');self.assertEqual(json.loads(self.store.rows('BTCUSDT')[0][1])[3],'11')
 def test_stale_epoch_not_durable(self):
  self.store.claim('2'*32);self.assertTrue(self.commit().startswith('LIVE_FINALIZED_NOT_YET_DURABLE'));self.assertFalse(self.store.rows('BTCUSDT'))
 def test_invalid_raw_linkage(self):
  b=self.p.encode(raw(T,self.now[0]));o=json.loads(b[32:]);o['source_event']['k']['c']='10';body=canonical(o)
  with self.assertRaises(ValueError):self.p.receive(hmac.digest(self.key,body,'sha256')+body)
 def test_wrong_universe(self):
  b=self.p.encode(raw(T,self.now[0]));o=json.loads(b[32:]);o['universe_version']='b'*64;body=canonical(o)
  with self.assertRaises(ValueError):self.p.receive(hmac.digest(self.key,body,'sha256')+body)
 def test_ledger_corruption_detected(self):
  self.commit();self.store.db.execute("UPDATE finals SET event_hash='broken'")
  with self.assertRaises(ValueError):self.store.rows('BTCUSDT')
 def test_recovery_no_prefix_promotion(self):
  self.commit();self.store.close();self.store=Store(self.path,'fixture');p=Pipeline(self.store,'2'*32,b'b'*32,['BTCUSDT'],'a'*64,lambda:self.now[0]);p.restore()
  self.assertEqual(len(p.receiver.history),1);self.assertFalse(p.receiver.status()['full_prefix_complete'])
 def test_budget_nan_rejected(self):
  for args in [(float('nan'),2,100),(2,float('nan'),100),(2,2,float('nan'))]:
   with self.assertRaises((ValueError,TypeError)):Budget(['BTCUSDT'],*args,lambda:1)
 def test_budget_noninteger_rejected(self):
  for x in [True,1.5]:
   with self.assertRaises((ValueError,TypeError)):Budget(['BTCUSDT'],x,2,100,lambda:1)
 def test_budget_page_type(self):
  b=Budget(['BTCUSDT'],3,6,100,lambda:1)
  for x in [True,1.5,float('nan')]:
   with self.assertRaises((ValueError,TypeError)):b.reserve('BTCUSDT',x)
 def test_budget_no_rest(self):
  b=Budget(['BTCUSDT'],0,0,100,lambda:1)
  with self.assertRaises(ValueError):b.reserve('BTCUSDT',1)
 def test_exact_tail(self):
  p=plan(T,T+1000*60000);self.assertEqual([x['limit'] for x in p],[499,499,2]);self.assertEqual(p[-1]['endTime'],T+1000*60000-1)
 def test_daily_incomplete_refused(self):
  self.commit();self.assertIsNone(self.store.daily('BTCUSDT',T//86400000*86400000))
 def test_durable_raw_metadata_preserved(self):
  self.commit();raw_json=self.store.db.execute('SELECT envelope_json FROM receipts').fetchone()[0];e=json.loads(raw_json)
  self.assertEqual(e['universe_version'],'a'*64);self.assertEqual(e['source_event']['k']['f'],123);self.assertEqual(e['source_event']['k']['L'],124)
 def test_missing_integrated_receipt_rejected(self):
  self.commit();self.store.db.execute('DELETE FROM receipts')
  with self.assertRaises(ValueError):self.p.restore()
 def test_other_symbol_success_keeps_pending_failure_visible(self):
  import struct
  self.p=Pipeline(self.store,'2'*32,self.key,['BTCUSDT','ETHUSDT'],'a'*64,lambda:self.now[0])
  original=self.store.commit
  def fail_btc(e,*a,**kw):
   if e['logical_symbol']=='BTCUSDT':raise sqlite3.OperationalError('injected full')
   return original(e,*a,**kw)
  self.store.commit=fail_btc
  self.assertTrue(self.commit().startswith('LIVE_FINALIZED_NOT_YET_DURABLE'))
  e=raw(T,self.now[0]);e['s']='ETHUSDT';e['k']['s']='ETHUSDT'
  self.assertEqual(self.commit(e),'DURABLE_FINALIZED:COMMITTED')
  self.assertIsNotNone(self.p.storage_error)
  self.assertEqual(struct.unpack_from('<I',self.p.snapshot('fixture'),12)[0],0)

if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 receipt={'passed':result.wasSuccessful(),'tests':result.testsRun,'failures':[(str(t),e) for t,e in result.failures+result.errors],
  'hashes':{p:hashlib.sha256((R/p).read_bytes()).hexdigest() for p in ['src/durable.py','src/pipeline.py','src/transport.py']},'network_requests':0,'production_writes':0}
 (R/'independent'/'receiver_durable_results.json').write_text(json.dumps(receipt,indent=2));sys.exit(not result.wasSuccessful())
