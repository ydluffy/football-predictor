import copy
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest
from strategy.universal_comparison import fallback_comparison,score_snapshot


def inputs():
    r={'match_number':'001','home_team':'A','away_team':'B','kickoff_time':'2026-10-20T01:00:00+08:00','home_handicap':'-1'}
    for play in ('spf','rqspf'):
        for key,v in zip(('home','draw','away'),(2.,3.,4.)):r[play+'_odds_'+key]=str(v)
    p={'match_id':'2026-10-19|001','home_team':'A','away_team':'B','kickoff':r['kickoff_time'],'prediction_at':'2026-10-19T21:00:00+08:00','model_id':'universal','status':'research_preview','p_home':.6,'p_draw':.2,'p_away':.2}
    for i,v in zip(range(-4,5),(.05,.05,.05,.05,.2,.3,.2,.05,.05)):p['margin_probability_'+str(i)]=v
    s={**p,'status':'blocked','reason':'outside_training_leagues'}
    return r,p,s


def test_only_specialist_skips_enter_separate_cohort():
    r,p,s=inputs();out=fallback_comparison([r],[p],[s])
    assert len(out['matches'])==1 and out['cohort'].endswith('fallback_only')
    assert all(v['invested']==12 for k,v in out['allocations'].items() if k!='cross_play_stress_v1')
    assert 0<=out['allocations']['cross_play_stress_v1']['invested']<=12
    s['status']='research_only'
    no=fallback_comparison([r],[p],[s]);assert not no['matches']
    assert no['skips'][0]['reason']=='specialist_already_covers'


def test_missing_primary_and_identity_cannot_turn_into_fallback():
    r,p,s=inputs()
    assert not fallback_comparison([r],[p],[])['matches']
    p['away_team']='wrong'
    assert not fallback_comparison([r],[p],[s])['matches']
    p['away_team']='B';s['reason']='after_kickoff'
    assert not fallback_comparison([r],[p],[s])['matches']


def test_probability_and_paper_returns_separate_void_and_pending():
    r,p,s=inputs();snap=fallback_comparison([r],[p],[s])
    result={'match_number':'001','home_team':'A','away_team':'B','date':'2026-10-20','status':'已完成','full_time_score':'2:0'}
    scored=score_snapshot(snap,[result]);assert len(scored['probability_scores'])==7
    assert any(x['play']=='nine_bin_margin' and x['target']==6 for x in scored['probability_scores'])
    assert scored['unique_matches_scored']==1
    assert 0<=scored['probability_summary']['nine_bin_margin|universal']['ranked_probability_score']<=1
    assert not scored['probability_pending']
    pending=score_snapshot(snap,[]);assert len(pending['probability_pending'])==1
    assert not pending['probability_scores']
    void=score_snapshot(snap,[{**result,'full_time_score':'无效场次'}])
    assert void['void_excluded_from_probability']==['001'] and not void['probability_scores']
    assert all(e['net']==0 for e in void['settled'])
    ambiguous=score_snapshot(snap,[result,result]);assert ambiguous['probability_pending']


