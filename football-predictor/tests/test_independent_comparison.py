import numpy as np
from strategy.independent_comparison import build_comparison

def inputs():
    r={'match_number':'001','home_team':'A','away_team':'B','kickoff_time':'2026-10-13 00:00','home_handicap':'-1'}
    for play in ['spf','rqspf']:
        for key,value in zip(['home','draw','away'],[2,3,4]):r[play+'_odds_'+key]=str(value)
    p={'match_id':'2026-10-12|001','home_team':'A','away_team':'B','kickoff':'2026-10-13T00:00:00+08:00','status':'research_only','model_id':'test','prediction_at':'2026-10-12T21:00:00+08:00','p_home':.6,'p_draw':.2,'p_away':.2}
    for i,x in zip(range(-4,5),[.05,.05,.05,.05,.2,.3,.2,.05,.05]):p['margin_probability_'+str(i)]=x
    return r,p

def test_same_universe_and_budget_no_market_positive_ev():
    r,p=inputs();out=build_comparison([r],[p])
    for arm in ['market','independent','fusion']:
        for play in ['spf','rqspf']:
            group=arm+'_'+play+'_direction'
            assert out['allocations'][group]['invested']==12
            assert sum(e['stake'] for e in out['experiments'] if e['family']==group)==12
    assert not any('estimated_value' in k for k in out['allocations'])
    assert all(e['positive_ev_claim'] is False and e['real_money_allowed'] is False for e in out['experiments'])

def test_identity_and_unknown_model_cannot_enter_control():
    r,p=inputs();p['away_team']='wrong'
    out=build_comparison([r],[p]);assert not out['experiments'] and out['skips']

def test_net_margin_branch_comes_from_model_distribution():
    r,p=inputs();out=build_comparison([r],[p]);e=next(e for e in out['experiments'] if e['family']=='independent_rqspf_direction')
    assert e['legs'][0]['selections'][0]['key']=='away'
    assert np.isclose(e['legs'][0]['selections'][0]['probability'],.4)


def test_coverage_failure_preserves_actual_reason():
    r,p=inputs();p.update(status='blocked',reason='outside_training_leagues')
    out=build_comparison([r],[p])
    assert not out['matches'] and out['skips'][0]['reason']=='outside_training_leagues'


def test_value_research_requires_explicit_opt_in():
    r,p=inputs();out=build_comparison([r],[p],policies=('estimated_value',))
    assert out['allocations']['market_spf_estimated_value']['invested']==0
    assert all(e['positive_ev_claim'] is False for e in out['experiments'])


def test_sbv_alias_matches_existing_model_team_without_fuzzy_guess():
    from data.competition_registry import load_team_alias_registry
    registry=load_team_alias_registry()
    assert registry.resolve('SBV精英')==registry.resolve('Excelsior')=='Excelsior'
    assert registry.resolve('SBV unknown') is None


def test_existing_official_hard_lock_rejects_new_comparison():
    import importlib.util
    import pandas as pd
    import pytest
    from pathlib import Path
    path=Path(__file__).resolve().parents[1]/'scripts/run_october_research.py'
    spec=importlib.util.spec_from_file_location('comparison_gate_test',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    gate={'phase':'READY_FOR_FINAL_ANALYSIS','may_create_plan':True,'failures':[],
          'deadlines':{'decision_start':'2026-10-12T21:00:00+08:00','decision_lock':'2026-10-12T21:45:00+08:00','sales_cutoff':'2026-10-12T22:00:00+08:00'}}
    with pytest.raises(ValueError,match='outside the current decision window'):
        module.freeze([],gate,pd.Timestamp('2026-10-12T21:45:00+08:00'),{'mode':'simulation_only','real_money_allowed':False,'effective_from':'2026-10-12T00:00:00+08:00'})
