"""Retrospective diagnostics over existing temporal forecasts; no test tuning."""
import argparse,json,hashlib,sys
from pathlib import Path
import numpy as np
import pandas as pd
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from evaluate.asian_handicap_research import settle_asian_handicap
from evaluate.favorite_risk import no_vig,favorite_side,classify,risk_probabilities,binary_metrics
from evaluate.market_enhancement_ablation import build_frame
CATEGORIES=['favorite_loss','favorite_draw','win_not_full_cover','full_cover']
ARMS=['team_only','market_levels','plus_totals']
FLAGS=['team_disagrees_10pp','favorite_probability_falls_3pp','low_total_environment','deep_asian_line','high_book_disagreement']

def ci(values,dates):
    f=pd.DataFrame({'v':values,'week':pd.to_datetime(dates,utc=True).dt.strftime('%G-%V')}).groupby('week').v.agg(['sum','count']).to_numpy()
    rng=np.random.default_rng(20261020);idx=rng.integers(len(f),size=(1000,len(f)))
    return np.quantile(f[idx,0].sum(1)/f[idx,1].sum(1),[.025,.975]).tolist()

def main():
 p=argparse.ArgumentParser();p.add_argument('--output-directory',required=True);a=p.parse_args();out=R/a.output_directory;out.mkdir(parents=True,exist_ok=False)
 rawpath=R/'data/processed/historical_matches_europe_extended_candidate.csv';predpath=R/'artifacts/eval/market_enhancement_20261019_v1/predictions.csv';manifestpath=predpath.parent/'manifest.json'
 raw=pd.read_csv(rawpath,low_memory=False);pred=pd.read_csv(predpath);manifest=json.loads(manifestpath.read_text(encoding='utf-8'))
 assert hashlib.sha256(rawpath.read_bytes()).hexdigest()==manifest['source_sha256']
 assert not pred.match_id.duplicated().any()
 for fold in manifest['folds']:
  assert pd.Timestamp(fold['train_end'])<pd.Timestamp(fold['calibration_start']) and pd.Timestamp(fold['calibration_end'])<pd.Timestamp(fold['test_start'])
 frame,source_audit=build_frame(raw)
 # Prediction frame is the previously evaluated common cohort, not a new holdout.
 assert set(pred.match_id).issubset(set(frame.match_id))
 frame=frame.set_index('match_id');records=[];rejected={}
 for _,r in pred.iterrows():
  f=frame.loc[r.match_id]
  assert int(f.home_goals)==int(r.home_goals) and int(f.away_goals)==int(r.away_goals)
  assert f.home_team==r.home_team and f.away_team==r.away_team;market=np.array([r.closing_market_home_probability,r.closing_market_draw_probability,r.closing_market_away_probability]);side=favorite_side(market)
  if side is None:rejected['no_favorite_above_50pct']=rejected.get('no_favorite_above_50pct',0)+1;continue
  classified=classify(r.home_goals,r.away_goals,side,f.AHCh);d=classified['favorite_margin']
  nine={arm:r[[f'{arm}__{k}' for k in range(-4,5)]].to_numpy(dtype=float) for arm in ARMS}
  teamwin=float(nine['team_only'][np.arange(-4,5)*(1 if side==0 else -1)>0].sum())
  favkey='home' if side==0 else 'away';opening=float(f['market_'+favkey+'_probability']);over=float(f.closing_over_25_probability)
  record={'match_id':r.match_id,'date':r.date,'season':r.season,'league':r.league,'home_team':r.home_team,'away_team':r.away_team,'favorite_side':favkey,'favorite_probability':float(market[side]),'favorite_probability_band':pd.cut([market[side]],[.5,.6,.7,.8,1.000001],right=False,labels=['50-60','60-70','70-80','80-100'])[0],**classified,'home_goals':int(r.home_goals),'away_goals':int(r.away_goals),'asian_home_line':float(f.AHCh),'p_loss_market':float(market[2 if side==0 else 0]),'p_draw_market':float(market[1]),'over25_probability':over,'book_quote_count':int(f.book_quote_count),'team_disagrees_10pp':teamwin<=market[side]-.1,'favorite_probability_falls_3pp':market[side]<=opening-.03,'low_total_environment':over<=.45,'deep_asian_line':bool(classified['cover_valid'] and abs(f.AHCh)>=1.5),'high_book_disagreement':bool(f.book_quote_count>=3 and f['book_'+favkey+'_probability_std']>=.04),'integer_minus1_let_draw':d==1,'integer_minus1_let_loss':d<=0,'integer_minus2_let_draw':d==2,'integer_minus2_let_loss':d<=1}
  for arm,probs in nine.items():
   signed=np.arange(-4,5)*(1 if side==0 else -1)
   record['p_loss_'+arm]=float(probs[signed<0].sum());record['p_draw_'+arm]=float(probs[signed==0].sum())
   if classified['nine_bin_cover_supported']:
    q=risk_probabilities(probs,side,classified['full_cover_threshold']);record['p_win_not_cover_'+arm]=float(q[2]);record['p_full_cover_'+arm]=float(q[3])
  record['asian_settlement_class']=settle_asian_handicap(r.home_goals,r.away_goals,f.AHCh,side=favkey,decimal_odds=2.).result if classified['cover_valid'] else 'unavailable'
  records.append(record)
 f=pd.DataFrame(records);f.to_csv(out/'events.csv',index=False,encoding='utf-8-sig');summary={};probability_bins=[];grouped=[];flagstats=[];comparisons=[]
 for risk,target,col,reference in [('favorite_loss',f.category.eq('favorite_loss'),'p_loss_','market'),('favorite_draw',f.category.eq('favorite_draw'),'p_draw_','market'),('win_not_full_cover',f.category.eq('win_not_full_cover'),'p_win_not_cover_','market_levels')]:
  valid=f.nine_bin_cover_supported if risk=='win_not_full_cover' else pd.Series(True,index=f.index)
  q=f[valid].copy();y=target[valid].to_numpy(dtype=float);stats={};losses={}
  arms=ARMS+(['market'] if reference=='market' else [])
  for arm in arms:
   probs=q[col+arm].to_numpy(dtype=float);stats[arm]=binary_metrics(probs,y);losses[arm]=-(y*np.log(np.clip(probs,1e-15,1))+(1-y)*np.log(np.clip(1-probs,1e-15,1)))
   for low in np.arange(0,1,.1):
    mask=(probs>=low)&(probs<low+.1)
    if mask.any():probability_bins.append({'risk':risk,'arm':arm,'bin_low':float(low),'n':int(mask.sum()),'probability':float(probs[mask].mean()),'observed_rate':float(y[mask].mean())})
  summary[risk]={'denominator':len(q),'cases':int(y.sum()),'base_rate':float(y.mean()),'probability_scores':stats,'reference':reference}
  for arm in ARMS:
   diff=losses[arm]-losses[reference];comparisons.append({'risk':risk,'arm':arm,'reference':reference,'log_loss_difference':float(diff.mean()),'week_block_ci95':ci(diff,q.date),'by_season':{str(s):float(diff[q.season.to_numpy()==s].mean()) for s in sorted(q.season.unique())}})
  for group in ['favorite_probability_band','league','season','favorite_side']:
   for value,part in q.groupby(group,observed=True):
    mask=q.index.isin(part.index);grouped.append({'risk':risk,'group':group,'value':str(value),'n':len(part),'cases':int(y[mask].sum()),'rate':float(y[mask].mean()),'reference_probability':float(part[col+reference].mean())})
  for flag in FLAGS:
   for state in [False,True]:
    mask=q[flag].to_numpy()==state
    if not mask.any():continue
    yy=y[mask];pp=q.loc[mask,col+reference].to_numpy();residual=yy-pp
    flagstats.append({'risk':risk,'flag':flag,'flag_value':state,'n':int(mask.sum()),'rate':float(yy.mean()),'reference_probability':float(pp.mean()),'calibration_residual':float(residual.mean()),'residual_week_ci95':ci(residual,q.loc[mask,'date']) if int(mask.sum())>=100 else None,'insufficient_n_below_100':int(mask.sum())<100,'not_causal_or_production_rule':True})
 # Asian settlement is distinct from hypothetical Sporttery integer mapping.
 valid=f[f.cover_valid];wins=valid[valid.favorite_margin>0]
 result={'status':'completed_research_only','source_rows':len(raw),'previous_temporal_test_rows':len(pred),'favorite_events':len(f),'excluded':rejected,'asian_compatible_events':len(valid),'asian_win_not_full_cover_cases':int(valid.category.eq('win_not_full_cover').sum()),'win_not_full_cover_given_favorite_won':float(wins.category.eq('win_not_full_cover').mean()),'nine_bin_boundary_supported_events':int(f.nine_bin_cover_supported.sum()),'win_not_cover_settlement_breakdown':f.loc[f.category.eq('win_not_full_cover'),'asian_settlement_class'].value_counts().to_dict(),'integer_handicap_scenarios_no_real_quotes':{str(k):{'favorite_exactly_won_k':int((f.favorite_margin==k).sum()),'favorite_won_but_not_won_integer_handicap':int(((f.favorite_margin>0)&(f.favorite_margin<=k)).sum()),'denominator':len(f)} for k in [1,2]},'categories':summary,'comparisons':comparisons,'flag_diagnostics':flagstats,'production_changed':False,'new_model_trained':False,'real_sporttery_roi_computed':False,'prospective_validation_complete':False,'limitations':['retrospective diagnostics of already examined chronological folds; not fresh untouched holdout','historical closing archive stage lacks exact capture timestamps','favorite threshold and signals fixed before this run; no outcome-selected sample','bookmaker-panel drift may confound dispersion','unadjusted signals correlated with probability/league; not causal','many diagnostic strata, no multiple-testing-corrected discovery claims','quarter Asian half-win/push/loss differ from Sporttery three-way result','all source-history filters and form-eligible common-cohort limitations retained','injury/lineup/xG timestamps incomplete: not tested','no comparable raw market price for third-risk distribution; market_levels is learned reference']}
 (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');pd.DataFrame(grouped).to_csv(out/'strata.csv',index=False);pd.DataFrame(probability_bins).to_csv(out/'calibration_bins.csv',index=False)
 audit={'sources':{str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [rawpath,predpath,manifestpath,Path(__file__),R/'src/evaluate/favorite_risk.py']},'source_audit':source_audit,'favorite_definition':'largest non-draw no-vig closing SPF probability >= .50; exact home-away ties excluded','all_eligible_favorites_included_regardless_of_outcome':True,'prediction_temporal_folds_verified':True,'production_promotion_allowed':False}
 (out/'manifest.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
 lines=['# 热门三类风险首轮研究','基于既有四折历史代理预测，回顾性诊断；不改正式模型、金额或历史票。',f"原始{len(raw)}行；已有时间留出{len(pred)}场；按去水热门胜率≥50%纳入{len(f)}场，无论输赢全部保留。",'|风险|适用场数|发生数|发生率|参考概率来源|','|---|---:|---:|---:|---|']
 for k,v in summary.items():lines.append(f"|{k}|{v['denominator']}|{v['cases']}|{v['base_rate']:.2%}|{v['reference']}|")
 lines += [f"亚洲盘口方向一致{len(valid)}场；热门已经赢球的比赛里，未全赢亚洲让球盘占{result['win_not_full_cover_given_favorite_won']:.2%}。该口径包括半赢/走盘，不能称全部亏损，也不是实际体彩让球ROI。",'## 概率评估：Log Loss越低越好','|风险|概率来源|样本|Log Loss|Brier|观察频率−预测概率|','|---|---|---:|---:|---:|---:|']
 for risk,v in summary.items():
  for arm,s in v['probability_scores'].items():lines.append(f"|{risk}|{arm}|{s['n']}|{s['log_loss']:.6f}|{s['brier']:.6f}|{s['calibration_bias_observed_minus_predicted']:+.2%}|")
 lines+=['## 赛前信号分组（描述性，非选票规则）','|风险|信号|信号成立|样本|实际率|基准预测率|残差|','|---|---|---|---:|---:|---:|---:|']
 for v in flagstats:lines.append(f"|{v['risk']}|{v['flag']}|{v['flag_value']}|{v['n']}|{v['rate']:.2%}|{v['reference_probability']:.2%}|{v['calibration_residual']:+.2%}|")
 lines+=['区间及逐季结果见summary.json；这些是多个相关分组的探索结果，不按显著性挑选生产规则。分联赛、赛季、热门概率、主客见strata.csv；逐场概率与三类标签见events.csv；校准分箱见calibration_bins.csv。','## 限制','；'.join(result['limitations']),'下一步：保留相同固定定义，在新冻结比赛及新赛季做前瞻风险评分；需要新增规则时用训练/校准窗口预先固定，不能用本报告反复调测试阈值。联赛与杯赛、国家队仍分域；本次不增加投注或升级模型。']
 (out/'report.md').write_text('\n\n'.join(lines),encoding='utf-8');print(json.dumps({k:result[k] for k in ['favorite_events','asian_compatible_events','win_not_full_cover_given_favorite_won','categories']},ensure_ascii=False))
if __name__=='__main__':main()
