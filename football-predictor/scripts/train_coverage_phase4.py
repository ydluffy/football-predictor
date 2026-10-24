"""Separate new-league candidates; temporal calibration, no production mutation."""
import argparse,json,sys,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from models.universal_goals import chronological_features,fit_coefficients,expected_goals,FEATURES
from models.independent_goals import score_distribution,aggregate
sys.path.insert(0,str(R/'scripts'))
from train_universal_goals import probs,metrics

def main():
 p=argparse.ArgumentParser();p.add_argument('--output-directory',required=True);a=p.parse_args();out=R/a.output_directory;out.mkdir(parents=True,exist_ok=False)
 sources=[R/'artifacts/data/coverage_phase4_20261021/history.csv',R/'artifacts/data/j2_phase4_20261021/history.csv'];f=pd.concat([pd.read_csv(p) for p in sources],ignore_index=True)
 market=pd.read_csv(R/'artifacts/data/coverage_phase4_20261021/closing_markets.csv');market['date']=pd.to_datetime(market.date,utc=True,format='ISO8601').dt.floor('D')
 results={};predictions=[];artifacts={};allskips=[]
 for league,lf in f.groupby('league'):
  rows,x,state,skips=chronological_features(lf);allskips+=skips;dates=rows.date
  if league=='J2':train=(dates<'2023-01-01').to_numpy();cal=((dates>='2023-01-01')&(dates<'2024-01-01')).to_numpy();test=(dates>='2024-01-01').to_numpy()
  else:train=(dates<'2024-01-01').to_numpy();cal=((dates>='2024-01-01')&(dates<'2025-01-01')).to_numpy();test=(dates>='2025-01-01').to_numpy()
  assert min(train.sum(),cal.sum(),test.sum())>=100
  assert dates[train].max()<dates[cal].min() and dates[cal].max()<dates[test].min()
  goals=rows[['home_goals','away_goals']].to_numpy();d=goals[:,0]-goals[:,1];y=np.where(d>0,0,np.where(d==0,1,2));ym=np.clip(d,-4,4)+4
  beta=fit_coefficients(x[train],goals[train]);rates=expected_goals(x[cal],beta)
  t=float(minimize_scalar(lambda t:metrics(probs(rates,t)[1],ym[cal])['log_loss'],bounds=(.6,1.8),method='bounded').x)
  p3,p9=probs(expected_goals(x[test],beta),t);detail=rows[test].copy();detail['model_league']=league
  for k,v in zip(['home','draw','away'],p3.T):detail['p_'+k]=v
  for k,v in zip(range(-4,5),p9.T):detail['margin_'+str(k)]=v
  # Total goals scored from the very same calibrated joint distribution.
  tp=[]
  for h,a in expected_goals(x[test],beta):
   joint,_=score_distribution(h,a,temperature=t);i,j=np.indices(joint.shape);tp.append([joint[np.minimum(i+j,7)==k].sum() for k in range(8)])
  tp=np.array(tp);yt=np.minimum(goals[test].sum(1),7).astype(int)
  for k,v in enumerate(tp.T):detail['total_'+str(k)]=v
  for k in ['home','draw','away']:assert np.isfinite(detail['p_'+k]).all()
  keys=['league','date','home_team','away_team'];m=detail.merge(market,on=keys,how='left',validate='one_to_one');od=m[['odds_home','odds_draw','odds_away']].to_numpy(dtype=float);ok=np.isfinite(od).all(1)&(od>1).all(1)
  marketresult={'matched':int(ok.sum()),'source':'same-game historical closing averages; exact capture time unknown'}
  if ok.any():
   mp=1/od[ok];mp/=mp.sum(1,keepdims=True);q=m.loc[ok,['p_home','p_draw','p_away']].to_numpy();mm=m.loc[ok];md=mm.home_goals.to_numpy()-mm.away_goals.to_numpy();my=np.where(md>0,0,np.where(md==0,1,2));diff=-np.log(np.clip(q[np.arange(len(my)),my],1e-15,1))+np.log(mp[np.arange(len(my)),my]);blocks=pd.DataFrame({'week':mm.date.dt.strftime('%G-%V'),'d':diff}).groupby('week').d.agg(['sum','count']).to_numpy();rng=np.random.default_rng(20261021);ix=rng.integers(len(blocks),size=(1000,len(blocks)));boot=blocks[ix,0].sum(1)/blocks[ix,1].sum(1)
   marketresult.update(model=metrics(q,my),market=metrics(mp,my),model_minus_market_logloss=float(diff.mean()),week_block_ci95=np.quantile(boot,[.025,.975]).tolist())
  age=(pd.Timestamp.now(tz='UTC').floor('D')-dates.max()).days
  results[league]={'raw_rows':len(lf),'feature_rows':len(rows),'train':int(train.sum()),'calibration':int(cal.sum()),'test':int(test.sum()),'train_end':dates[train].max().isoformat(),'calibration_start':dates[cal].min().isoformat(),'calibration_end':dates[cal].max().isoformat(),'test_start':dates[test].min().isoformat(),'latest_history':dates.max().isoformat(),'history_age_days':int(age),'temperature':t,'spf':metrics(p3,y[test]),'margin':metrics(p9,ym[test]),'total_goals':metrics(tp,yt),'market_comparison':marketresult,'current_history_fresh':age<=120,'status':'research_candidate_no_live_routing' if age<=120 else 'historical_only_current_history_stale'}
  final=fit_coefficients(x,goals);artifacts[league]={'league':league,'model_id':'coverage_phase4_'+league+'_research','features':FEATURES,'coefficients':final.tolist(),'temperature':t,'evaluated_coefficients':beta.tolist(),'trained_through':dates.max().isoformat(),'teams':[{'league':k[0],'team':k[1],**{c:(v.isoformat() if c=='last' else v) for c,v in s.items()}} for k,s in state.teams.items()],'leagues':dict(state.leagues),'alpha':state.alpha,'prior':state.prior,'research_only':True,'production_enabled':False}
  detail.to_csv(out/(league+'_holdout_predictions.csv'),index=False);predictions.append(detail)
  print(json.dumps({'league':league,'completed':True,'test':int(test.sum()),'history_age_days':age}),flush=True)
 pd.concat(predictions,ignore_index=True).to_csv(out/'holdout_predictions.csv',index=False)
 (out/'models.json').write_text(json.dumps(artifacts,ensure_ascii=False,indent=2),encoding='utf-8')
 summary={'leagues':results,'sources':{str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},'history_skipped':len(allskips),'production_changed':False,'original_model_artifact_unchanged':True,'live_routing_enabled':False,'prospective_validation_complete':False,'limitations':['all same-day results updated after predictions','prior-day result availability is historical assumption','source date timezone/day bucket may differ from official Sporttery date','historical closing price is not live aligned odds','hyperparameters fixed; no test optimization','evaluation model and all-history refit are distinct','J2 current season access refused; no current inference permitted']}
 (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 lines=['# 英冠/日职/日乙独立候选验证','仅研究，不改变现有生产模型及今日覆盖。','|联赛|训练/校准/测试|SPF Log Loss|净胜球Log Loss|总进球Log Loss|距历史末场天数|','|---|---|---:|---:|---:|---:|']
 for league,v in results.items():lines.append(f"|{league}|{v['train']}/{v['calibration']}/{v['test']}|{v['spf']['log_loss']:.6f}|{v['margin']['log_loss']:.6f}|{v['total_goals']['log_loss']:.6f}|{v['history_age_days']}|")
 lines+=['市场对照：'+json.dumps({l:v['market_comparison'] for l,v in results.items()},ensure_ascii=False),'限制：'+'；'.join(summary['limitations'])]
 (out/'report.md').write_text('\n\n'.join(lines),encoding='utf-8')
 print(json.dumps({'completed':True,'leagues':list(results)}))
if __name__=='__main__':main()
