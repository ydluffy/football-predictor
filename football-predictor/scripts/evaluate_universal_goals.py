"""Matched market baseline and reliability diagnostics; research only."""
import argparse,json,sys
from pathlib import Path
import numpy as np
import pandas as pd
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'scripts'))
from train_universal_goals import metrics


def main():
    p=argparse.ArgumentParser();p.add_argument('--evaluation-directory',required=True);p.add_argument('--market-history',required=True);a=p.parse_args()
    directory=Path(a.evaluation_directory);pred=pd.read_csv(directory/'holdout_predictions.csv');market=pd.read_csv(a.market_history,low_memory=False)
    keys=['league','date','home_team','away_team']
    for f in (pred,market):f['date']=pd.to_datetime(f.date,utc=True,format='ISO8601').dt.floor('D')
    if market.duplicated(keys).any():raise ValueError('ambiguous market history')
    odds=['odds_home','odds_draw','odds_away'];matched=pred.merge(market[keys+odds],on=keys,how='inner',validate='one_to_one')
    v=matched[odds].apply(pd.to_numeric,errors='coerce').to_numpy();valid=np.isfinite(v).all(axis=1)&(v>1).all(axis=1);matched=matched[valid].copy();v=v[valid]
    m=1/v;m/=m.sum(axis=1,keepdims=True);q=matched[['p_home','p_draw','p_away']].to_numpy();margin=matched.home_goals.to_numpy()-matched.away_goals.to_numpy();y=np.where(margin>0,0,np.where(margin==0,1,2))
    diff=-np.log(np.clip(q[np.arange(len(y)),y],1e-15,1))+np.log(np.clip(m[np.arange(len(y)),y],1e-15,1))
    # Calendar-week cluster resampling is descriptive uncertainty, not promotion.
    blocks=matched.assign(loss_difference=diff).groupby(matched.date.dt.strftime('%G-%V')).loss_difference.agg(['sum','count']).to_numpy()
    rng=np.random.default_rng(20261019);draw=rng.integers(0,len(blocks),size=(1000,len(blocks)));boot=blocks[draw,0].sum(axis=1)/blocks[draw,1].sum(axis=1)
    bins=[]
    for name,probs in [('universal',q),('market',m)]:
        for j,label in enumerate(('home','draw','away')):
            for low in np.arange(0,1,.1):
                mask=(probs[:,j]>=low)&(probs[:,j]<low+.1)
                if mask.any():bins.append({'model':name,'class':label,'bin_low':float(low),'n':int(mask.sum()),'mean_probability':float(probs[mask,j].mean()),'observed_frequency':float((y[mask]==j).mean())})
    pd.DataFrame(bins).to_csv(directory/'reliability_bins.csv',index=False)
    result={'matched_rows':len(matched),'unmatched_or_invalid_market_rows':len(pred)-len(matched),'universal':metrics(q,y),'market':metrics(m,y),'mean_logloss_universal_minus_market':float(diff.mean()),'calendar_week_bootstrap_ci95':np.quantile(boot,[.025,.975]).tolist(),'probability_market_timestamps_exactly_aligned':False,'market_source':'historical archive odds; not live Sporttery-time comparison','prospective_validation_complete':False,'production_promotion_allowed':False,'decision':'separate_research_preview_only'}
    with (directory/'market_comparison.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps(result))


if __name__=='__main__':main()
