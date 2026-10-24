"""New-league matched historical market checks, no model tuning on tests."""
import argparse,json,hashlib,sys
from pathlib import Path
import numpy as np
import pandas as pd
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'scripts'))
from train_universal_goals import metrics


def main():
    p=argparse.ArgumentParser();p.add_argument('--archive-directory',required=True);p.add_argument('--evaluation-directory',required=True);p.add_argument('--output-directory',required=True);a=p.parse_args()
    archive=Path(a.archive_directory);out=Path(a.output_directory);out.mkdir(parents=True,exist_ok=False)
    pred=pd.read_csv(Path(a.evaluation_directory)/'holdout_predictions.csv');pred['date']=pd.to_datetime(pred.date,utc=True).dt.floor('D')
    markets=[];sources=[]
    for source in sorted(archive.glob('0*.csv')):
        league=source.stem.split('_')[-1];f=pd.read_csv(source,encoding='utf-8-sig',low_memory=False)
        if league not in {'F2','SWE','BRA'}:continue
        keys=['Date','HomeTeam','AwayTeam'] if league=='F2' else ['Date','Home','Away']
        # Identical closing-market definition in all three leagues; never fill
        # missing closing odds from opening odds or a different bookmaker.
        odds=['AvgCH','AvgCD','AvgCA']
        z=f[keys+odds].copy();z.columns=['date','home_team','away_team','odds_home','odds_draw','odds_away']
        z['date']=pd.to_datetime(z.date,dayfirst=True,utc=True,errors='coerce').dt.floor('D');z['league']=league;z['source_file']=source.name
        markets.append(z);sources.append({'file':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'price_columns':odds})
    market=pd.concat(markets,ignore_index=True);keys=['league','date','home_team','away_team']
    if market.duplicated(keys).any():raise ValueError('duplicate market identity')
    results={};bins=[];details=[]
    for league in ('F2','SWE','BRA'):
        universe=pred[pred.league==league];m=universe.merge(market,on=keys,how='left',validate='one_to_one')
        odds=m[['odds_home','odds_draw','odds_away']].apply(pd.to_numeric,errors='coerce').to_numpy();valid=np.isfinite(odds).all(axis=1)&(odds>1).all(axis=1)
        m=m[valid].copy();odds=odds[valid]
        if not len(m):results[league]={'status':'no_valid_comparable_market','test_rows':len(universe)};continue
        marketp=1/odds;marketp/=marketp.sum(axis=1,keepdims=True);q=m[['p_home','p_draw','p_away']].to_numpy();delta=m.home_goals.to_numpy()-m.away_goals.to_numpy();y=np.where(delta>0,0,np.where(delta==0,1,2))
        d=-np.log(q[np.arange(len(y)),y])+np.log(marketp[np.arange(len(y)),y]);blocks=m.assign(d=d).groupby(m.date.dt.strftime('%G-%V')).d.agg(['sum','count']).to_numpy()
        rng=np.random.default_rng(20261019);ix=rng.integers(len(blocks),size=(1000,len(blocks)));b=blocks[ix,0].sum(axis=1)/blocks[ix,1].sum(axis=1)
        results[league]={'test_rows':len(universe),'matched_rows':len(m),'missing_or_invalid_market_rows':len(universe)-len(m),'universal':metrics(q,y),'market':metrics(marketp,y),'logloss_difference':float(d.mean()),'calendar_week_ci95':np.quantile(b,[.025,.975]).tolist(),'by_calendar_year':{str(year):{'n':int(mask.sum()),'universal':metrics(q[mask],y[mask]),'market':metrics(marketp[mask],y[mask])} for year in sorted(m.date.dt.year.unique()) for mask in [(m.date.dt.year==year).to_numpy()]},'decision':'prospective_shadow_only_not_production'}
        for name,probs in [('universal',q),('market',marketp)]:
            for j,label in enumerate(('home','draw','away')):
                for low in np.arange(0,1,.1):
                    mask=(probs[:,j]>=low)&(probs[:,j]<low+.1)
                    if mask.any():bins.append({'league':league,'model':name,'class':label,'bin_low':float(low),'n':int(mask.sum()),'mean_probability':float(probs[mask,j].mean()),'observed_frequency':float((y[mask]==j).mean())})
        for j,k in enumerate(('home','draw','away')):m['market_p_'+k]=marketp[:,j]
        details.append(m)
    pd.concat(details,ignore_index=True).to_csv(out/'matched_predictions.csv',index=False);pd.DataFrame(bins).to_csv(out/'reliability_bins.csv',index=False)
    audit={'sources':sources,'price_definition':'multi-bookmaker mean pregame closing archive proxy','exact_historical_capture_timestamps_available':False,'training_prices_used':False,'model_refit_or_calibration_performed':False,'leagues':results,'production_promotion_allowed':False,'limitation':'Retrospective league diagnostics; historical proxy is not same-time Sporttery and cannot establish betting advantage.'}
    (out/'summary.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(results,ensure_ascii=False))


if __name__=='__main__':main()
