"""Probability-only UCL research; exact identities, dated provider fixture gate."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from models.ucl_domestic import ClubState
from models.independent_goals import score_distribution,aggregate
from strategy.goal_distribution_tracking import forecast_fields,NAMES
from data.competition_registry import load_team_alias_registry,normalize_alias

def publish_refresh_pointer(config_path,audit,captured_at):
 """Move the 24h freshness pointer after a real archive refresh; a failed fetch must never advance it."""
 source=audit.get('sources',{}).get('CL_2026',{})
 if source.get('status') not in ('archived','refreshed'):return {'updated':False,'reason':'provider_archive_not_refreshed'}
 config_path=Path(config_path);cfg=json.loads(config_path.read_text(encoding='utf-8'))
 cfg['provider_captured_at']=captured_at
 config_path.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 return {'updated':True,'provider_captured_at':captured_at}

def identity_index(teams,registry=None):
 registry=registry or load_team_alias_registry();index={}
 for ident,t in teams.items():
  # TLA abbreviations alone do not provide sufficient identity evidence.
  for name in t['names']:
   if len(name)<=3:continue
   key=normalize_alias(registry.resolve(name) or name);index.setdefault(key,set()).add(str(ident))
 return index

def resolve_team(name,index,registry=None):
 registry=registry or load_team_alias_registry();ids=index.get(normalize_alias(registry.resolve(name) or name),set())
 return next(iter(ids)) if len(ids)==1 else None

def predictions(scan,artifact,provider,now,reviewed_aliases=None):
 now=pd.Timestamp(now);registry=load_team_alias_registry();index=identity_index(artifact['teams'],registry);state=ClubState.restore(artifact['state']);rows=[];skips=[]
 for alias,ident in (reviewed_aliases or {}).items():
  if str(ident) not in artifact['teams']:raise ValueError('reviewed alias ID absent from provider archive')
  key=normalize_alias(registry.resolve(alias) or alias);existing=index.get(key,set())
  if existing and existing!={str(ident)}:raise ValueError('reviewed alias conflicts with registered identity')
  index[key]={str(ident)}
 if pd.Timestamp(artifact['trained_through'])>=now:raise ValueError('training must precede prediction')
 for f in scan['fixtures']:
  n=f['match_number'];base={'match_id':f['match_id'],'match_number':n,'home_team':f['home_team'],'away_team':f['away_team'],'kickoff_time':f['kickoff'],'prediction_at':now.isoformat(),'probability_source':'independent_club_history_no_market','model_id':artifact['model_id']}
  if f.get('competition_id')!='UEFA_CHAMPIONS_LEAGUE':skips.append({**base,'reason':'not_champions_league'});continue
  if f.get('sale_status')!='on_sale' or pd.Timestamp(f['kickoff'])<=now:skips.append({**base,'reason':'not_on_sale_or_started'});continue
  home=resolve_team(f['home_team'],index,registry);away=resolve_team(f['away_team'],index,registry)
  if home is None or away is None or home==away:skips.append({**base,'reason':'unknown_or_ambiguous_provider_identity'});continue
  matches=[m for m in provider.get('matches',[]) if str(m.get('homeTeam',{}).get('id'))==home and str(m.get('awayTeam',{}).get('id'))==away and abs((pd.Timestamp(m['utcDate'])-pd.Timestamp(f['kickoff'])).total_seconds())<=300]
  if len(matches)!=1:skips.append({**base,'reason':'provider_fixture_or_kickoff_mismatch','home_provider_id':home,'away_provider_id':away});continue
  if matches[0]['status'] not in ['SCHEDULED','TIMED']:skips.append({**base,'reason':'provider_fixture_not_prematch'});continue
  x,reason=state.features(home,away,now)
  if reason:skips.append({**base,'reason':reason});continue
  for name,m in artifact['models'].items():
   xx=x.copy()
   if name=='elo_only':xx[:,3:]=0
   rates=np.clip(np.exp(xx@np.array(m['coefficients'])),.1,6);joint,_=score_distribution(*rates,temperature=m['temperature']);p3,p9=aggregate(joint)
   rows.append({**base,'candidate':name,'handicap_model_id':artifact['model_id']+'|'+name,'home_provider_id':home,'away_provider_id':away,'source_match_id':matches[0]['id'],'p_home':float(p3[0]),'p_draw':float(p3[1]),'p_away':float(p3[2]),**{'margin_probability_'+k:float(v) for k,v in zip(NAMES,p9)},**forecast_fields(joint)})
 return rows,skips
