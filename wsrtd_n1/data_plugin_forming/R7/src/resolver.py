"""Owned subprocess bounds resolver lifetime; no external resolution allowed in R7."""
import subprocess,sys,json,socket,time
from pathlib import Path
def resolve(host,port,timeout=.5,fixture_delay=0):
 if host!='localhost' or type(port)is not int or not 1024<=port<=65535 or port in (10101,18101):raise ValueError('R7 isolated resolution only')
 if not 0<timeout<=2 or not 0<=fixture_delay<=5:raise ValueError('bounds')
 p=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),str(port),str(fixture_delay)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 try:
  out,err=p.communicate(timeout=timeout)
  if p.returncode or len(out)>4096:raise ValueError('resolver result')
  addresses=json.loads(out)
  if not addresses or set(addresses)!={'127.0.0.1'}:raise ValueError('DNS pin/rebinding')
  return addresses
 except subprocess.TimeoutExpired:
  p.terminate();p.communicate(timeout=3)
  raise TimeoutError('resolver child cancelled and reaped')
 finally:
  if p.poll() is None:p.terminate();p.communicate(timeout=3)
  p.stdout.close();p.stderr.close()
if __name__=='__main__':
 time.sleep(float(sys.argv[2]));print(json.dumps(sorted({x[4][0] for x in socket.getaddrinfo('localhost',int(sys.argv[1]),socket.AF_INET,socket.SOCK_STREAM)})))
