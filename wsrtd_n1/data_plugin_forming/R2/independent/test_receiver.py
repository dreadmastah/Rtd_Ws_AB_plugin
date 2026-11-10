"""Independent adversarial tests. Writes disposable fixtures only; no network."""
import sys,unittest,json,hashlib,sqlite3,tempfile,pathlib,time,copy
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import transport as T

class Cases(unittest.TestCase):
 def setUp(self):
  self.t=1793746800000;self.now=[self.t+20000];self.session='a'*32;self.key=b'k'*32
  self.r=T.Receiver(self.session,self.key,['BTCUSDT','ETHUSDT'],clock=lambda:self.now[0])
 def event(self,s='BTCUSDT',t=None,et=None,final=False,**kw):
  t=self.t if t is None else t;et=self.now[0] if et is None else et
  k=dict(s=s,i='1m',t=t,T=t+59999,o='10',h='12',l='9',c='11',v='2',q='22',n=2,x=final);k.update(kw)
  return T.envelope(dict(e='kline',s=s,E=et,k=k),self.session,self.now[0],{s:('UM','PERPETUAL')})
 def put(self,e):return self.r.ingest(T.signed(e,self.key))
 def test_wrong_key(self):
  self.assertTrue(self.r.ingest(T.signed(self.event(),b'x'*32)).startswith('INVALID'))
  self.assertFalse(self.r.buckets)
 def test_wrong_session(self):
  e=self.event();e['producer_session']='b'*32
  self.assertTrue(self.put(e).startswith('INVALID'))
 def test_duplicate_idempotence(self):
  e=self.event();self.assertEqual(self.put(e),'ACCEPTED');serial=self.r.serial
  self.assertEqual(self.put(e),'DUPLICATE');self.assertEqual(serial,self.r.serial)
 def test_old_event(self):
  self.assertEqual(self.put(self.event()),'ACCEPTED')
  self.assertTrue(self.put(self.event(et=self.now[0]-1,c='10')).startswith('INVALID'))
 def test_final_cannot_reopen(self):
  self.now[0]=self.t+60000;f=self.event(final=True,et=self.t+59999)
  self.assertEqual(self.put(f),'ACCEPTED')
  self.assertTrue(self.put(self.event(final=False)).startswith('INVALID'))
 def test_late_final_previous_bucket(self):
  self.assertEqual(self.put(self.event()),'ACCEPTED');self.now[0]=self.t+61000
  self.assertEqual(self.put(self.event(t=self.t+60000)),'ACCEPTED')
  self.assertEqual(self.put(self.event(t=self.t,final=True,et=self.t+60000)),'ACCEPTED')
  self.assertFalse(self.r.missing_finals)
 def test_wall_clock_is_not_finality(self):
  self.put(self.event());self.now[0]=self.t+61000
  rows,status=self.r.snapshot();self.assertFalse(rows);self.assertEqual(status['BTCUSDT'],'STALE')
  self.assertFalse(self.r.buckets['BTCUSDT',self.t]['is_final'])
 def test_disconnect_strips_forming(self):
  self.put(self.event());self.r.disconnect();rows,status=self.r.snapshot()
  self.assertFalse(rows);self.assertEqual(status['BTCUSDT'],'STALE')
  self.assertTrue(self.put(self.event()).startswith('INVALID'))
 def test_stale_receipt(self):
  e=self.event();self.now[0]+=6000
  self.assertTrue(self.put(e).startswith('INVALID'))
 def test_cumulative_volume_regression(self):
  self.put(self.event());self.now[0]+=1
  self.assertTrue(self.put(self.event(v='1')).startswith('INVALID'))
 def test_source_identity_and_finality_types(self):
  for field,value in [('raw_symbol','ETHUSDT'),('is_final',1),('schema_version',True),('provenance','BINANCE_VERIFIED')]:
   e=self.event();e[field]=value;self.assertTrue(self.put(e).startswith('INVALID'),field)
 def test_precision_preserved(self):
  e=self.event(c='10.123456789123456789');self.put(e)
  self.assertEqual(self.r.buckets['BTCUSDT',self.t]['close'],e['close'])
 def test_deep_json_rejected_not_crash(self):
  b=b'['*1200+b'0'+b']'*1200
  import hmac
  self.assertTrue(self.r.ingest(hmac.digest(self.key,b,'sha256')+b).startswith('INVALID'))
 def db(self,rows):
  folder=pathlib.Path(tempfile.mkdtemp(prefix='independent_',dir=ROOT/'disposable'));p=folder/'history.sqlite'
  db=sqlite3.connect(p);db.executescript('PRAGMA application_id=1465074229;PRAGMA user_version=2;CREATE TABLE database_context(database_id);INSERT INTO database_context VALUES("fixture");CREATE TABLE bars(database_id,symbol,interval,finalized,ts_ms,o REAL,h REAL,l REAL,c REAL,v REAL);')
  db.executemany('INSERT INTO bars VALUES(?,?,?,?,?,?,?,?,?,?)',[('fixture','BTCUSDT','1m',1,*r) for r in rows]);db.commit();db.close();return p
 def test_numeric_equivalent_sqlite_merge(self):
  self.r.load_history(self.db([(self.t,10,12,9,11,2)]),'fixture')
  self.now[0]=self.t+60000
  self.assertEqual(self.put(self.event(final=True,et=self.t+59999)),'ACCEPTED')
  rows,_=self.r.snapshot();self.assertEqual(len(rows),1);self.assertEqual(rows['BTCUSDT',self.t][1],'SQLITE_FINALIZED')
 def test_history_regression_rejected_or_retained(self):
  self.r.load_history(self.db([(self.t-60000,10,12,9,11,2)]),'fixture')
  try:self.r.load_history(self.db([]),'fixture')
  except ValueError:pass
  self.assertIn(('BTCUSDT',self.t-60000),self.r.history)
 def test_finalized_pending_backpressure(self):
  for n in range(T.MAX_BUCKETS):
   self.now[0]=self.t+(n+1)*60000
   self.assertEqual(self.put(self.event(t=self.t+n*60000,et=self.now[0],final=True)),'ACCEPTED')
  self.now[0]+=60000
  self.assertTrue(self.put(self.event(t=self.now[0]-60000,final=True)).startswith('INVALID'))
  self.assertEqual(len(self.r.buckets),T.MAX_BUCKETS)

if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(Cases);result=unittest.TextTestRunner(verbosity=2).run(suite)
 receipt={'tests':result.testsRun,'failures':[(str(t),e) for t,e in result.failures], 'errors':[(str(t),e) for t,e in result.errors], 'passed':result.wasSuccessful(), 'source_sha256':hashlib.sha256((ROOT/'transport.py').read_bytes()).hexdigest(), 'network_requests':0,'production_mutations':0,'actual_amibroker':False}
 (ROOT/'independent'/'receiver_results.json').write_text(json.dumps(receipt,indent=2))
 sys.exit(not result.wasSuccessful())
