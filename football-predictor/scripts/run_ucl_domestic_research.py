"""Separate zero-budget prospective freeze/score; cannot produce tickets."""
import argparse,json,sys,hashlib,re
from pathlib import Path
import pandas as pd
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'));sys.path.insert(0,str(R/'scripts'))
from strategy.ucl_domestic_research import predictions
from strategy.goal_distribution_tracking import score_goals
from strategy.universal_comparison import score_snapshot
from models.independent_goals import handicap_probability
from strategy.goal_distribution_tracking import NAMES
import math
from run_october_research import freeze,write_new,digest
from strategy.october_research import timestamp
p=argparse.ArgumentParser();p.add_argument('stage',choices=['check','freeze','settle-pending']);p.add_argument('--scan-json',type=Path);p.add_argument('--market-csv',type=Path);p.add_argument('--gate-json',type=Path);p.add_argument('--sales-day');p.add_argument('--batch-id');p.add_argument('--results-csv',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
cfg=json.loads((R/'config/ucl_domestic_research.json').read_text(encoding='utf-8'));directory=R/'artifacts/data/ucl_domestic_comparison';now=pd.Timestamp.now(tz='UTC')
if a.stage=='settle-pending':
 results=pd.read_csv(a.results_csv,dtype=str).fillna('').to_dict('records');output=[]
 for target in directory.glob('20*.json'):
  snap=json.loads(target.read_text(encoding='utf-8'))
  if snap.get('protocol_version')!='ucl_domestic_probability_only_v1' or pd.Timestamp(snap['sales_day']).date()>=now.tz_convert('Asia/Shanghai').date():continue
  review={'candidates':{},'simulation_stake':0,'snapshot_sha256':digest(target),'results_sha256':digest(a.results_csv),'reviewed_at':now.isoformat()}
  for name in ['elo_only','elo_domestic_form']:
   subset=[m for m in snap['matches'] if m['candidate']==name];review['candidates'][name]=score_snapshot({'matches':subset,'experiments':[],'protocol_version':'ucl_domestic_probability_only_v1','cohort':name},results)
  codehash=hashlib.sha256((digest(Path(__file__))+digest(R/'src/strategy/goal_distribution_tracking.py')+digest(R/'src/strategy/universal_comparison.py')).encode()).hexdigest();out=directory/'reviews'/f'{target.stem}_{digest(a.results_csv)[:16]}_{codehash[:8]}.json';review['scoring_code_sha256']=codehash
  if not out.exists():write_new(out,review)
  output.append(str(out))
 print(json.dumps({'reviews':output}));sys.exit(0)
if not a.scan_json:p.error('scan required')
model=R/cfg['model_artifact'];provider=R/cfg['provider_fixtures'];scan=json.loads(a.scan_json.read_text(encoding='utf-8-sig'));artifact=json.loads(model.read_text(encoding='utf-8'));payload=json.loads(provider.read_text(encoding='utf-8'))
if a.stage=='check':
 rows,skips=predictions(scan,artifact,payload,now,cfg.get('reviewed_aliases'));result={'checked_at':now.isoformat(),'forecast_freeze_performed':False,'covered_matches':sorted(set(r['match_number'] for r in rows)),'skips':skips,'simulation_stake':0}
 if a.output:a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(result,ensure_ascii=False));sys.exit(0)
if not cfg['prospective_enabled']:raise ValueError('prospective cohort disabled')
if not a.batch_id or not re.fullmatch(r'[A-Za-z0-9_-]+',a.batch_id):raise ValueError('safe batch ID required')
hashes={k:digest(v) for k,v in {'scan_sha256':a.scan_json,'market_sha256':a.market_csv,'gate_sha256':a.gate_json}.items()};out=directory/f'{a.sales_day}_{a.batch_id}.json'
if out.exists():
 old=json.loads(out.read_text(encoding='utf-8'))
 if any(old[k]!=v for k,v in hashes.items()):raise ValueError('immutable UCL snapshot input changed')
 print(json.dumps({'snapshot':str(out),'idempotent':True}));sys.exit(0)
gate=json.loads(a.gate_json.read_text(encoding='utf-8'));markets=pd.read_csv(a.market_csv,dtype=str).fillna('').to_dict('records');validated=freeze(markets,gate,now,{'mode':'simulation_only','real_money_allowed':False,'effective_from':cfg['effective_from']})
expected=set(gate['expected_match_numbers']);numbers={f['match_number'] for f in scan['fixtures']}
if numbers!=expected or scan['sales_day']!=a.sales_day:raise ValueError('exact batch scan scope required')
if (now-pd.Timestamp(cfg['provider_captured_at'])).total_seconds()>86400:raise ValueError('provider fixture archive stale; refresh before research')
rows,skips=predictions(scan,artifact,payload,now,cfg.get('reviewed_aliases'))
for row in rows:
 market=[m for m in validated if m['match_number']==row['match_number'] and m['home_team']==row['home_team'] and m['away_team']==row['away_team'] and timestamp(m['kickoff_time'])==timestamp(row['kickoff_time'])]
 if len(market)!=1:raise ValueError('market identity mismatch')
 market=market[0];row['home_handicap']=market['home_handicap'];row['comparison_probabilities']={}
 for play in ['spf','rqspf']:
  try:
   odds=[float(market[f'{play}_odds_{k}']) for k in ['home','draw','away']]
   if not all(math.isfinite(v) and v>1 for v in odds):raise ValueError('missing odds')
   q=[1/v for v in odds];q=[v/sum(q) for v in q]
   prob=[row['p_'+k] for k in ['home','draw','away']] if play=='spf' else handicap_probability([row['margin_probability_'+k] for k in NAMES],float(row['home_handicap']))
   row['comparison_probabilities'][play]={'market':q,'independent':list(prob),'fusion':[(v+w)/2 for v,w in zip(q,prob)]}
  except (ValueError,KeyError,TypeError):skips.append({'match_number':row['match_number'],'play':play,'candidate':row['candidate'],'reason':'missing_odds_or_unsupported_handicap'})
# Fresh gate recheck immediately before immutable write.
freeze(markets,gate,pd.Timestamp.now(tz='UTC'),{'mode':'simulation_only','real_money_allowed':False,'effective_from':cfg['effective_from']})
result={**hashes,'model_sha256':digest(model),'provider_sha256':digest(provider),'protocol_version':'ucl_domestic_probability_only_v1','sales_day':a.sales_day,'batch_id':a.batch_id,'frozen_at':now.isoformat(),'matches':rows,'skips':skips,'experiments':[],'simulation_stake':0,'production_probability_change_allowed':False,'status':'frozen' if rows else 'coverage_skipped'}
write_new(out,result);out.with_suffix('.md').write_text('# 欧冠跨联赛概率研究（预算0）\n\n'+json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'snapshot':str(out),'covered_matches':len(set(r['match_number'] for r in rows)),'status':result['status']}))
