import csv
import hashlib
import importlib.util
import json
import sys
import subprocess
from datetime import datetime,timedelta,timezone
from pathlib import Path

import pytest


def setup_case(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('formal_recorder_test',Path(__file__).resolve().parents[1]/'scripts/record_formal_batch.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(module,'ROOT',tmp_path)
    now=datetime.now(timezone(timedelta(hours=8)));day=now.date().isoformat();key='synthetic-batch'
    def write(name,value):
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value),encoding='utf-8');return p
    task={'key':key,'sales_day':day,'purpose':'终版分析','status':'updated','match_numbers':['001','002','003'],'run_at':now.isoformat(),'hard_lock':(now+timedelta(hours=1)).isoformat(),'sales_cutoff':(now+timedelta(hours=2)).isoformat()}
    write('registry.json',{'tasks':[task]})
    write('gate.json',{'phase':'READY_FOR_FINAL_ANALYSIS','may_create_plan':True,'expected_match_numbers':task['match_numbers'],'deadlines':{'decision_lock':task['hard_lock']},'freshness':{'official_captured_at':(now-timedelta(seconds=5)).isoformat()}})
    write('strategy.json',{'ok':True,'input_rows':3,'match_rows':3,'production_plan_rows':2})
    prior=write('prior.json',{'input_rows':3,'match_rows':1})
    write('policy.json',{'scope':'simulation_only','real_money_allowed':False,'effective_from':(now-timedelta(hours=1)).isoformat(),'budget_per_type':100,'max_per_type_per_batch':1,'max_shared_matches':1,'version':'test','quota_scope':'sales_day_and_registered_batch'})
    original=write('artifacts/data/formal_batches/'+day+'_'+hashlib.sha256(key.encode()).hexdigest()[:12]+'.json',{'input_sha256':{'strategy_audit':hashlib.sha256(prior.read_bytes()).hexdigest()},'cards':[{'status':'not_generated','stake':0},{'status':'not_generated','stake':0}]})
    fields=['date','time_window','plan_id','plan_type','selections','stake','estimated_odds','actual_odds','result','payout','net_profit','roi','review_note']
    ledger=tmp_path/'ledger.csv'
    with ledger.open('w',newline='',encoding='utf-8') as f:csv.DictWriter(f,fieldnames=fields).writeheader()
    plans=[{'plan_type':'稳健','selections':'001 A胜 + 002 B胜','is_shadow':False,'total_stake':100,'estimated_odds_min':2},{'plan_type':'价值','selections':'002 B胜 + 003 C胜','is_shadow':False,'total_stake':100,'estimated_odds_min':3}]
    with (tmp_path/'plans.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(plans[0]));writer.writeheader();writer.writerows(plans)
    argv=['recorder','--sales-day',day,'--batch-key',key,'--plans-csv','plans.csv','--strategy-audit','strategy.json','--gate-json','gate.json','--registry','registry.json','--ledger','ledger.csv','--policy','policy.json','--correct-empty-scope','--prior-strategy-audit','prior.json']
    monkeypatch.setattr(sys,'argv',argv)
    return module,original,ledger,write,task


def test_scope_correction_preserves_empty_receipt_and_is_idempotent(tmp_path,monkeypatch):
    module,original,ledger,_,_=setup_case(tmp_path,monkeypatch);before=original.read_bytes()
    module.main();rows=list(csv.DictReader(ledger.open(encoding='utf-8')))
    assert len(rows)==2 and sum(float(r['stake']) for r in rows)==200
    ledger_before=ledger.read_bytes();module.main()
    assert original.read_bytes()==before and ledger.read_bytes()==ledger_before
    correction=next(original.parent.glob('*_scope_correction.json'))
    assert json.loads(correction.read_text())['correction']['reason']=='original_formal_scope_incomplete'


@pytest.mark.parametrize('failure',['nonempty','late','incomplete_current'])
def test_correction_rejects_invalid_cases_without_ledger_write(tmp_path,monkeypatch,failure):
    module,original,ledger,write,task=setup_case(tmp_path,monkeypatch)
    if failure=='nonempty':
        x=json.loads(original.read_text());x['cards'][0]={'status':'recorded','stake':100};original.write_text(json.dumps(x))
    if failure=='late':
        task['hard_lock']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat();write('registry.json',{'tasks':[task]})
    if failure=='incomplete_current':write('strategy.json',{'ok':True,'input_rows':3,'match_rows':2,'production_plan_rows':2})
    before=ledger.read_bytes()
    with pytest.raises(ValueError):module.main()
    assert ledger.read_bytes()==before


def test_strategy_cli_does_not_truncate_batch_to_legacy_three(tmp_path):
    market=[]
    for n in range(1,10):
        market.append(dict(match_number=f'{n:03}',competition='test',kickoff_time='2026-10-18 20:00',home_team=f'H{n}',away_team=f'A{n}',home_handicap=-1,
            spf_odds_home=2.5 if n<7 else 1.2+n/100,spf_odds_draw=4,spf_odds_away=5,rqspf_odds_home=2.5,rqspf_odds_draw=3.2,rqspf_odds_away=2.3))
    source=tmp_path/'markets.csv'
    with source.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(market[0]));writer.writeheader();writer.writerows(market)
    root=Path(__file__).resolve().parents[1]
    args=[sys.executable,'-X','utf8',str(root/'scripts/build_multi_play_betting_strategy.py'),'--market-csv',str(source),'--max-matches','3']
    for flag,name in [('plans-output','plans.csv'),('matches-output','matches.csv'),('report-output','report.md'),('audit-output','audit.json')]:args+=['--'+flag,str(tmp_path/name)]
    result=subprocess.run(args,cwd=root,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    audit=json.loads((tmp_path/'audit.json').read_text(encoding='utf-8'))
    assert audit['match_rows']==audit['input_rows']==9 and audit['production_plan_rows']==2
    plans=list(csv.DictReader((tmp_path/'plans.csv').open(encoding='utf-8-sig')))
    safe=next(p for p in plans if p['plan_type']=='稳健')
    assert '007' in safe['selections'] and '008' in safe['selections']
