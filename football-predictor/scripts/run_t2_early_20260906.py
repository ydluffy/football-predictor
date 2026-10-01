import csv
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT=Path(__file__).resolve().parents[1]
TZ=timezone(timedelta(hours=8))
def run(script,*args):
    if datetime.now(TZ)>=datetime(2026,9,6,16,45,tzinfo=TZ):
        raise RuntimeError('hard lock reached; stop candidate generation')
    r=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'scripts'/script),*args],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    print(script,r.returncode,r.stdout[-1300:],r.stderr[-1300:],flush=True)
    if r.returncode: raise RuntimeError(script)

scan=json.loads((ROOT/'artifacts/data/sporttery_sales_window_scan_2026-09-06_1632_confirm.json').read_text(encoding='utf-8'))
scan['fixtures']=[f for f in scan['fixtures'] if f['match_number'] in ['001','002','003','004','005']]
assert len(scan['fixtures'])==5
scan['planned_tasks']=[]
sp='artifacts/data/t2_early_20260906_scan.json'
(ROOT/sp).write_text(json.dumps(scan,ensure_ascii=False,indent=2),encoding='utf-8')
mp='artifacts/data/t2_early_20260906_markets.csv'
with (ROOT/'data/manual/sporttery_handicap_markets_2026-09-06_1632_confirm.csv').open(encoding='utf-8-sig',newline='') as f:
    reader=csv.DictReader(f);fields=reader.fieldnames;rows=[r for r in reader if r['date']=='2026-09-06' and r['match_number'] in ['001','002','003','004','005']]
assert len(rows)==5
with (ROOT/mp).open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
pp='data/manual/sporttery_play_odds_2026-09-06_1632_confirm.csv'
run('refresh_the_odds_for_sporttery.py','--scan-json',sp,'--snapshot-type','final','--regions','eu','--timeout','25')
run('check_evening_final_analysis_gate.py','--official-markets',mp,'--play-odds',pp,'--matches','001,002,003,004,005','--decision-start','2026-09-06T16:30:00+08:00','--decision-lock','2026-09-06T16:45:00+08:00','--sales-cutoff','2026-09-06T17:00:00+08:00','--output','artifacts/data/t2_early_20260906_gate.json','--markdown-output','artifacts/data/t2_early_20260906_gate.md','--require-ready')
run('predict_sporttery_handicap.py','--market-csv',mp,'--output','artifacts/data/t2_early_20260906_model.csv','--audit-output','artifacts/data/t2_early_20260906_model.json')
run('build_multi_play_betting_strategy.py','--market-csv',mp,'--handicap-model-csv','artifacts/data/t2_early_20260906_model.csv','--plans-output','artifacts/data/t2_early_20260906_plans.csv','--matches-output','artifacts/data/t2_early_20260906_matches.csv','--report-output','artifacts/data/t2_early_20260906_strategy.md','--audit-output','artifacts/data/t2_early_20260906_strategy.json')
run('build_sporttery_all_play_candidates.py','--market-csv',mp,'--play-odds-csv',pp,'--start-after','2026-09-06 16:30','--start-before','2026-09-06 18:30','--base-output','artifacts/data/t2_early_20260906_base.csv','--play-output','artifacts/data/t2_early_20260906_plays.csv','--report-output','artifacts/data/t2_early_20260906_allplays.md','--audit-output','artifacts/data/t2_early_20260906_allplays.json')
run('predict_sporttery_handicap_shadow_v2.py','--market-csv',mp,'--output','artifacts/data/t2_early_20260906_shadow_v2.csv','--audit-output','artifacts/data/t2_early_20260906_shadow_v2.json','--stage','final','--sales-day','2026-09-06')
