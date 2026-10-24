"""READY-gated immutable universal fallback research and official scoring."""
import argparse,json,sys,re,subprocess
from pathlib import Path
import pandas as pd
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from run_october_research import freeze,digest,write_new
from strategy.october_research import timestamp
from strategy.universal_comparison import fallback_comparison,score_snapshot


def recover_report(out,snapshot):
    report=out.with_suffix('.md')
    if report.exists() or snapshot.get('protocol_version')!='universal_fallback_v1':return
    lines=['# 通用后备前瞻模拟对照','仅包含专用模型未覆盖且通用模型可覆盖的比赛；不混入原专用模型评分。independent组在本账内指通用后备，fusion为通用与市场固定50%融合。',f"批次：{snapshot['batch_id']}；冻结：{snapshot['frozen_at']}；每组每玩法12元理论预算，单关资格未核验，不能单独触发投注。"]
    for m in snapshot['matches']:
        lines.append(f"{m['match_number']} {m['home_team']} vs {m['away_team']}：通用胜/平/负 {m['p_home']:.2%}/{m['p_draw']:.2%}/{m['p_away']:.2%}；九档净胜球 {json.dumps({k:v for k,v in m.items() if k.startswith('margin_probability_')},ensure_ascii=False)}")
    lines+=['总进球与净胜球冻结：'+json.dumps([{k:v for k,v in m.items() if k.startswith(('total_probability_','margin_probability_')) or k in {'match_number','expected_total_goals','expected_goal_margin'}} for m in snapshot['matches']],ensure_ascii=False)]
    lines+=['逐场跨玩法概率与价格比较：'+json.dumps(snapshot.get('cross_play_selection',{}),ensure_ascii=False)]
    lines+=['分账研究卡：'+json.dumps(snapshot.get('research_cards',[]),ensure_ascii=False)]
    lines+=['各组投入及未用预算：'+json.dumps(snapshot['allocations'],ensure_ascii=False),'逐场方案：'+json.dumps(snapshot['experiments'],ensure_ascii=False),'跳过：'+json.dumps(snapshot['skips'],ensure_ascii=False)]
    with report.open('x',encoding='utf-8') as stream:stream.write('\n\n'.join(lines))


