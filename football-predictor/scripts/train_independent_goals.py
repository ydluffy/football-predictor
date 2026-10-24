"""Time-separated training/calibration/test; research artifacts only."""
import json,sys,hashlib
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from models.independent_goals import IndependentGoals,score_distribution,aggregate,INPUT_COLUMNS
from p0.poisson import TeamAverages,compute_lambdas
OUT=R/'artifacts/eval/independent_goals_20261012';OUT.mkdir(parents=True,exist_ok=True)
SOURCE=R/'data/processed/historical_matches_europe_extended_candidate.csv'

def metrics(p,y):
    p=np.asarray(p);y=np.asarray(y,dtype=int);one=np.eye(p.shape[1])[y]
    return {'log_loss':float(-np.log(np.clip(p[np.arange(len(y)),y],1e-15,1)).mean()),'brier':float(np.square(p-one).sum(axis=1).mean())}

def rates(model,f):return [model.rates(r.home_team,r.away_team) for r in f.itertuples()]

def calibrate(rates_,f):
    targets=np.clip(f.home_goals.to_numpy()-f.away_goals.to_numpy(),-4,4).astype(int)+4
    def loss(t):return metrics([aggregate(score_distribution(*r,temperature=t)[0])[1] for r in rates_],targets)['log_loss']
    result=minimize_scalar(loss,bounds=(.6,1.8),method='bounded')
    return float(result.x)

def p0_rates(train,test):
    stats={}
    for r in train.itertuples():
        for team,gf,ga in [(r.home_team,r.home_goals,r.away_goals),(r.away_team,r.away_goals,r.home_goals)]:
            s=stats.setdefault(team,[0.,0.,0]);s[0]+=gf;s[1]+=ga;s[2]+=1
    def avg(team):
        s=stats.get(team,[1.2,1.2,1]);return TeamAverages(s[0]/s[2],s[1]/s[2],s[2])
    return [compute_lambdas(avg(r.home_team),avg(r.away_team)) for r in test.itertuples()]

