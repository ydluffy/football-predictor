from strategy.cross_play_selection import select_cross_play

def match(n):
    m={'match_number':n,'home_team':'a','away_team':'b','kickoff_time':'2026-10-20T01:00:00+08:00','home_handicap':'-1','handicap_model_id':'test','comparison_probabilities':{}}
    for play,model,odds in [('spf',[.75,.15,.1],[1.4,5,8]),('rqspf',[.35,.4,.25],[2.2,3.8,2.6])]:
        inv=[1/o for o in odds];market=[v/sum(inv) for v in inv]
        m['comparison_probabilities'][play]={'independent':model,'market':market,'fusion':[(x+y)/2 for x,y in zip(model,market)]}
        for k,v in zip(['home','draw','away'],odds):m[f'{play}_odds_{k}']=v
    return m

def test_high_win_probability_does_not_force_handicap_win():
    result=select_cross_play([match('001')]);row=result['observations'][0]
    assert row['highest_probability']['play']=='spf'
    assert row['selected']['play']=='rqspf' and row['selected']['key']=='draw'
    assert result['allocation']['invested']==6
    assert result['allocation']['unused']==6

def test_distinct_match_two_leg_and_budget_not_double_counted():
    result=select_cross_play([match('001'),match('002'),match('003')])
    assert len(result['experiments'])==3
    assert sum(e['stake'] for e in result['experiments'])==12
    double=result['experiments'][-1]
    assert len({l['match_number'] for l in double['legs']})==2
    assert double['joint_probability_status']=='not_estimated_correlation_unknown'

def test_no_edge_empty_not_forced():
    m=match('001')
    for arms in m['comparison_probabilities'].values():
        arms['independent']=arms['market'];arms['fusion']=arms['market']
    result=select_cross_play([m]);assert not result['experiments']
    assert result['allocation']['unused']==12

def test_handicap_single_and_double_use_frozen_odds_on_settlement():
    from strategy.october_research import settle
    result=select_cross_play([match('001'),match('002')])
    results=[{'match_number':n,'home_team':'a','away_team':'b','date':'2026-10-20','status':'已完成','full_time_score':'2:1'} for n in ['001','002']]
    review=settle({'protocol_version':'cross_play_stress_v1','matches':[],'experiments':result['experiments']},results)
    assert not review['pending']
    group=review['by_family']['cross_play_stress_v1']
    assert group['stake']==12
    assert abs(group['payout']-(6*3.8+6*3.8*3.8))<.011
