"""Small-sample real same-time probability-gap ablation; no live deployment."""
import argparse,json,hashlib,sys
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from threadpoolctl import threadpool_limits
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from evaluate.market_enhancement_ablation import make_model,calibrate,temperature,class_metrics,aggregate_margin,target_three
from evaluate.sporttery_handicap_model import aligned_margin_probabilities

BASE=('official_handicap','official_spf_home','official_spf_draw','official_spf_away','official_rq_home','official_rq_draw','official_rq_away')
GAP=('probability_gap_home','probability_gap_draw','probability_gap_away')
ASIAN_TOTALS=('outer_primary_line','outer_home_price_share','outer_total_line','outer_over_price_share')
QUALITY=('h2h_dispersion','quote_count','time_delta_minutes','minutes_to_kickoff')
CHANGES=('provider_reported_line_delta','provider_reported_price_delta','observed_line_strength_per_hour','observed_common_books')
GROUPS={'official_only':BASE,'plus_same_time_probability_gap':BASE+GAP,'plus_asian_totals':BASE+GAP+ASIAN_TOTALS,'plus_disagreement_quality':BASE+GAP+ASIAN_TOTALS+QUALITY,'plus_changes':BASE+GAP+ASIAN_TOTALS+QUALITY+CHANGES}


def temporal_split(frame):
    dates=sorted(frame.sales_day.unique());first=max(1,int(len(dates)*.6));second=max(first+1,int(len(dates)*.8))
    train=frame[frame.sales_day.isin(dates[:first])].copy();cal=frame[frame.sales_day.isin(dates[first:second])].copy();test=frame[frame.sales_day.isin(dates[second:])].copy()
    if min(len(train),len(cal),len(test))==0:raise ValueError('empty temporal split')
    # Conservative publication proxy: a training/calibration kickoff must be
    # at least three hours earlier than the next partition's first forecast.
    train=train[train.kickoff_at+pd.Timedelta(hours=3)<cal['at'].min()]
    cal=cal[cal.kickoff_at+pd.Timedelta(hours=3)<test['at'].min()]
    if len(train)<120 or len(cal)<30 or len(test)<30:raise ValueError('insufficient disjoint train/calibration/test events')
    assert train.kickoff_at.max()+pd.Timedelta(hours=3)<cal['at'].min()
    assert cal.kickoff_at.max()+pd.Timedelta(hours=3)<test['at'].min()
    return train,cal,test


def main():
    p=argparse.ArgumentParser();p.add_argument('--dataset-directory',required=True);p.add_argument('--output-directory',required=True);a=p.parse_args();dataset=R/a.dataset_directory;out=R/a.output_directory;out.mkdir(parents=True,exist_ok=False)
    audit=json.loads((dataset/'audit.json').read_text(encoding='utf-8'));f=pd.read_csv(dataset/'events.csv');f=f[f.label_status=='official_completed_unique'].copy()
    result={'dataset_sha256':hashlib.sha256((dataset/'events.csv').read_bytes()).hexdigest(),'labelled_events':len(f),'min_labelled_events':300,'production_promotion_allowed':False,'prospective_evidence':False,'protocol':'latest safe event, fixed C=.5, prior-only margin calibration; no test tuning','source_audit':str(dataset/'audit.json')}
    if len(f)<300:
        result.update(status='blocked_insufficient_labelled_unique_events',missing_events=300-len(f));(out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result));return
    f['at']=pd.to_datetime(f.prediction_at,utc=True,format='ISO8601');f['kickoff_at']=pd.to_datetime(f.kickoff,utc=True,format='ISO8601');f['margin_class']=f.actual_margin.astype(int).clip(-4,4)
    try:train,cal,test=temporal_split(f)
    except ValueError as exc:
        result.update(status='blocked_temporal_sample_shortfall',reason=str(exc));(out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result));return
    support=train.margin_class.value_counts().reindex(range(-4,5),fill_value=0)
    if (support<5).any():
        result.update(status='blocked_training_tail_class_support',class_counts={str(k):int(v) for k,v in support.items()});(out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result));return
    result['split']={'train_rows':len(train),'calibration_rows':len(cal),'test_rows':len(test),'train_forecast_end':train['at'].max().isoformat(),'train_last_kickoff':train.kickoff_at.max().isoformat(),'calibration_forecast_start':cal['at'].min().isoformat(),'calibration_last_kickoff':cal.kickoff_at.max().isoformat(),'test_forecast_start':test['at'].min().isoformat(),'train_sales_days':sorted(train.sales_day.unique()),'calibration_sales_days':sorted(cal.sales_day.unique()),'test_sales_days':sorted(test.sales_day.unique())}
    margin=test.actual_margin.to_numpy();y=np.clip(margin,-4,4).astype(int)+4;yc=cal.margin_class.to_numpy()+4;models={};arms={};losses={};detail=test[['match_id','sales_day','league','actual_margin','prediction_at']].copy()
    with threadpool_limits(limits=1):
        for name,features in GROUPS.items():
            model=make_model(features).fit(train,train.margin_class)
            if model.named_steps['model'].n_iter_.max()>=1500:raise ValueError('model did not converge')
            t=calibrate(aligned_margin_probabilities(model,cal),yc);q=temperature(aligned_margin_probabilities(model,test),t)
            m,values=class_metrics(q,y,True);losses[name]=values['log_loss']
            spf=class_metrics(aggregate_margin(q),target_three(margin))[0]
            handicap=test.official_handicap.to_numpy();rq=np.stack([aggregate_margin(q[i:i+1],handicap[i])[0] for i in range(len(q))]);rqscore=class_metrics(rq,target_three(margin,handicap))[0]
            arms[name]={'margin':m,'spf':spf,'rqspf':rqscore,'temperature':t,'features':features};models[name]={'pipeline':model,'temperature':t}
            for k in range(9):detail[f'{name}__{k-4}']=q[:,k]
    result['arms']=arms;result['raw_official_spf']=class_metrics(test[['official_spf_'+k for k in ('home','draw','away')]].to_numpy(),target_three(margin))[0]
    result['raw_official_rqspf']=class_metrics(test[['official_rq_'+k for k in ('home','draw','away')]].to_numpy(),target_three(margin,test.official_handicap.to_numpy()))[0]
    comparisons={};names=list(GROUPS);rng=np.random.default_rng(20261019)
    for j,name in enumerate(names[1:],1):
        parent=names[j-1];diff=losses[name]-losses[parent];g=pd.DataFrame({'date':test.sales_day,'d':diff}).groupby('date').d.agg(['sum','count']).to_numpy();ix=rng.integers(len(g),size=(2000,len(g)));boot=g[ix,0].sum(axis=1)/g[ix,1].sum(axis=1)
        comparisons[name]={'parent':parent,'log_loss_difference':float(diff.mean()),'sales_day_bootstrap_ci95':np.quantile(boot,[.025,.975]).tolist(),'independent_test_sales_days':len(g)}
    result.update(status='retrospective_development_test_complete',incremental_comparisons=comparisons,limitations=['small dataset; no prospective evaluation','source opening timestamp not known; provider delta is not observed speed','provider last-update age not available','same-stage probability gaps are SPF-vs-SPF only','no real ROI or production promotion','three-hour result-availability proxy is not a historical publication log'])
    detail.to_csv(out/'predictions.csv',index=False);joblib.dump({'models':models,'split':result['split'],'production_promotion_allowed':False},out/'frozen_development_models.joblib')
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
