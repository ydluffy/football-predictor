"""Freeze/settle independent-model controls behind the existing official gate."""
import argparse,json,sys,subprocess,re,math
from pathlib import Path
import pandas as pd
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from run_october_research import freeze,digest,write_new
from strategy.october_research import settle,timestamp
from strategy.independent_comparison import build_comparison
from universal_controller_hook import run_hook
from ucl_research_hook import run_hook as _ucl_hook
from strategy.goal_distribution_tracking import score_goals

def ucl_hook(stage,arguments):
    try:_ucl_hook(stage,arguments)
    except Exception as exc:
        audit=R/'artifacts/data/ucl_domestic_comparison/audits';audit.mkdir(parents=True,exist_ok=True)
        stamp=pd.Timestamp.now(tz='UTC').strftime('%Y%m%dT%H%M%S%fZ')
        write_new(audit/f'{stamp}_hook_error.json',{'stage':stage,'status':'failed','reason':str(exc),'production_blocked':False})
        print(json.dumps({'ucl_research_hook':'failed','reason':str(exc)}))


def universal_hook(stage,arguments):
    try:run_hook(stage,arguments)
    except Exception as exc:
        # Original frozen research/production remains valid; persist hook errors.
        audit=R/'artifacts/data/universal_comparison/audits';audit.mkdir(parents=True,exist_ok=True)
        stamp=pd.Timestamp.now(tz='UTC').strftime('%Y%m%dT%H%M%S%fZ')
        write_new(audit/f'{stamp}_hook_error.json',{'stage':stage,'status':'failed','error_type':type(exc).__name__,'reason':str(exc),'production_blocked':False})
        print(json.dumps({'universal_research_hook':'failed','error_type':type(exc).__name__}))