def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['freeze','settle','settle-pending']);p.add_argument('--sales-day');p.add_argument('--batch-id');p.add_argument('--scan-json',type=Path);p.add_argument('--market-csv',type=Path);p.add_argument('--gate-json',type=Path);p.add_argument('--specialist-predictions',type=Path);p.add_argument('--snapshot',type=Path);p.add_argument('--results-csv',type=Path);a=p.parse_args()
    directory=R/'artifacts/data/universal_comparison';now=pd.Timestamp.now(tz='Asia/Shanghai')
    if a.stage in {'settle','settle-pending'}:
        if not a.results_csv:p.error('official results CSV required')
        if a.stage=='settle' and not a.snapshot:p.error('frozen snapshot required')
        targets=[a.snapshot] if a.stage=='settle' else [q for q in directory.glob('*.json') if re.fullmatch(r'\d{4}-\d{2}-\d{2}_.+',q.stem) and not q.stem.endswith('_predictions')]
        results=pd.read_csv(a.results_csv,dtype=str).fillna('').to_dict('records');outputs=[]
        for target in targets:
            snapshot=json.loads(target.read_text(encoding='utf-8'))
            if snapshot.get('protocol_version')!='universal_fallback_v1':continue
            if timestamp(snapshot['sales_day']).date()>=now.date():continue
            review=score_snapshot(snapshot,results);engine=digest(R/'src/strategy/universal_comparison.py')+digest(R/'src/strategy/october_research.py')+digest(R/'src/strategy/goal_distribution_tracking.py')
            import hashlib
            engine=hashlib.sha256(engine.encode()).hexdigest()
            out=directory/'reviews'/f'{target.stem}_{digest(a.results_csv)[:16]}_{engine[:8]}.json'
            review.update(reviewed_at=now.isoformat(),snapshot_sha256=digest(target),results_sha256=digest(a.results_csv),settlement_engine_sha256=engine)
            if not out.exists():write_new(out,review)
            report=out.with_suffix('.md')
            if not report.exists():
                lines=['# 通用后备研究复盘','概率误差与理论收益分开；不同组与原专用模型不可直接合并比较。',f"独立比赛数：{review['unique_matches_scored']}；待定：{len(review['probability_pending'])}；无效场次不评分。",json.dumps(review['goal_distribution_review'],ensure_ascii=False),json.dumps(review['probability_summary'],ensure_ascii=False),json.dumps(review['by_family'],ensure_ascii=False)]
                with report.open('x',encoding='utf-8') as stream:stream.write('\n\n'.join(lines))
            outputs.append({'review':str(out),'probability_pending':len(review['probability_pending'])})
        print(json.dumps({'reviews':outputs}));return
    if not a.sales_day or not a.batch_id or not re.fullmatch(r'[A-Za-z0-9_-]+',a.batch_id):p.error('safe sales day and batch ID required')
    if not all((a.scan_json,a.market_csv,a.gate_json,a.specialist_predictions)):p.error('scan, market, READY gate and specialist predictions required')
    cfg=json.loads((R/'config/universal_goals_research.json').read_text(encoding='utf-8'))
    modelpath=R/cfg['model_artifact'];out=directory/f'{a.sales_day}_{a.batch_id}.json'
    hashes={k:digest(v) for k,v in {'scan_sha256':a.scan_json,'market_sha256':a.market_csv,'gate_sha256':a.gate_json,'specialist_predictions_sha256':a.specialist_predictions}.items()}
    if out.exists():
        old=json.loads(out.read_text(encoding='utf-8'))
        if any(old[k]!=v for k,v in hashes.items()):raise ValueError('immutable universal batch inputs changed')
        recover_report(out,old)
        print(json.dumps({'snapshot':str(out),'idempotent':True}));return
    if not cfg.get('prospective_shadow_enabled'):raise ValueError('universal prospective shadow not enabled')
    hashes['model_sha256']=digest(modelpath)
    gate=json.loads(a.gate_json.read_text(encoding='utf-8'));markets=pd.read_csv(a.market_csv,dtype=str).fillna('').to_dict('records')
    protocol={'mode':'simulation_only','real_money_allowed':False,'effective_from':cfg['prospective_effective_from']}
    rows=freeze(markets,gate,now,protocol)
    scan=json.loads(a.scan_json.read_text(encoding='utf-8-sig'))
    if not all(str(f['match_id']).startswith(a.sales_day+'|') for f in scan['fixtures']):raise ValueError('scan sales day mismatch')
    primary_audit=json.loads(a.specialist_predictions.with_suffix('.json').read_text(encoding='utf-8'))
    if primary_audit['scan_sha256']!=hashes['scan_sha256']:raise ValueError('specialist forecast belongs to another scan')
    specialist=pd.read_csv(a.specialist_predictions,dtype=str).fillna('').to_dict('records')
    directory.mkdir(parents=True,exist_ok=True);forecast=directory/f'{a.sales_day}_{a.batch_id}_predictions.json'
    if not forecast.exists():subprocess.run([sys.executable,str(R/'scripts/predict_universal_goals.py'),'--scan-json',str(a.scan_json),'--output',str(forecast)],cwd=R,check=True,capture_output=True,text=True)
    data=json.loads(forecast.read_text(encoding='utf-8'))
    if data['scan_sha256']!=hashes['scan_sha256'] or data['model_sha256']!=hashes['model_sha256']:raise ValueError('forecast input provenance mismatch')
    now=pd.Timestamp.now(tz='Asia/Shanghai');rows=freeze(markets,gate,now,protocol)
    captured=timestamp(gate['freshness']['official_captured_at'])
    if not captured<=timestamp(data['created_at'])<=now:raise ValueError('forecast time outside current official snapshot')
    result=fallback_comparison(rows,data['rows'],specialist)
    snapshot={**result,**hashes,'forecast_sha256':digest(forecast),'sales_day':a.sales_day,'batch_id':a.batch_id,'frozen_at':now.isoformat(),'protocol_version':'universal_fallback_v1','simulation_only':True,'production_promotion_allowed':False,'comparison_budget_per_arm_play_policy':12.}
    write_new(out,snapshot)
    write_new(out.with_suffix('.receipt.json'),{'snapshot':str(out),'status':'frozen' if result['matches'] else 'coverage_skipped','covered_matches':len(result['matches']),'original_ledgers_written':False})
    recover_report(out,snapshot)
    registry=R/f'artifacts/data/sporttery_task_registry_{a.sales_day}.json'
    if registry.exists():
        reg=json.loads(registry.read_text(encoding='utf-8-sig'));expected=set(gate['expected_match_numbers'])
        for task in reg['tasks']:
            if set(task.get('match_numbers',[]))==expected:
                task['universal_comparison_artifact']=str(out.relative_to(R))
                task['universal_comparison_status']='frozen' if result['matches'] else 'coverage_skipped'
        registry.write_text(json.dumps(reg,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'snapshot':str(out),'covered_matches':len(result['matches'])}))


if __name__=='__main__':main()
