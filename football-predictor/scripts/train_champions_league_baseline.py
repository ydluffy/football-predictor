"""First UCL-only independent baseline, stable provider IDs, strict season holdout."""
import argparse,json,sys,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'));sys.path.insert(0,str(R/'scripts'))
from models.independent_goals import IndependentGoals,score_distribution,aggregate
from train_universal_goals import metrics

def main():
 p=argparse.ArgumentParser();p.add_argument('--output-directory',required=True);a=p.parse_args();out=R/a.output_directory;out.mkdir(parents=True,exist_ok=False)
 sources=sorted((R/'artifacts/data/coverage_phase4_20261021').glob('CL_*_verified_90min.csv'));f=pd.concat([pd.read_csv(p) for p in sources],ignore_index=True)
 assert not f.source_match_id.duplicated().any();f['date']=pd.to_datetime(f.date,utc=True,format='ISO8601');assert (f.date<pd.Timestamp.now(tz='UTC').floor('D')).all()
 excluded_finals=int((f.stage=='FINAL').sum());f=f[f.stage!='FINAL'].copy()
 # No borrowing a domestic league strength scale: directly fit UCL opponent links.
 names={str(int(r.home_id)):r.home_team for r in f.itertuples()};names.update({str(int(r.away_id)):r.away_team for r in f.itertuples()})
 f['home_team']=f.home_id.map(lambda v:'fdorg:'+str(int(v)));f['away_team']=f.away_id.map(lambda v:'fdorg:'+str(int(v)))
 train=f[f.season==2023];cal=f[f.season==2024];test=f[f.season==2025];assert train.date.max()<cal.date.min() and cal.date.max()<test.date.min()
 counts=pd.concat([train.home_team,train.away_team]).value_counts();known=set(counts[counts>=5].index)
 eligible=lambda part:part[part.home_team.isin(known)&part.away_team.isin(known)].copy()
 c=eligible(cal);t=eligible(test);audit={'source_rows':len(f),'train_rows':len(train),'calibration_rows':len(c),'calibration_identity_or_history_skips':len(cal)-len(c),'test_rows':len(t),'test_identity_or_history_skips':len(test)-len(t),'excluded_neutral_finals':excluded_finals,'model_inputs':'UCL past scores and stable provider club IDs only; no odds','production_changed':False,'live_routing_enabled':False,'history_threshold_per_team':5,'market_comparison_available':False}
 if min(len(train),len(c),len(t))<30:
  audit['status']='blocked_insufficient_strict_holdout_coverage';(out/'summary.json').write_text(json.dumps(audit,indent=2),encoding='utf-8');print(json.dumps(audit));return
 model=IndependentGoals.fit(train,penalty=1.,half_life=365.)
 def predict(part,temp):
  three=[];nine=[];total=[]
  for r in part.itertuples():
   joint,_=score_distribution(*model.rates(r.home_team,r.away_team),temperature=temp);p3,p9=aggregate(joint);i,j=np.indices(joint.shape);three.append(p3);nine.append(p9);total.append([joint[np.minimum(i+j,7)==k].sum() for k in range(8)])
  return np.array(three),np.array(nine),np.array(total)
 cm=np.clip(c.home_goals.to_numpy()-c.away_goals.to_numpy(),-4,4)+4
 temp=float(minimize_scalar(lambda z:metrics(predict(c,z)[1],cm)['log_loss'],bounds=(.6,1.8),method='bounded').x)
 p3,p9,pt=predict(t,temp);d=t.home_goals.to_numpy()-t.away_goals.to_numpy();y=np.where(d>0,0,np.where(d==0,1,2));ym=np.clip(d,-4,4)+4;yt=np.minimum(t.home_goals.to_numpy()+t.away_goals.to_numpy(),7)
 prior=(train.home_goals>train.away_goals).mean(),(train.home_goals==train.away_goals).mean(),(train.home_goals<train.away_goals).mean()
 audit.update(status='trained_research_baseline_not_production',temperature=temp,spf=metrics(p3,y),margin=metrics(p9,ym),total_goals=metrics(pt,yt),train_only_frequency_baseline=metrics(np.tile(prior,(len(t),1)),y),train_end=train.date.max().isoformat(),calibration_start=c.date.min().isoformat(),calibration_end=c.date.max().isoformat(),test_start=t.date.min().isoformat(),test_end=t.date.max().isoformat(),sources={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},limitations=['one strict season holdout; only clubs seen five times in initial training','no historical market prices: cannot establish market superiority or ROI','neutral finals excluded; no domestic-strength/lineup/xG input','full-history refit is not the evaluated model','no automatic live coverage; stable ID mapping and future prospective validation required'])
 detail=t.copy()
 for k,v in zip(['home','draw','away'],p3.T):detail['p_'+k]=v
 for k,v in zip(range(-4,5),p9.T):detail['margin_'+str(k)]=v
 for k,v in enumerate(pt.T):detail['total_'+str(k)]=v
 detail.to_csv(out/'holdout_predictions.csv',index=False)
 final=IndependentGoals.fit(f,penalty=1.,half_life=365.)
 artifact={'model_id':'ucl_attack_defence_baseline_v1_research','teams':final.teams,'coefficients':final.coefficients.tolist(),'trained_through':final.trained_through,'penalty':final.penalty,'half_life':final.half_life,'temperature':temp,'provider_team_names':names,'research_only':True,'production_enabled':False,'evaluated_teams':model.teams,'evaluated_coefficients':model.coefficients.tolist()}
 (out/'model.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2),encoding='utf-8');(out/'summary.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(audit,ensure_ascii=False))
if __name__=='__main__':main()
