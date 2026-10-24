import numpy as np
from models.independent_goals import score_distribution, aggregate
from strategy.goal_distribution_tracking import forecast_fields,score_goals,NAMES
from strategy.independent_comparison import build_comparison
from test_independent_comparison import inputs

def test_joint_fields_survive_freeze_and_score_without_tickets():
    joint,_=score_distribution(1.7,.8,temperature=1.2)
    fields=forecast_fields(joint)
    assert abs(sum(fields[f'total_probability_{i}'] for i in range(8))-1)<1e-12
    r,p=inputs();p.update(fields)
    _,nine=aggregate(joint)
    p.update({f'margin_probability_{i}':v for i,v in zip(range(-4,5),nine)})
    snap=build_comparison([r],[p]);snap['experiments']=[]
    result={'match_number':'001','home_team':'A','away_team':'B','date':'2026-10-13','status':'已完成','full_time_score':'2:1'}
    review=score_goals(snap['matches'],[result])
    assert set(review['summary'])=={'total_goals','nine_bin_margin'}
    assert all(x['ranked_probability_score']>=0 for x in review['scores'])
    assert review['scores'][0]['target']==3

def test_old_snapshots_missing_totals_never_backfilled_and_void_not_scored():
    r,p=inputs();matches=build_comparison([r],[p])['matches']
    result={'match_number':'001','home_team':'A','away_team':'B','date':'2026-10-13','status':'已完成','full_time_score':'1:0'}
    review=score_goals(matches,[result])
    assert review['pending'][0]['reason']=='not_frozen_in_original_snapshot'
    result['full_time_score']='无效场次'
    assert not score_goals(matches,[result])['scores']

def test_rps_penalizes_distant_error_more():
    r,p=inputs();m=build_comparison([r],[p])['matches'][0]
    result={'match_number':'001','home_team':'A','away_team':'B','date':'2026-10-13','status':'已完成','full_time_score':'1:0'}
    def error(bucket):
        m.update({'margin_probability_'+name:float(i==bucket) for i,name in enumerate(NAMES)})
        return score_goals([m],[result])['scores'][0]['ranked_probability_score']
    assert error(4)<error(0)
