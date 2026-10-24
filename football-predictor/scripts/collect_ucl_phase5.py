"""Bounded current and domestic-history collection; immutable research only."""
import sys,json,time,hashlib
from pathlib import Path
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'));sys.path.insert(0,str(R/'scripts'))
from import_football_data_org_europe_incremental import _load_dotenv
from world_cup.football_data_org_adapter import FootballDataOrgClient
from strategy.ucl_domestic_research import publish_refresh_pointer
REFRESH_SEASON=2026
_load_dotenv(R/'.env');client=FootballDataOrgClient(timeout=25)
refresh='--refresh' in sys.argv
out=R/'artifacts/data/ucl_phase5_20261021';out.mkdir(exist_ok=True)
audit={'captured_at':datetime.now(timezone.utc).isoformat(),'refresh':refresh,'sources':{},'production_changed':False}
requests=[('CL',2026)]+[(c,y) for y in [2026,2023,2024,2025] for c in ['PL','BL1','FL1','SA','DED','PPL','PD']]
for code,season in requests:
 key=f'{code}_{season}';path=out/(key+'.json')
 try:
  archived=path.exists()
  if archived and not (refresh and season==REFRESH_SEASON):payload=json.loads(path.read_text(encoding='utf-8'));status='reused_archive'
  else:
   payload=client.get(f'competitions/{code}/matches',{'season':season});path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8');status='refreshed' if archived else 'archived';time.sleep(6.3)
  audit['sources'][key]={'status':status,'rows':len(payload.get('matches',[])),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
 except Exception as exc:audit['sources'][key]={'status':'failed','reason':str(exc)}
 (out/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({key:audit['sources'][key]}),flush=True)
 if audit['sources'][key].get('reason','').endswith('(network_error)'):break
if refresh:print(json.dumps({'provider_pointer':publish_refresh_pointer(R/'config/ucl_domestic_research.json',audit,datetime.now(timezone.utc).isoformat())}),flush=True)
