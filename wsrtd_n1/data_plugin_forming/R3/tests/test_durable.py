from pathlib import Path
import sys,json,secrets,subprocess,sqlite3,unittest
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from durable import Store
from transport import envelope
S='1'*32;T=1800057600000
def event(t=T,**changes):
 k=dict(s='BTCUSDT',i='1m',t=t,T=t+59999,o='100',h='102',l='99',c='101',v='2',x=True);k.update(changes)
 return envelope(dict(e='kline',s='BTCUSDT',E=t+60000,k=k),S,t+61000,{'BTCUSDT':('UM','PERPETUAL')})
if len(sys.argv)>1 and sys.argv[1]=='crash':
 st=Store(sys.argv[2],'fixture');st.commit(event(),int(sys.argv[3]),S,sys.argv[4]);raise SystemExit(99)
class Tests(unittest.TestCase):
 def setUp(self):
  self.p=R/'disposable'/('durable_'+secrets.token_hex(6)+'.sqlite');self.s=Store(self.p,'fixture');self.g=self.s.claim(S)
 def tearDown(self):self.s.close()
 def test_duplicate(self):
  self.assertEqual(self.s.commit(event(),self.g,S),'COMMITTED');self.assertEqual(self.s.commit(event(),self.g,S),'IDEMPOTENT');self.assertEqual(len(self.s.rows('BTCUSDT')),1)
 def test_conflict(self):
  self.s.commit(event(),self.g,S)
  with self.assertRaises(ValueError):self.s.commit(event(c='100'),self.g,S)
  self.assertEqual(len(self.s.rows('BTCUSDT')),1)
 def test_forming(self):
  with self.assertRaises(ValueError):self.s.commit(event(x=False),self.g,S)
  self.assertEqual(self.s.rows('BTCUSDT'),[])
 def test_stale_epoch(self):
  other=Store(self.p,'fixture');other.claim('2'*32);other.close()
  with self.assertRaises(ValueError):self.s.commit(event(),self.g,S)
 def test_before_crash(self):
  p=subprocess.run([sys.executable,'-B',__file__,'crash',str(self.p),str(self.g),'before']);self.assertEqual(p.returncode,71);self.assertEqual(self.s.rows('BTCUSDT'),[])
 def test_after_crash(self):
  p=subprocess.run([sys.executable,'-B',__file__,'crash',str(self.p),str(self.g),'after']);self.assertEqual(p.returncode,72);self.assertEqual(len(self.s.rows('BTCUSDT')),1)
 def test_storage_full(self):
  # Real SQLite maximum-page constraint on disposable DB, no injected success receipt.
  pages=self.s.db.execute('PRAGMA page_count').fetchone()[0];self.s.db.execute('PRAGMA max_page_count='+str(pages))
  failed=False
  for i in range(100):
   try:self.s.commit(event(T+i*60000),self.g,S)
   except sqlite3.OperationalError as e:failed='full' in str(e);break
  self.assertTrue(failed);self.assertFalse(self.s.db.in_transaction)
 def test_late_replay_gap(self):
  self.s.commit(event(T+60000),self.g,S);self.assertFalse(self.s.coverage('BTCUSDT',T,T+120000)['structural_complete'])
  self.s.commit(event(T),self.g,S);a=self.s.coverage('BTCUSDT',T,T+120000);self.assertTrue(a['structural_complete']);self.assertFalse(a['full_prefix_qualified'])
 def test_scope(self):
  with self.assertRaises(ValueError):Store(self.p,'wrong')
 def test_daily_gap(self):self.assertIsNone(self.s.daily('BTCUSDT',T//86400000*86400000))
 def test_precision(self):
  v='12345678901234567890.123456789012345678'
  self.s.commit(event(o=v,h=v,l=v,c=v),self.g,S)
  self.assertEqual(json.loads(self.s.rows('BTCUSDT')[0][1])[0],v)
 def test_corrupt_ledger(self):
  self.s.commit(event(),self.g,S);self.s.db.execute("UPDATE finals SET event_hash='bad'")
  with self.assertRaises(ValueError):self.s.coverage('BTCUSDT',T,T+60000)
suite=unittest.defaultTestLoader.loadTestsFromTestCase(Tests);result=unittest.TextTestRunner(verbosity=2).run(suite)
(R/'R3_SQLITE_TRANSACTION_ACCEPTANCE.json').write_text(json.dumps({'tests':result.testsRun,'pass':result.wasSuccessful(),'failures':[str(x) for x in result.failures+result.errors],'source_kind':'synthetic','power_loss_tested':False,'production_writes':0},indent=2))
raise SystemExit(not result.wasSuccessful())
