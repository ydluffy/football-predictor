import json,sys,os,time,hashlib,argparse
from pathlib import Path
from datetime import datetime,timezone
import pandas as pd
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from world_cup.api_football_adapter import ApiFootballClient
p=argparse.ArgumentParser();p.add_argument('--output-directory',required=True);a=p.parse_args();out=R/a.output_directory;out.mkdir(parents=True,exist_ok=False)
for raw in (R/'.env').read_text(encoding='utf-8-sig').splitlines():
 if raw.strip() and not raw.lstrip().startswith('#') and '=' in raw:
  k,v=raw.split('=',1);os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))
client=ApiFootballClient(timeout=20);audit={'sources':[],'scope':'J2 official-provider league ID99','production_changed':False};history=[];today=pd.Timestamp.now(tz='UTC').floor('D')
for season in [2024,2023,2022,2026]:
 rec={'season':season,'league_id':99}
 try:
  payload=client.get('fixtures',{'league':99,'season':season});raw=json.dumps(payload,ensure_ascii=False,indent=2);path=out/f'J2_{season}_raw.json';path.write_text(raw,encoding='utf-8');rec['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
  rec['errors']=payload.get('errors');accepted=[]
  for x in payload.get('response',[]):
   f=x['fixture'];score=x.get('goals',{});d=pd.Timestamp(f['date'])
   if x.get('league',{}).get('id')!=99 or f['status']['short']!='FT' or d>=today or score.get('home') is None or score.get('away') is None:continue
   accepted.append({'league':'J2','date':d.floor('D').isoformat(),'home_team':x['teams']['home']['name'],'away_team':x['teams']['away']['name'],'home_goals':int(score['home']),'away_goals':int(score['away'])})
  rec.update(status='ok' if accepted else 'no_usable_completed_rows',accepted_rows=len(accepted),returned_rows=len(payload.get('response',[])))
  history+=accepted
 except Exception as exc:rec.update(status='failed',error_type=type(exc).__name__)
 audit['sources'].append(rec);(out/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(rec),flush=True)
 if rec['status']=='failed' or rec.get('errors'):break
 time.sleep(6.2)
if history:
 f=pd.DataFrame(history)
 if f.duplicated(['league','date','home_team','away_team']).any():raise ValueError('duplicate J2 identity')
 f.to_csv(out/'history.csv',index=False)
audit.update(rows=len(history),freshness_for_current_inference='must_check_latest_date',not_training_ready_by_collection_alone=True);(out/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
