"""Bounded free league archive and Champions League access audit."""
import argparse,sys,json,hashlib,io,time,os
from pathlib import Path
from datetime import datetime,timezone
from urllib.request import Request,urlopen
import pandas as pd
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from data.club_history_expansion import verified_ucl_matches

def main():
 p=argparse.ArgumentParser();p.add_argument('--output-directory',required=True);a=p.parse_args();out=R/a.output_directory;out.mkdir(parents=True,exist_ok=False)
 for raw in (R/'.env').read_text(encoding='utf-8-sig').splitlines():
  if raw.strip() and not raw.lstrip().startswith('#') and '=' in raw:
   k,v=raw.split('=',1);os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))
 audit={'captured_at':datetime.now(timezone.utc).isoformat(),'sources':[],'production_changed':False};hist=[];markets=[];today=pd.Timestamp.now(tz='UTC').floor('D')
 def save(): (out/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
 def fetch(label,url,headers=None):
  record={'label':label,'url':url}
  try:
   with urlopen(Request(url,headers={'User-Agent':'football-research/1.0',**(headers or {})}),timeout=20) as res:raw=res.read();record['http_status']=res.status
   path=out/(label+('.json' if url.find('api.')>=0 or url.endswith('.json') else '.csv'));path.write_bytes(raw);record.update(status='archived',sha256=hashlib.sha256(raw).hexdigest(),path=str(path.relative_to(R)));audit['sources'].append(record);save();return raw,record
  except Exception as exc:
   record.update(status='failed',error_type=type(exc).__name__,http_status=getattr(exc,'code',None));audit['sources'].append(record);save();return None,record
 sources=[('E1_'+str(y),'E1',f'https://www.football-data.co.uk/mmz4281/{y:02d}{y+1:02d}/E1.csv') for y in range(20,27)]+[('JPN','JPN','https://www.football-data.co.uk/new/JPN.csv')]
 for label,league,url in sources:
  raw,rec=fetch(label,url)
  if raw is None:continue
  try:
   f=pd.read_csv(io.BytesIO(raw),encoding='utf-8-sig');cols=['Date','HomeTeam','AwayTeam','FTHG','FTAG'] if league=='E1' else ['Date','Home','Away','HG','AG']
   z=f[cols].copy();z.columns=['date','home_team','away_team','home_goals','away_goals'];z['date']=pd.to_datetime(z.date,dayfirst=True,utc=True,errors='coerce')
   for c in ['home_goals','away_goals']:z[c]=pd.to_numeric(z[c],errors='coerce')
   ok=z.notna().all(axis=1)&(z.date<today)&(z.date>=pd.Timestamp('2020-01-01',tz='UTC'))&(z.home_goals>=0)&(z.away_goals>=0)&(z.home_goals%1==0)&(z.away_goals%1==0)
   z=z.loc[ok].copy();z['league']=league;hist.append(z)
   if all(c in f for c in ['AvgCH','AvgCD','AvgCA']):
    m=z[['league','date','home_team','away_team']].copy()
    for c,src in zip(['odds_home','odds_draw','odds_away'],['AvgCH','AvgCD','AvgCA']):m[c]=pd.to_numeric(f.loc[ok,src],errors='coerce')
    markets.append(m)
   rec.update(parse_status='ok',accepted_rows=len(z),excluded_rows=len(f)-len(z))
  except Exception as exc:rec.update(parse_status='failed',parse_error=type(exc).__name__)
  save()
 # Small public JSON probe, no guessed dataset silently treated as valid.
 for year in [2025,2024]:
  raw,rec=fetch('J2_open_'+str(year),f'https://raw.githubusercontent.com/openfootball/football.json/master/{year}/jp.2.json')
  if raw:
   payload=json.loads(raw);rec['match_rows']=len(payload.get('matches',[]));rec['parse_status']='requires_verified_90min_schema'
  if rec.get('http_status')==404:break
 token=os.getenv('FOOTBALL_DATA_TOKEN','')
 if token:
  for season in [2025,2024,2023,2022]:
   raw,rec=fetch('CL_'+str(season),f'https://api.football-data.org/v4/competitions/CL/matches?season={season}',{'X-Auth-Token':token})
   if raw is None:break
   payload=json.loads(raw);accepted,rejected=verified_ucl_matches(payload,season,today)
   pd.DataFrame(accepted).to_csv(out/f'CL_{season}_verified_90min.csv',index=False);rec.update(accepted_90min_rows=len(accepted),excluded_not_finished_extra_time_or_invalid=sum(rejected.values()),rejection_reasons=rejected,returned_match_rows=len(payload.get('matches',[])));save();time.sleep(6.2)
 else:audit['CL_status']='token_not_configured'
 if hist:
  h=pd.concat(hist,ignore_index=True)
  if h.duplicated(['league','date','home_team','away_team']).any():raise ValueError('duplicate source identity')
  h.to_csv(out/'history.csv',index=False);audit['league_counts']=h.groupby('league').size().to_dict()
 if markets:pd.concat(markets,ignore_index=True).to_csv(out/'closing_markets.csv',index=False)
 audit['status']='finished_with_source_specific_gaps';save();print(json.dumps(audit.get('league_counts',{})))
if __name__=='__main__':main()
