import csv, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
nums={f'{n:03d}' for n in range(6,15)}
scan=json.loads((ROOT/'artifacts/data/sporttery_sales_window_scan_2026-09-06_1819_confirm.json').read_text(encoding='utf-8'))
scan['fixtures']=[f for f in scan['fixtures'] if f['match_number'] in nums]
scan['planned_tasks']=[]
assert len(scan['fixtures'])==9 and all(f['sale_status']=='on_sale' for f in scan['fixtures'])
(ROOT/'artifacts/data/t2_late_20260906_scan.json').write_text(json.dumps(scan,ensure_ascii=False,indent=2),encoding='utf-8')
def subset(src,dst,keep):
    with (ROOT/src).open(encoding='utf-8-sig',newline='') as f:
        r=csv.DictReader(f); fields=r.fieldnames; rows=[x for x in r if x['match_number'].zfill(3) in keep and x['date']=='2026-09-06']
    with (ROOT/dst).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    return len(rows)
assert subset('data/manual/sporttery_handicap_markets_2026-09-06_1819_confirm.csv','artifacts/data/t2_late_20260906_markets_all.csv',nums)==9
assert subset('data/manual/sporttery_handicap_markets_2026-09-06_1819_confirm.csv','artifacts/data/t2_late_20260906_markets_plan.csv',nums-{'013'})==8
print('prepared 9 analysis rows; 8 parlay-eligible rows; 013 excluded')
