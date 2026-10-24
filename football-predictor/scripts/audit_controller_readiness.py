"""Read-only controller wiring, queue and coverage audit; never creates bets."""
import argparse,json,sys
from pathlib import Path
from datetime import datetime
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'src'));sys.path.insert(0,str(R/'scripts'))
from strategy.sporttery_sales_window import group_on_sale_fixtures,build_task_records

def audit(day):
    read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
    failures=[];warnings=[]
    registry=read(R/f'artifacts/data/sporttery_task_registry_{day}.json')
    scans=sorted((R/'artifacts/data').glob(f'sporttery_sales_window_scan_{day}_*_confirm.json'))
    if not scans:raise ValueError('today confirmation scan missing')
    scan=read(scans[-1]);active=[t for t in registry['tasks'] if t.get('status') not in {'completed','archived','cancelled','skipped'}]
    actual=[n for t in active for n in t['match_numbers']]
    if len(actual)!=len(set(actual)):failures.append('overlapping_active_batches')
    terminal={n for t in registry['tasks'] if t.get('status') in {'completed','cancelled','skipped'} for n in t.get('match_numbers',[])}
    expected={f['match_number'] for f in scan['fixtures'] if f.get('sale_status')=='on_sale'}-terminal
    if set(actual)!=expected:failures.append('active_queue_differs_from_confirmation_requires_reconciliation')
    windows=[(t['run_at'],t['hard_lock'],t['sales_cutoff']) for t in active]
    if len(windows)!=len(set(windows)):failures.append('same_window_split_into_multiple_budget_batches')
    for t in active:
        if not datetime.fromisoformat(t['run_at'])<datetime.fromisoformat(t['hard_lock'])<datetime.fromisoformat(t['sales_cutoff']):failures.append('invalid_deadline_order')
    configs={}
    for name in ['independent_goals_research','universal_goals_research']:
        cfg=read(R/f'config/{name}.json');artifact=R/cfg['model_artifact']
        configs[name]={'artifact_exists':artifact.exists(),'production_probability_change_allowed':cfg.get('production_probability_change_allowed',False)}
        if not artifact.exists():failures.append(name+'_model_missing')
    uclcfg=R/'config/ucl_domestic_research.json'
    if uclcfg.exists():
        cfg=read(uclcfg);configs['ucl_domestic_research']={'artifact_exists':(R/cfg['model_artifact']).exists(),'prospective_enabled':cfg.get('prospective_enabled',False),'production_probability_change_allowed':cfg.get('production_probability_change_allowed',False),'simulation_budget':cfg.get('simulation_budget')}
        if cfg.get('prospective_enabled') and not (R/cfg['model_artifact']).exists():failures.append('ucl_research_model_missing')
        if cfg.get('production_probability_change_allowed') or cfg.get('simulation_budget')!=0:failures.append('ucl_research_scope_violation')
    required=['scripts/run_independent_comparison.py','scripts/run_universal_comparison.py','scripts/record_formal_batch.py','scripts/next_controller_task.py','scripts/verify_controller_runtime_schedule.py','src/strategy/goal_distribution_tracking.py']
    failures += ['missing:'+p for p in required if not (R/p).exists()]
    state=read(R/'artifacts/data/football_automation_controller_state.json')
    if state.get('pending_reschedule'):failures.append('schedule_update_pending')
    warnings += ['audit_does_not_replace_live_READY_gate','computer_and_application_must_be_online','external_free_provider_quota_or_network_can_degrade','market_enhanced_model_not_promoted']
    return {'ok':not failures,'sales_day':day,'active_batches':len(active),'active_match_count':len(actual),'batches':[{'key':t['key'],'run_at':t['run_at'],'matches':t['match_numbers']} for t in active],'models':configs,'failures':failures,'limitations':warnings,'next_wakeup_at':state.get('next_wakeup_at'),'confirmation_source':str(scans[-1].relative_to(R))}

def main():
    p=argparse.ArgumentParser();p.add_argument('--sales-day',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    result=audit(a.sales_day);out=R/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False));return 0 if result['ok'] else 1
if __name__=='__main__':raise SystemExit(main())
