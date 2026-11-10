from pathlib import Path
import subprocess,json
R=Path(__file__).resolve().parents[1]
paths=[Path('C:/Program Files/Git/usr/bin/openssl.exe'),Path('C:/Program Files/Git/mingw64/bin/openssl.exe')]
exe=next((p for p in paths if p.exists()),None)
print(exe)
if exe:
 p=R/'disposable/tls';p.mkdir(exist_ok=True)
 cmd=[str(exe),'req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(p/'key.pem'),'-out',str(p/'cert.pem'),'-days','2','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost','-addext','basicConstraints=critical,CA:TRUE']
 subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 print('test-only certificate generated')
