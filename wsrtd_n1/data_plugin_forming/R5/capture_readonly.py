from pathlib import Path
import sys,json,datetime
R=Path(__file__).resolve().parent
sys.path.insert(0,r'D:\WSRTD_N1_ACTIVE_CHART_RADAR_R1\retirement_controller_r1')
import r3_observer as o
prior=json.loads(Path(r'D:\WSRTD_N1_DATA_PLUGIN_FORMING_R4\R4_PROTECTED_RUNTIME_NONINTERFERENCE.json').read_text())
rows=[]
for p in prior['processes']:
 try:
  with o.opened(p['pid']) as h:ident=o.handle_identity(h)
  rows.append(dict(pid=p['pid'],current=ident,prior_creation=p['creation']))
 except Exception as e:rows.append(dict(pid=p['pid'],error=str(e)))
out=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),observations=rows,listeners10101=o.listeners(10101),listeners18101=o.listeners(18101),scope='Point-in-time read-only identity/listener observation, not candle continuity proof',process_control_operations=0,protected_port_connections=0,production_binance_requests=0,installed_dll_writes=0,historical_database_writes=0)
(R/'R5_PROTECTED_RUNTIME_NONINTERFERENCE.json').write_text(json.dumps(out,indent=2));print('Read-only runtime receipt saved')
