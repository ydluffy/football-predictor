"""Archive free-provider current-season results without exposing credentials.

This collector never changes training artifacts, forecasts or production ledgers.
Partial provider failures are saved explicitly for restart recovery.
"""
import json, sys
from pathlib import Path
from datetime import datetime, timezone
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'src'))
from import_football_data_org_europe_incremental import _load_dotenv
from world_cup.football_data_org_adapter import FootballDataOrgClient

def main():
    _load_dotenv(R/'.env')
    now=datetime.now(timezone.utc)
    destination=R/'artifacts/data/independent_refresh'/now.strftime('%Y%m%dT%H%M%SZ')
    destination.mkdir(parents=True,exist_ok=False)
    client=FootballDataOrgClient(timeout=20)
    audit={'captured_at':now.isoformat(),'season':2026,'production_change_allowed':False,'competitions':{}}
    for code in ['PL','BL1','FL1','SA','DED','PPL','PD']:
        try:
            payload=client.get(f'competitions/{code}/matches',{'season':2026,'status':'FINISHED'})
            (destination/f'{code}.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
            audit['competitions'][code]={'status':'ok','rows':len(payload.get('matches',[]))}
        except Exception as exc:
            audit['competitions'][code]={'status':'failed','reason':str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__}
        (destination/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({code:audit['competitions'][code]},ensure_ascii=True),flush=True)
    print(json.dumps({'audit':str(destination/'audit.json')},ensure_ascii=True))

if __name__=='__main__':main()