def main():
    frame=pd.read_csv(SOURCE,low_memory=False);frame['date']=pd.to_datetime(frame.date)
    assert not frame.match_id.duplicated().any()
    assert frame[list(INPUT_COLUMNS)].notna().all().all()
    seasons=sorted(frame.season.unique());folds=[];records=[];manifest=[];models={}
    for league,f in frame.groupby('league',sort=True):
        for pos in range(2,len(seasons)):
            cal_season,test_season=seasons[pos-1],seasons[pos]
            train=f[f.season.isin(seasons[:pos-1])].sort_values(['date','match_id']);cal=f[f.season==cal_season];test=f[f.season==test_season]
            if not len(train) or not len(cal) or not len(test):continue
            assert train.date.max()<cal.date.min() and cal.date.max()<test.date.min()
            candidates=[]
            for penalty,half_life in [(1.,180.),(1.,365.),(10.,365.)]:
                model=IndependentGoals.fit(train,penalty,half_life); cr=rates(model,cal)
                p=[aggregate(score_distribution(*r)[0])[1] for r in cr]
                y=np.clip(cal.home_goals-cal.away_goals,-4,4).astype(int)+4
                candidates.append((metrics(p,y)['log_loss'],model,cr))
            _,model,cr=min(candidates,key=lambda x:x[0]);temperature=calibrate(cr,cal)
            pred={'raw':[],'calibrated':[],'p0':[],'market':[]};margins={'raw':[],'calibrated':[],'p0':[]};max_tail=0.
            test_rates=rates(model,test);old=p0_rates(train,test)
            for (_,row),r,old_r in zip(test.iterrows(),test_rates,old):
                entry={'match_id':row.match_id,'league':league,'test_season':test_season,'date':row.date.isoformat(),'home_team':row.home_team,'away_team':row.away_team,'home_goals':row.home_goals,'away_goals':row.away_goals,'train_through':model.trained_through,'calibration_through':cal.date.max().isoformat(),'temperature':temperature,'lambda_home':r[0],'lambda_away':r[1],'unknown_team':row.home_team not in model.teams or row.away_team not in model.teams}
                for name,rr,t in [('raw',r,1.),('calibrated',r,temperature),('p0',old_r,1.)]:
                    joint,tail=score_distribution(*rr,temperature=t);three,nine=aggregate(joint);max_tail=max(max_tail,tail)
                    pred[name].append(three);margins[name].append(nine)
                    for i,v in enumerate(three):entry[f'{name}_1x2_{i}']=v
                    for i,v in zip(range(-4,5),nine):entry[f'{name}_margin_{i}']=v
                odds=np.asarray([row.odds_home,row.odds_draw,row.odds_away],dtype=float);assert np.isfinite(odds).all() and (odds>1).all()
                market=(1/odds)/(1/odds).sum();pred['market'].append(market)
                for i,v in enumerate(market):entry[f'market_1x2_{i}']=v
                records.append(entry)
            y=np.where(test.home_goals>test.away_goals,0,np.where(test.home_goals==test.away_goals,1,2));ym=np.clip(test.home_goals-test.away_goals,-4,4).astype(int)+4
            fold={'league':league,'test_season':test_season,'train_rows':len(train),'calibration_rows':len(cal),'test_rows':len(test),'penalty':model.penalty,'half_life':model.half_life,'temperature':temperature,'max_poisson_tail_mass':max_tail,'metrics_1x2':{k:metrics(v,y) for k,v in pred.items()},'metrics_margin':{k:metrics(v,ym) for k,v in margins.items()}}
            folds.append(fold);print(json.dumps({'fold':league+' '+test_season,'test_rows':len(test)},ensure_ascii=True),flush=True)
            manifest.append({'league':league,'test_season':test_season,'train_end':train.date.max().isoformat(),'cal_start':cal.date.min().isoformat(),'cal_end':cal.date.max().isoformat(),'test_start':test.date.min().isoformat()})
        # Final research artifact uses all available historical outcomes. Its next-live
        # performance has not been tested; parameters come from last pre-test calibration.
        final=IndependentGoals.fit(f,model.penalty,model.half_life)
        models[league]={'teams':final.teams,'coefficients':final.coefficients.tolist(),'trained_through':final.trained_through,'penalty':final.penalty,'half_life':final.half_life,'temperature':temperature,'scope':'research_only_refit_all_history_not_production'}
    result=pd.DataFrame(records);result.to_csv(OUT/'holdout_predictions.csv',index=False,encoding='utf-8-sig')
    y=np.where(result.home_goals>result.away_goals,0,np.where(result.home_goals==result.away_goals,1,2));ym=np.clip(result.home_goals-result.away_goals,-4,4).astype(int)+4
    summary={'trained_at':datetime.now(timezone.utc).isoformat(),'model_id':'independent_attack_defence_poisson_v1_research','source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'source_rows':len(frame),'odds_used_in_model':False,'model_input_columns':list(INPUT_COLUMNS),'selection_and_calibration':'prior season only; model frozen before calibration and test','fold_count':len(folds),'test_rows':len(result),'unique_test_matches':result.match_id.nunique(),'metrics_1x2':{k:metrics(result[[f'{k}_1x2_{i}' for i in range(3)]],y) for k in ['raw','calibrated','p0','market']},'metrics_margin':{k:metrics(result[[f'{k}_margin_{i}' for i in range(-4,5)]],ym) for k in ['raw','calibrated','p0']},'production_promotion_allowed':False,'limitations':['independent Poisson assumption','within each test season parameters frozen; no online updates','no historical injury/lineup/xG features','market source history not exact Sporttery-time alignment','six-season source itself excludes eight missing-odds matches','final refit is not the frozen model evaluated in each fold']}
    for name,v in [('summary',summary),('folds',folds),('split_manifest',manifest),('research_models',models)]: (OUT/(name+'.json')).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
    calibration=[]
    for model in ['calibrated','p0','market']:
        for i,label in enumerate(['home','draw','away']):
            p=result[f'{model}_1x2_{i}'].to_numpy()
            for low in np.arange(0,1,.1):
                mask=(p>=low)&(p<low+.1)
                if mask.any():calibration.append({'model':model,'class':label,'bin_low':low,'n':int(mask.sum()),'mean_probability':float(p[mask].mean()),'observed_frequency':float((y[mask]==i).mean())})
    pd.DataFrame(calibration).to_csv(OUT/'reliability_bins.csv',index=False)
    lines=['# 独立进球模型第一版训练与验证','',f'历史{len(frame)}场；{len(folds)}个联赛/赛季留出，测试{len(result)}场。研究模型，未晋级。','', '|版本|胜平负Log Loss|Brier|','|---|---:|---:|']
    for k,v in summary['metrics_1x2'].items():lines.append(f'|{k}|{v["log_loss"]:.6f}|{v["brier"]:.6f}|')
    lines+=['','九档净胜球：','|版本|Log Loss|Brier|','|---|---:|---:|']
    for k,v in summary['metrics_margin'].items():lines.append(f'|{k}|{v["log_loss"]:.6f}|{v["brier"]:.6f}|')
    lines+=['','训练只读取日期、主客队和历史比分。赔率仅用作胜平负评估基线，不存在可比的市场九档分布。训练早于校准、校准早于测试；模型选择和温度仅使用校准季。','新模型学习双方进攻/防守、主场效应；较久比赛衰减，小样本向联赛均值收缩。P0使用相同训练窗口均值和原固定主场修正。温度在联合比分分布上校准后再汇总，保持玩法概率一致。','', '限制：'+ '；'.join(summary['limitations'])+'。','既有当前正式策略没有替换；不以回测ROI或一次盈利宣称优势。']
    (OUT/'report.md').write_text('\n'.join(lines),encoding='utf-8');print(json.dumps(summary,ensure_ascii=True),flush=True)

if __name__=='__main__':main()
