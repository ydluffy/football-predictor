"""Chronological cross-league candidate, paired ablation, immutable artifacts."""
import sys,json,hashlib
from pathlib import Path
from collections import Counter
import numpy as np
import pandas as pd
from scipy.optimize import minimize,minimize_scalar
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'));sys.path.insert(0,str(R/'scripts'))
from models.ucl_domestic import chronological_examples,FEATURES
from models.independent_goals import score_distribution,aggregate
from data.club_history_expansion import verified_ucl_matches
from train_universal_goals import metrics
out=R/'artifacts/eval/ucl_domestic_phase5_20261021';out.mkdir(exist_ok=False)
raw=R/'artifacts/data/ucl_phase5_20261021';cutoff=pd.Timestamp.now(tz='UTC').floor('D');rows=[];rejections={};teams={};source_hashes={}
paths=sorted(raw.glob('*_20*.json'))+sorted((R/'artifacts/data/coverage_phase4_20261021').glob('CL_20*.json'))
for p in paths:
 code,season=p.stem.split('_');season=int(season);payload=json.loads(p.read_text(encoding='utf-8'));accepted,rejected=verified_ucl_matches(payload,season,cutoff)
 for r in accepted:r['competition']=code
 rows.extend(accepted);rejections[p.name]=rejected;source_hashes[str(p.relative_to(R))]=hashlib.sha256(p.read_bytes()).hexdigest()
 for m in payload.get('matches',[]):
  for side in ['homeTeam','awayTeam']:
   t=m.get(side,{})
   if t.get('id') and t.get('name'):
    k=str(t['id']);entry=teams.setdefault(k,{'id':k,'names':[],'competitions':[]})
    for key in ['name','shortName','tla']:
     if t.get(key) and t[key] not in entry['names']:entry['names'].append(t[key])
    if code not in entry['competitions']:entry['competitions'].append(code)
f=pd.DataFrame(rows);assert not f.source_match_id.duplicated().any();f.to_csv(out/'verified_history.csv',index=False)
examples,x,state,skips=chronological_examples(f);examples.to_csv(out/'feature_events.csv',index=False);np.save(out/'features.npy',x)
dates=pd.to_datetime(examples.date,utc=True);train=(examples.season==2023).to_numpy();cal=(examples.season==2024).to_numpy();test=(examples.season==2025).to_numpy();assert min(train.sum(),cal.sum(),test.sum())>=30;assert dates[train].max()<dates[cal].min() and dates[cal].max()<dates[test].min()
goals=examples[['home_goals','away_goals']].to_numpy();d=goals[:,0]-goals[:,1];labels=np.where(d>0,0,np.where(d==0,1,2));ym=np.clip(d,-4,4)+4;yt=np.minimum(goals.sum(1),7)
def fit(xx,yy):
 xx=xx.reshape(-1,6);yy=yy.reshape(-1)
 def loss(b):
  eta=xx@b;mu=np.exp(eta);return float(np.mean(mu-yy*eta)+np.sum(b[1:]**2)/(2*len(yy))),xx.T@(mu-yy)/len(yy)+np.r_[0,b[1:]/len(yy)]
 r=minimize(loss,np.zeros(6),jac=True,method='L-BFGS-B',bounds=[(-3,3)]*6)
 if not r.success:raise RuntimeError(r.message)
 return r.x

def predict(xx,b,t):
 p3=[];p9=[];pt=[]
 for h,a in np.clip(np.exp(xx@b),.1,6):
  joint,_=score_distribution(h,a,temperature=t);three,nine=aggregate(joint);i,j=np.indices(joint.shape);p3.append(three);p9.append(nine);pt.append([joint[np.minimum(i+j,7)==k].sum() for k in range(8)])
 return np.array(p3),np.array(p9),np.array(pt)
results={};models={};all_predictions=[]
for enhanced in [False,True]:
 name='elo_only' if not enhanced else 'elo_domestic_form';xx=x.copy()
 if not enhanced:xx[:,:,3:]=0
 beta=fit(xx[train],goals[train]);temp=float(minimize_scalar(lambda t:metrics(predict(xx[cal],beta,t)[1],ym[cal])['log_loss'],bounds=(.6,1.8),method='bounded').x);p3,p9,pt=predict(xx[test],beta,temp)
 results[name]={'train':int(train.sum()),'calibration':int(cal.sum()),'test':int(test.sum()),'temperature':temp,'spf':metrics(p3,labels[test]),'margin':metrics(p9,ym[test]),'total':metrics(pt,yt[test])}
 detail=examples[test].copy()
 for k,v in zip(['home','draw','away'],p3.T):detail['p_'+k]=v
 for k,v in zip(range(-4,5),p9.T):detail['margin_'+str(k)]=v
 for k,v in enumerate(pt.T):detail['total_'+str(k)]=v
 detail.to_csv(out/(name+'_holdout.csv'),index=False)
 models[name]={'coefficients':fit(xx,goals).tolist(),'evaluated_coefficients':beta.tolist(),'temperature':temp,'research_only':True}
# Do not choose by test: preserve both as separately named probability-only cohorts.
artifact={'model_id':'ucl_domestic_elo_form_phase5_research','features':FEATURES,'models':models,'state':state.as_dict(),'teams':teams,'trained_through':str(pd.to_datetime(f.date,utc=True).max()),'effective_from':pd.Timestamp.now(tz='UTC').isoformat(),'uses_market_inputs':False,'production_enabled':False}
(out/'model.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2),encoding='utf-8')
summary={'source_counts':f.groupby(['competition','season']).size().unstack(fill_value=0).to_dict(),'total_verified':len(f),'ucl_current_verified':int(((f.competition=='CL')&(f.season==2026)).sum()),'eligible_ucl_by_season':examples.groupby('season').size().to_dict(),'skips_by_reason':dict(Counter(s['reason'] for s in skips)),'skips':skips,'metrics':results,'paired_test_spf_difference':results['elo_domestic_form']['spf']['log_loss']-results['elo_only']['spf']['log_loss'],'sources':source_hashes,'rejections':rejections,'historical_market_comparator':False,'production_enabled':False,'test_previously_examined_in_phase4':True,'interpretation':'developmental historical ablation only; not untouched external validation; preserve both prospectively; no market superiority or ROI established'}
(out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in summary.items() if k in ['total_verified','ucl_current_verified','eligible_ucl_by_season','metrics','paired_test_spf_difference']},ensure_ascii=False))
