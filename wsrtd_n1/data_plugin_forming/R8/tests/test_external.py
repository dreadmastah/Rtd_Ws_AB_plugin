from external_fixture import *
rows=[]
for mode in ('success','bad_digest','missing_authority','url','proxy','expired','wrong_pid','wrong_hash','bad_ip','live_fixture_ca','redirect','reconnect','zero_rest','extra_sub','restart'):
 s=Server('redirect' if mode=='redirect' else 'ws_raw',b'{}',cert=str(R/'disposable/tls/cert.pem'),key=str(R/'disposable/tls/key.pem'));m=manifest(s.port);b=None;ctl=None
 if mode=='missing_authority':m['operator_authorization']=False
 if mode=='url':m['url']=URL.replace('/market','')
 if mode=='wrong_pid':m['producer']['pid']=1
 if mode=='wrong_hash':m['code_hashes']['external.py']='0'*64
 if mode=='bad_ip':m['approved_ips']=['127.0.0.2']
 if mode=='expired':m['contract']['start_ms']-=130000;m['contract']['end_ms']-=130000
 digest=hashlib.sha256(canonical(m)).hexdigest()
 if mode=='bad_digest':digest='0'*64
 try:
  if mode=='live_fixture_ca':validate(m,digest,False)
  path=R/'disposable'/('external_'+secrets.token_hex(5)+'.sqlite');Controller.provision(path,m['contract']);ctl=Controller(path,m['contract']);b=ExternalWS(ctl,m,digest,True)
  if mode=='zero_rest':b.http('metadata')
  elif mode=='extra_sub':b.subscribe('ETHUSDT')
  elif mode=='reconnect':b.connect_ws(True)
  else:
   if mode=='proxy':os.environ['HTTPS_PROXY']='http://127.0.0.1:18101'
   b.connect_ws();assert b.receive()==b'{}'
   if mode=='restart':
    b.close();ctl.close();ctl=Controller(path,m['contract']);b=ExternalWS(ctl,m,digest,True);b.connect_ws()
  assert mode in ('success','proxy'),mode
 except (Refused,ValueError):assert mode not in ('success','proxy'),mode
 finally:
  os.environ.pop('HTTPS_PROXY',None)
  if b:b.close()
  if ctl:ctl.close()
  s.close()
 assert s.count==(1 if mode in ('success','proxy','redirect','restart') else 0),(mode,s.count)
 rows.append(dict(case=mode,passed=True,connections=s.count))
(R/'R8_EXTERNAL_ENDPOINT_NEGATIVE_TESTS.json').write_text(json.dumps(dict(passed=True,cases=rows,actual_local_tls=True,live_connections=0),indent=2));print('15 external transport local cases PASS')
