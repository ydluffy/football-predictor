"""Versioned same-cohort temporal margin ablation with untouched test seasons."""
import argparse,json,hashlib,sys
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from evaluate.market_enhancement_ablation import build_frame,fit_fold,class_metrics,aggregate_margin,target_three,HANDICAPS


def main():
    p=argparse.ArgumentParser();p.add_argument('--output-directory',required=True);a=p.parse_args();out=R/a.output_directory;out.mkdir(parents=True,exist_ok=False)
    source=R/'data/processed/historical_matches_europe_extended_candidate.csv';raw=pd.read_csv(source,low_memory=False);frame,audit=build_frame(raw)
    manifest={'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'audit':audit,'protocol':'fixed features/C=.5; prior calibration only; no production mutation','current_snapshot_speed_and_inner_outer_gap_not_in_proxy':True,'folds':[]}
    seasons=sorted(frame.season.unique());parts=[];last_models=None;last_meta=None
    for i in range(2,len(seasons)):
        train=frame[frame.season.isin(seasons[:i-1])];cal=frame[frame.season==seasons[i-1]];test=frame[frame.season==seasons[i]]
        predictions,metadata,models=fit_fold(train,cal,test);last_models,last_meta=models,metadata
        meta={'test_season':seasons[i],'train_end':train.date.max().isoformat(),'calibration_start':cal.date.min().isoformat(),'calibration_end':cal.date.max().isoformat(),'test_start':test.date.min().isoformat(),'train_rows':len(train),'calibration_rows':len(cal),'test_rows':len(test),'arms':metadata}
        manifest['folds'].append(meta)
        detail=test[['match_id','date','season','league','home_team','away_team','home_goals','away_goals','actual_margin','closing_market_home_probability','closing_market_draw_probability','closing_market_away_probability','book_quote_count']].copy()
        for name,probs in predictions.items():
            for k in range(9):detail[f'{name}__{k-4}']=probs[:,k]
        detail.to_csv(out/f'predictions_{seasons[i]}.csv',index=False);parts.append(detail)
        joblib.dump({'models':models,'metadata':meta,'production_promotion_allowed':False},out/f'frozen_models_{seasons[i]}.joblib')
        (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'completed_fold':seasons[i],'test_matches':len(test)},ensure_ascii=False),flush=True)
    f=pd.concat(parts,ignore_index=True);f.to_csv(out/'predictions.csv',index=False);margin=f.actual_margin.to_numpy();target=np.clip(margin,-4,4)+4
    arms=list(last_meta);summary={};bins=[];losses={}
    for name in arms:
        probs=f[[f'{name}__{k}' for k in range(-4,5)]].to_numpy();m,values=class_metrics(probs,target,True);losses[name]=values
        spf,_=class_metrics(aggregate_margin(probs),target_three(margin));rq={};rqll=[]
        for handicap in HANDICAPS:
            q=aggregate_margin(probs,handicap);rq[str(handicap)],v=class_metrics(q,target_three(margin,handicap));rqll.append(v['log_loss'])
        summary[name]={'margin':m,'spf':spf,'handicap':rq,'handicap_average_log_loss':float(np.mean(rqll)),'by_season':{},'by_league':{}}
        for field,section in [('season','by_season'),('league','by_league')]:
            for value in sorted(f[field].unique()):
                mask=(f[field]==value).to_numpy();summary[name][section][str(value)]=class_metrics(probs[mask],target[mask],True)[0]
        for k in range(9):
            for low in np.arange(0,1,.1):
                mask=(probs[:,k]>=low)&(probs[:,k]<low+.1)
                if mask.any():bins.append({'arm':name,'margin_bin':k-4,'bin_low':float(low),'n':int(mask.sum()),'mean_probability':float(probs[mask,k].mean()),'observed_frequency':float((target[mask]==k).mean())})
    comparisons={};parents={'team_only':'market_levels','plus_totals':'market_levels','plus_movement':'plus_totals','plus_dispersion':'plus_movement','plus_team_form':'plus_dispersion','learned_team_market_blend':'plus_dispersion'}
    weeks=pd.to_datetime(f.date,utc=True).dt.strftime('%G-%V');rng=np.random.default_rng(20261019)
    for name,parent in parents.items():
        diff=losses[name]['log_loss']-losses[parent]['log_loss'];b=pd.DataFrame({'week':weeks,'d':diff}).groupby('week').d.agg(['sum','count']).to_numpy();ix=rng.integers(len(b),size=(2000,len(b)));boot=b[ix,0].sum(axis=1)/b[ix,1].sum(axis=1)
        recent=seasons[-2:];stable=all(summary[name]['by_season'][s]['log_loss']<=summary[parent]['by_season'][s]['log_loss'] for s in recent)
        comparisons[name]={'parent':parent,'log_loss_difference':float(diff.mean()),'calendar_week_ci95':np.quantile(boot,[.025,.975]).tolist(),'rps_difference':summary[name]['margin']['rps']-summary[parent]['margin']['rps'],'ece_difference':summary[name]['margin']['top_label_ece']-summary[parent]['margin']['top_label_ece'],'last_two_seasons_not_worse':stable,'historical_signal_only':True}
    market=f[['closing_market_home_probability','closing_market_draw_probability','closing_market_away_probability']].to_numpy()
    result={'manifest':'manifest.json','test_matches':len(f),'folds':len(parts),'arms':summary,'incremental_comparisons':comparisons,'raw_closing_market_spf':class_metrics(market,target_three(margin))[0],'production_promotion_allowed':False,'prospective_validation_complete':False,'limitations':['pregame closing archive proxy without exact capture timestamps','eight outcome-filtered source odds omissions remain upstream','all arms share form-eligible common cohort','bookmaker panel changes may confound dispersion','multiple predeclared ablations; no test-set-based production selection','calibration is prior-season only; no real Sporttery ROI from proxy']}
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');pd.DataFrame(bins).to_csv(out/'reliability_bins.csv',index=False)
    lines=['# 市场增强净胜球增量实验','历史代理、同报价阶段、同比赛集合；不修改生产。',f'{len(f)}场，{len(parts)}个时间留出。','|组别|净胜球Log Loss|Brier|有序RPS|ECE|胜平负Log Loss|四档让球平均Log Loss|','|---|---:|---:|---:|---:|---:|---:|']
    for name,v in summary.items():lines.append(f"|{name}|{v['margin']['log_loss']:.6f}|{v['margin']['brier']:.6f}|{v['margin']['rps']:.6f}|{v['margin']['top_label_ece']:.6f}|{v['spf']['log_loss']:.6f}|{v['handicap_average_log_loss']:.6f}|")
    lines+=['','原始市场胜平负：'+json.dumps(result['raw_closing_market_spf'],ensure_ascii=False),'增量比较：'+json.dumps(comparisons,ensure_ascii=False),'限制：'+'；'.join(result['limitations'])]
    (out/'report.md').write_text('\n\n'.join(lines),encoding='utf-8');print(json.dumps({'completed':True,'test_matches':len(f),'summary':str(out/'summary.json')}),flush=True)


if __name__=='__main__':main()