def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['freeze','settle']);p.add_argument('--sales-day');p.add_argument('--batch-id');p.add_argument('--scan-json',type=Path);p.add_argument('--market-csv',type=Path);p.add_argument('--gate-json',type=Path);p.add_argument('--snapshot',type=Path);p.add_argument('--results-csv',type=Path);a=p.parse_args();now=pd.Timestamp.now(tz='Asia/Shanghai');directory=R/'artifacts/data/independent_comparison'
    if a.stage=='settle':
        snapshot=json.loads(a.snapshot.read_text(encoding='utf-8'));results=pd.read_csv(a.results_csv,dtype=str).fillna('').to_dict('records');review=settle(snapshot,results)
        probability_scores=[]
        for m in snapshot['matches']:
            rs=[r for r in results if str(r['match_number']).endswith(m['match_number']) and r['home_team']==m['home_team'] and r['away_team']==m['away_team'] and r['date']==timestamp(m['kickoff_time']).date().isoformat() and r.get('status') in {'已完成','finished','completed'}]
            if len(rs)!=1 or not re.fullmatch(r'\d+[:：]\d+',rs[0]['full_time_score']):continue
            h,away=map(int,re.split('[:：]',rs[0]['full_time_score']))
            for play,arms in m.get('comparison_probabilities',{}).items():
                margin=h-away+(float(m['home_handicap']) if play=='rqspf' else 0);target=0 if margin>0 else 2 if margin<0 else 1
                for arm,probs in arms.items():probability_scores.append({'match_number':m['match_number'],'play':play,'arm':arm,'log_loss':-math.log(max(probs[target],1e-15)),'brier':sum((v-(i==target))**2 for i,v in enumerate(probs))})
        review['comparison_probability_scores']=probability_scores
        review['goal_distribution_review']=score_goals(snapshot['matches'],results)
        # Winner-only ROI is not a fair comparison: pending observations stay pending.
        review.update(reviewed_at=now.isoformat(),snapshot_sha256=digest(a.snapshot),results_sha256=digest(a.results_csv),allocations=snapshot['allocations'])
        review['settlement_engine_sha256']=__import__('hashlib').sha256((''.join(digest(q) for q in [R/'src/strategy/october_research.py',Path(__file__),R/'src/strategy/goal_distribution_tracking.py'])).encode()).hexdigest()
        out=directory/'reviews'/f'{a.snapshot.stem}_{digest(a.results_csv)[:16]}_{review["settlement_engine_sha256"][:8]}.json'
        if not out.exists():write_new(out,review)
        universal_hook('settle-pending',['--results-csv',a.results_csv])
        ucl_hook('settle-pending',['--results-csv',a.results_csv])
        print(json.dumps({'review':str(out),'pending':len(review['pending'])},ensure_ascii=True));return
    if not a.sales_day or not a.batch_id or not re.fullmatch(r'[A-Za-z0-9_-]+',a.batch_id):raise ValueError('safe sales day and batch id required')
    gate=json.loads(a.gate_json.read_text(encoding='utf-8'));markets=pd.read_csv(a.market_csv,dtype=str).fillna('').to_dict('records');out=directory/f'{a.sales_day}_{a.batch_id}.json'
    hashes={'market_sha256':digest(a.market_csv),'gate_sha256':digest(a.gate_json),'scan_sha256':digest(a.scan_json)}
    if out.exists():
        old=json.loads(out.read_text(encoding='utf-8'))
        if any(old[k]!=v for k,v in hashes.items()):raise ValueError('immutable batch input changed')
        forecast=directory/f'{a.sales_day}_{a.batch_id}_predictions.csv'
        universal_hook('freeze',['--sales-day',a.sales_day,'--batch-id',a.batch_id,'--scan-json',a.scan_json,'--market-csv',a.market_csv,'--gate-json',a.gate_json,'--specialist-predictions',forecast])
        print(json.dumps({'snapshot':str(out),'idempotent':True}));return
    rows=freeze(markets,gate,now,{'mode':'simulation_only','real_money_allowed':False,'effective_from':'2026-10-12T00:00:00+08:00'})
    directory.mkdir(parents=True,exist_ok=True);forecast=directory/f'{a.sales_day}_{a.batch_id}_predictions.csv'
    if not forecast.exists():subprocess.run([sys.executable,str(R/'scripts/predict_independent_goals.py'),'--scan-json',str(a.scan_json),'--output',str(forecast)],cwd=R,check=True,capture_output=True,text=True)
    predictions=pd.read_csv(forecast,dtype=str).fillna('').to_dict('records');now=pd.Timestamp.now(tz='Asia/Shanghai');rows=freeze(markets,gate,now,{'mode':'simulation_only','real_money_allowed':False,'effective_from':'2026-10-12T00:00:00+08:00'})
    selected=[]
    for pred in predictions:
        if pred['status']!='research_only':selected.append(pred);continue
        if not timestamp(gate['freshness']['official_captured_at'])<=timestamp(pred['prediction_at'])<=now:raise ValueError('prediction must follow current official snapshot')
        selected.append(pred)
    result=build_comparison(rows,selected);snapshot={**result,**hashes,'protocol_version':'independent_comparison_v2_direction_only','sales_day':a.sales_day,'batch_id':a.batch_id,'frozen_at':now.isoformat(),'simulation_only':True,'forecast_sha256':digest(forecast),'production_promotion_allowed':False,'comparison_budget_per_arm_play_policy':12.}
    write_new(out,snapshot)
    ucl_hook('freeze',['--sales-day',a.sales_day,'--batch-id',a.batch_id,'--scan-json',a.scan_json,'--market-csv',a.market_csv,'--gate-json',a.gate_json])
    universal_hook('freeze',['--sales-day',a.sales_day,'--batch-id',a.batch_id,'--scan-json',a.scan_json,'--market-csv',a.market_csv,'--gate-json',a.gate_json,'--specialist-predictions',forecast])
    registry=R/'artifacts/data'/f'sporttery_task_registry_{a.sales_day}.json'
    if registry.exists():
        reg=json.loads(registry.read_text(encoding='utf-8-sig'));expected=set(gate['expected_match_numbers'])
        for task in reg['tasks']:
            if set(task.get('match_numbers',[]))==expected:
                task['independent_comparison_artifact']=str(out.relative_to(R))
                task['independent_comparison_status']='frozen' if result['matches'] else 'coverage_skipped'
        registry.write_text(json.dumps(reg,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 独立预测同条件对照','所有金额为理论虚拟预算；单关资格未核验。原正式方案保持原记录，不并入本对照。','市场、独立、50%固定融合使用相同覆盖比赛和赔率；方向观察与估值筛选分开，后者不构成真实正EV声明。',json.dumps(snapshot['allocations'],ensure_ascii=False)]
    for m in result['matches']:lines.append('逐场总进球/净胜球：'+json.dumps(m,ensure_ascii=False))
    lines+=['逐场跨玩法概率与价格比较：'+json.dumps(snapshot.get('cross_play_selection',{}),ensure_ascii=False)]
    lines+=['分账研究卡：'+json.dumps(snapshot.get('research_cards',[]),ensure_ascii=False)]
    for e in result['experiments']:lines.append(json.dumps(e,ensure_ascii=False))
    lines+=['跳过记录：'+json.dumps(result['skips'],ensure_ascii=False)];out.with_suffix('.md').write_text('\n\n'.join(lines),encoding='utf-8');print(json.dumps({'snapshot':str(out),'plans':len(result['experiments']),'covered_matches':len(result['matches'])},ensure_ascii=True))

if __name__=='__main__':main()
