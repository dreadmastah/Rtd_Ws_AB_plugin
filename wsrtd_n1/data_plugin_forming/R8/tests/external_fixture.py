from pathlib import Path
import sys,json,hashlib,secrets,time,os,dataclasses
R=Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'src'),str(R/'tests')]
from external import ExternalWS,canonical,URL,validate
from custody import Attestation
from admission import Controller,Refused
from servers import Server
from test_network import contract
def manifest(port):
 a=Attestation(os.getpid());actor=a.check();a.close();c=contract();c.update(symbols=['BTCUSDT'],rest_requests=0,rest_weight=0,connection_attempts=1,subscriptions=1,reconnects=0,receiver_creation=actor['creation'])
 parent=R/'disposable';st=parent.stat()
 hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (R/'src').glob('*.py')}
 hashes.update({'dependencies/r3/'+p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (R/'dependencies/r3').glob('*.py')})
 return dict(version=1,scope='LOCAL_TLS_TEST',url=URL,contract=c,producer=actor,code_hashes=hashes,approved_ips=['127.0.0.1'],port=port,cafile=str(R/'disposable/tls/cert.pem'),output_dir=str(parent/('out_'+secrets.token_hex(5))),storage_parent_identity=dict(path=str(parent),device=st.st_dev,inode=st.st_ino),operator_authorization=True)
