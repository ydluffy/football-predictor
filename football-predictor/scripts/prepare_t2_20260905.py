import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def read(p):
    with (ROOT / p).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))
def write(p, rows):
    with (ROOT / p).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
markets = [r for r in read('data/manual/sporttery_handicap_markets_2026-09-05_2201_confirm.csv') if '2026-09-05 23:15' <= r['kickoff_time'] < '2026-09-06 10:00']
assert len(markets) == 13
assert {r['match_number'] for r in markets} == {f'{i:03}' for i in range(17,30)}
keys = {(r['date'],r['match_number'],r['home_team'],r['away_team']) for r in markets}
plays = [r for r in read('data/manual/sporttery_play_odds_2026-09-05_2201_confirm.csv') if (r['date'],r['match_number'],r['home_team'],r['away_team']) in keys]
write('artifacts/data/t2_2201_markets.csv', markets)
write('artifacts/data/t2_2201_plays.csv', plays)
scan = json.loads((ROOT / 'artifacts/data/sporttery_sales_window_scan_2026-09-05_2201_confirm.json').read_text(encoding='utf-8-sig'))
scan['fixtures'] = [f for f in scan['fixtures'] if f['match_number'] in {f'{i:03}' for i in range(17,30)}]
assert all(f['sale_status']=='on_sale' for f in scan['fixtures'])
(ROOT / 'artifacts/data/t2_2201_scan.json').write_text(json.dumps(scan,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'markets':len(markets),'plays':len(plays),'on_sale':len(scan['fixtures'])}))
