"""Chronological and leave-league-out validation of shared club goal model."""
import argparse, hashlib, json, sys
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.stats import poisson
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from models.universal_goals import chronological_features, fit_coefficients, expected_goals, FEATURES
from models.independent_goals import score_distribution, aggregate


def probs(rates,t):
    g=np.arange(21);m=g[:,None]-g[None,:]
    logp=(poisson.logpmf(g[None,:],rates[:,0,None])[:,:,None]+poisson.logpmf(g[None,:],rates[:,1,None])[:,None,:])/t
    logp-=logp.max(axis=(1,2),keepdims=True);p=np.exp(logp);p/=p.sum(axis=(1,2),keepdims=True)
    return np.stack([p[:,m>0].sum(axis=1),p[:,m==0].sum(axis=1),p[:,m<0].sum(axis=1)],axis=1),np.stack([p[:,np.clip(m,-4,4)==i].sum(axis=1) for i in range(-4,5)],axis=1)


def metrics(p,y):
    return {'n':len(y),'log_loss':float(-np.log(np.clip(p[np.arange(len(y)),y],1e-15,1)).mean()),'brier':float(((p-np.eye(p.shape[1])[y])**2).sum(axis=1).mean())}


def main():
    p=argparse.ArgumentParser();p.add_argument('--history',action='append',required=True);p.add_argument('--output-directory',required=True);a=p.parse_args()
    out=Path(a.output_directory);out.mkdir(parents=True,exist_ok=False)
    frames=[pd.read_csv(path,low_memory=False) for path in a.history]
    f=pd.concat(frames,ignore_index=True)
    rows,x,state,skips=chronological_features(f)
    if rows.date.max()>=pd.Timestamp.now(tz='UTC').floor('D'):
        raise ValueError('history must end before current prediction day')
    goals=rows[['home_goals','away_goals']].to_numpy();margin=goals[:,0]-goals[:,1];y=np.where(margin>0,0,np.where(margin==0,1,2));ym=np.clip(margin,-4,4)+4
    train=(rows.date<'2024-07-01').to_numpy();cal=((rows.date>='2024-07-01')&(rows.date<'2025-07-01')).to_numpy();test=(rows.date>='2025-07-01').to_numpy()
    assert min(train.sum(),cal.sum(),test.sum())>=100
    assert rows.date[train].max()<rows.date[cal].min()<rows.date[test].min()
    b=fit_coefficients(x[train],goals[train]);cr=expected_goals(x[cal],b)
    temperature=float(minimize_scalar(lambda t:metrics(probs(cr,t)[1],ym[cal])['log_loss'],bounds=(.6,1.8),method='bounded').x)
    rates=expected_goals(x[test],b);p3,p9=probs(rates,temperature)
    per_league={};transfer={}
    for league in sorted(rows.league.unique()):
        sel=(rows.league[test]==league).to_numpy()
        if sel.sum():per_league[league]={'1x2':metrics(p3[sel],y[test][sel]),'margin':metrics(p9[sel],ym[test][sel])}
        # Neither coefficient fitting nor calibration sees held-out league outcomes.
        # Its earlier outcomes are allowed only as pre-match form inputs.
        other=(rows.league!=league).to_numpy();fitmask=train&other;calmask=cal&other;tm=test&~other
        if min(fitmask.sum(),calmask.sum(),tm.sum())<100:continue
        tb=fit_coefficients(x[fitmask],goals[fitmask]);tr=expected_goals(x[calmask],tb)
        tt=float(minimize_scalar(lambda t:metrics(probs(tr,t)[1],ym[calmask])['log_loss'],bounds=(.6,1.8),method='bounded').x)
        q3,q9=probs(expected_goals(x[tm],tb),tt)
        transfer[league]={'1x2':metrics(q3,y[tm]),'margin':metrics(q9,ym[tm]),'calibration_temperature':tt,'team_form_history_used':True}
    pred=rows.loc[test].copy();pred['lambda_home']=rates[:,0];pred['lambda_away']=rates[:,1]
    for j,k in enumerate(('home','draw','away')):pred['p_'+k]=p3[:,j]
    for j in range(9):pred['margin_'+str(j-4)]=p9[:,j]
    pred.to_csv(out/'holdout_predictions.csv',index=False)
    summary={'created_at':datetime.now(timezone.utc).isoformat(),'model_id':'universal_club_form_poisson_v1_research','status':'research_only_not_live_enabled','source_hashes':{str(p):hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in a.history},'input_features':FEATURES,'odds_used':False,'train_rows':int(train.sum()),'calibration_rows':int(cal.sum()),'test_rows':int(test.sum()),'skipped_warmup_or_stale':len(skips),'1x2':metrics(p3,y[test]),'margin':metrics(p9,ym[test]),'per_league':per_league,'leave_league_out':transfer,'temperature':temperature,'coefficient_train_through':rows.date[train].max().isoformat(),'calibration_through':rows.date[cal].max().isoformat(),'test_from':rows.date[test].min().isoformat(),'historical_validation_is_retrospective':True,'production_promotion_allowed':False,'limitations':['shared form model does not measure cross-league strength','no cup or national-team validation','no historical injury lineup xG or market inputs','prior-day outcome availability assumed, no historical publication timestamps','no prospective sample or betting superiority established']}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    # Deployable research candidate is distinct from the frozen evaluated model.
    final=fit_coefficients(x,goals)
    artifact={'model_id':summary['model_id'],'features':FEATURES,'coefficients':final.tolist(),'temperature':temperature,'trained_through':rows.date.max().isoformat(),'research_only':True,'live_enabled':False,'teams':[{'league':k[0],'team':k[1],**{c:(v.isoformat() if c=='last' else v) for c,v in s.items()}} for k,s in state.teams.items()],'leagues':dict(state.leagues),'alpha':state.alpha,'prior':state.prior,'evaluated_coefficients':b.tolist()}
    (out/'model.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=True),flush=True)


if __name__=='__main__':main()
