import copy
import json
from datetime import datetime
from pathlib import Path

import pytest
from strategy.formal_batch import prepare_batch


def inputs():
    policy = json.loads((Path(__file__).resolve().parents[1]/'config/formal_simulation_policy.json').read_text())
    return dict(sales_day='2026-10-18', task=dict(key='batch-a', sales_day='2026-10-18', purpose='终版分析', status='scheduled', match_numbers=['004','005','006'], run_at='2026-10-18T16:45:00+08:00', hard_lock='2026-10-18T18:00:00+08:00', sales_cutoff='2026-10-18T18:15:00+08:00'), gate=dict(phase='READY_FOR_FINAL_ANALYSIS', may_create_plan=True, expected_match_numbers=['004','005','006'], deadlines=dict(decision_lock='2026-10-18T18:00:00+08:00'), freshness=dict(official_captured_at='2026-10-18T16:44:00+08:00')), strategy=dict(ok=True, production_plan_rows=2), plans=[dict(plan_type='稳健',is_shadow=False,selections='004 A胜 + 005 B胜',total_stake=100,estimated_odds_min=2),dict(plan_type='价值',is_shadow=False,selections='005 B胜 + 006 C胜',total_stake=100,estimated_odds_min=3)],existing=[],policy=policy,now=datetime.fromisoformat('2026-10-18T16:45:00+08:00'))


def test_each_batch_has_own_budget_and_immutable_ids():
    a=inputs(); rows, receipt=prepare_batch(**a)
    assert len(rows)==2 and sum(c['stake'] for c in receipt['cards'])==200
    a['existing']=rows
    assert prepare_batch(**a)[0]==[]
    a['task']['key']='batch-b'
    assert len(prepare_batch(**a)[0])==2


def test_missing_value_preserves_empty_card_and_budget():
    a=inputs();a['plans']=a['plans'][:1];a['strategy']['production_plan_rows']=1
    rows,receipt=prepare_batch(**a)
    assert len(rows)==1
    assert receipt['cards'][1]['status']=='not_generated'
    assert receipt['cards'][1]['unused_budget']==100


@pytest.mark.parametrize('failure',['terminal','late','stale','duplicate','outside','overbudget','changed','gate'])
def test_rejects_invalid_freezes(failure):
    a=inputs()
    if failure=='terminal': a['task']['status']='completed'
    if failure=='late': a['now']=datetime.fromisoformat('2026-10-18T18:00:00+08:00')
    if failure=='stale': a['gate']['freshness']['official_captured_at']='2026-10-18T13:26:00+08:00'
    if failure=='duplicate': a['plans'][1]['selections']=a['plans'][0]['selections']
    if failure=='outside': a['plans'][1]['selections']='999 X胜'
    if failure=='overbudget': a['plans'][0]['total_stake']=101
    if failure=='gate': a['gate']['may_create_plan']=False
    if failure=='changed':
        a['existing']=copy.deepcopy(prepare_batch(**a)[0]);a['plans'][0]['estimated_odds_min']=2.1
    with pytest.raises(ValueError): prepare_batch(**a)


def test_shadow_failure_does_not_consume_formal_slot():
    a=inputs();a['plans'].append(dict(is_shadow=True,plan_type='价值',total_stake=1000))
    assert len(prepare_batch(**a)[0])==2
