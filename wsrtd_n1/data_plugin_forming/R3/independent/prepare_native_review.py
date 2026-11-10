from pathlib import Path
R=Path(__file__).resolve().parents[1]
s=(R/'tests'/'test_native_inherited.py').read_text()
s=s.replace('Author rerun of inherited independent R2 harness, plus changed R3 interval tests.','Independent rerun against R3 DLL with additional durable-day exclusion tests.')
needle=" record('weekly_direct_unsupported',dll.GetQuotesEx(b'BTCUSDT',604800,-1,4,q,None)==0)"
replacement=needle+'''
 p.rows=[row(day+i*60000,state=3 if i==1439 else 1) for i in range(1440)];p.serial=22
 record('daily_pending_final_cannot_complete_day',applied(22) and dll.GetQuotesEx(b'BTCUSDT',86400,-1,4,q,None)==0)
 p.rows=[row(day+i*60000) for i in range(2880)];p.serial=23
 record('daily_two_UTC_days_order_and_volume',applied(23) and dll.GetQuotesEx(b'BTCUSDT',86400,-1,4,q,None)==2 and q[0].date<q[1].date and q[0].volume==2880 and q[1].volume==2880)
'''
assert needle in s;s=s.replace(needle,replacement)
s=s.replace("(ROOT/'evidence'/'native_results.json')","(ROOT/'independent'/'native_results.json')")
(R/'independent'/'native_review_run.py').write_text(s)
