"""One resolver subprocess, one IPv4 result set; never connects or retries."""
import sys,socket,json,subprocess,time,ipaddress
from pathlib import Path
def resolve(host,port,allowed,deadline,fixture=False,delay=0):
 if host!=('localhost' if fixture else 'fstream.binance.com') or (not fixture and port!=443):raise ValueError('resolver endpoint')
 if not 1<=len(allowed)<=16:raise ValueError('DNS allowlist')
 for a in allowed:
  ip=ipaddress.IPv4Address(a)
  if (fixture and str(ip)!='127.0.0.1') or (not fixture and not ip.is_global):raise ValueError('address scope')
 remaining=deadline-time.monotonic()
 if remaining<=0:raise TimeoutError('resolution expired before dispatch')
 p=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),host,str(port),str(delay if fixture else 0)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 try:
  out,err=p.communicate(timeout=remaining)
  if p.returncode or len(out)>4096:raise ValueError('resolver output')
  ips=json.loads(out)
  if not ips or len(ips)>16 or any(ip not in allowed for ip in ips):raise ValueError('unexpected DNS answer')
  if time.monotonic()>=deadline:raise TimeoutError('late DNS result discarded')
  return sorted(set(ips))[0] # exactly one chosen address, no fallback iteration
 except subprocess.TimeoutExpired:
  p.terminate();p.communicate(timeout=3);raise TimeoutError('resolver cancelled/reaped')
 finally:
  if p.poll() is None:p.terminate();p.communicate(timeout=3)
  p.stdout.close();p.stderr.close()
if __name__=='__main__':
 host=sys.argv[1]
 if host not in ('localhost','fstream.binance.com'):raise ValueError('resolver host')
 time.sleep(float(sys.argv[3]));print(json.dumps(sorted({x[4][0] for x in socket.getaddrinfo(host,int(sys.argv[2]),socket.AF_INET,socket.SOCK_STREAM)})))