def load_runner():
    path=Path(__file__).resolve().parents[1]/'scripts'
    sys.path.insert(0,str(path))
    spec=importlib.util.spec_from_file_location('universal_runner_test',path/'run_universal_comparison.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_real_ready_gate_rejects_hard_lock_and_wrong_scope():
    runner=load_runner();r,_,_=inputs();r['updated_at']='2026-10-19T21:00:00+08:00'
    gate={'phase':'READY_FOR_FINAL_ANALYSIS','may_create_plan':True,'failures':[],'expected_match_numbers':['001'],'as_of':'2026-10-19T21:01:00+08:00','freshness':{'official_captured_at':r['updated_at']},'deadlines':{'decision_start':'2026-10-19T21:00:00+08:00','decision_lock':'2026-10-19T21:45:00+08:00','sales_cutoff':'2026-10-19T22:00:00+08:00'}}
    cfg={'mode':'simulation_only','real_money_allowed':False,'effective_from':'2026-10-19T12:00:00+08:00'}
    assert len(runner.freeze([r],gate,pd.Timestamp('2026-10-19T21:01:00+08:00'),cfg))==1
    with pytest.raises(ValueError,match='outside'):runner.freeze([r],gate,pd.Timestamp('2026-10-19T21:45:00+08:00'),cfg)
    gate['expected_match_numbers']=['002']
    with pytest.raises(ValueError,match='expected batch'):runner.freeze([r],gate,pd.Timestamp('2026-10-19T21:01:00+08:00'),cfg)


def test_cli_existing_snapshot_replay_does_not_touch_forecasts(tmp_path,monkeypatch):
    runner=load_runner();runner.R=tmp_path
    config=tmp_path/'config';config.mkdir();(config/'universal_goals_research.json').write_text(json.dumps({'model_artifact':'absent-model.json','prospective_shadow_enabled':False}))
    paths=[]
    for name in ('scan','market','gate','primary'):
        p=tmp_path/(name+'.json');p.write_text(name);paths.append(p)
    from run_october_research import digest
    hashes={k:digest(v) for k,v in zip(('scan_sha256','market_sha256','gate_sha256','specialist_predictions_sha256'),paths)}
    directory=tmp_path/'artifacts/data/universal_comparison';directory.mkdir(parents=True)
    target=directory/'2026-10-19_test.json';target.write_text(json.dumps(hashes));original=target.read_bytes()
    args=['runner','freeze','--sales-day','2026-10-19','--batch-id','test','--scan-json',str(paths[0]),'--market-csv',str(paths[1]),'--gate-json',str(paths[2]),'--specialist-predictions',str(paths[3])]
    monkeypatch.setattr(sys,'argv',args);runner.main();assert target.read_bytes()==original
    paths[0].write_text('changed')
    with pytest.raises(ValueError,match='immutable'):runner.main()


def test_actual_freeze_workflow_provenance_and_replay(tmp_path,monkeypatch):
    runner=load_runner();runner.R=tmp_path
    now=pd.Timestamp.now(tz='Asia/Shanghai');day=now.date().isoformat();kickoff=(now.normalize()+pd.Timedelta(days=1,hours=1)).isoformat()
    r,p,s=inputs();r['kickoff_time']=kickoff;p.update(match_id=day+'|001',kickoff=kickoff,prediction_at=now.isoformat());s.update(match_id=day+'|001',kickoff=kickoff,prediction_at=now.isoformat())
    captured=(now-pd.Timedelta(minutes=1)).isoformat();r['updated_at']=captured
    gate={'phase':'READY_FOR_FINAL_ANALYSIS','may_create_plan':True,'failures':[],'expected_match_numbers':['001'],'as_of':now.isoformat(),'freshness':{'official_captured_at':captured},'deadlines':{'decision_start':(now-pd.Timedelta(minutes=2)).isoformat(),'decision_lock':(now+pd.Timedelta(minutes=10)).isoformat(),'sales_cutoff':(now+pd.Timedelta(minutes=20)).isoformat()}}
    config=tmp_path/'config';config.mkdir();(config/'universal_goals_research.json').write_text(json.dumps({'model_artifact':'model.json','prospective_shadow_enabled':True,'prospective_effective_from':(now-pd.Timedelta(minutes=3)).isoformat()}))
    model=tmp_path/'model.json';model.write_text('{}')
    scan=tmp_path/'scan.json';scan.write_text(json.dumps({'fixtures':[p]}));market=tmp_path/'market.csv';pd.DataFrame([r]).to_csv(market,index=False)
    gp=tmp_path/'gate.json';gp.write_text(json.dumps(gate));primary=tmp_path/'primary.csv';pd.DataFrame([s]).to_csv(primary,index=False)
    from run_october_research import digest
    primary.with_suffix('.json').write_text(json.dumps({'scan_sha256':digest(scan)}))
    def fake_run(command,**kwargs):
        path=Path(command[command.index('--output')+1]);data={'created_at':pd.Timestamp.now(tz='UTC').isoformat(),'model_sha256':digest(model),'scan_sha256':digest(scan),'rows':[p]};path.write_text(json.dumps(data))
    monkeypatch.setattr(runner.subprocess,'run',fake_run)
    args=['runner','freeze','--sales-day',day,'--batch-id','integration','--scan-json',str(scan),'--market-csv',str(market),'--gate-json',str(gp),'--specialist-predictions',str(primary)]
    monkeypatch.setattr(sys,'argv',args);runner.main()
    output=tmp_path/f'artifacts/data/universal_comparison/{day}_integration.json'
    original=output.read_bytes();snapshot=json.loads(original)
    assert len(snapshot['matches'])==1 and snapshot['production_promotion_allowed'] is False
    assert snapshot['forecast_sha256']
    runner.main();assert output.read_bytes()==original
    output.with_suffix('.md').unlink()
    runner.main();assert output.read_bytes()==original and output.with_suffix('.md').exists()


def test_research_failure_is_audited_without_blocking_primary(tmp_path,monkeypatch):
    import universal_controller_hook as hook
    from types import SimpleNamespace
    monkeypatch.setattr(hook,'R',tmp_path);(tmp_path/'config').mkdir()
    (tmp_path/'config/universal_goals_research.json').write_text(json.dumps({'prospective_shadow_enabled':True}))
    monkeypatch.setattr(hook.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(returncode=3,stdout='',stderr='test provider failure'))
    hook.run_hook('freeze',['--batch-id','test'])
    audit=json.loads(next((tmp_path/'artifacts/data/universal_comparison/audits').glob('*.json')).read_text())
    assert audit['status']=='failed' and audit['production_blocked'] is False
