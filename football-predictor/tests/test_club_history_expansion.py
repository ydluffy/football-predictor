from copy import deepcopy
import pytest
from data.club_history_expansion import verified_ucl_matches

def match():
    return {'id':1,'season':{'startDate':'2025-09-16'},'utcDate':'2026-05-01T19:00:00Z','status':'FINISHED','score':{'duration':'REGULAR','fullTime':{'home':2,'away':1}},'homeTeam':{'id':1,'name':'A'},'awayTeam':{'id':2,'name':'B'},'stage':'SEMI_FINALS'}

def test_extra_time_not_used_as_90_minute_label():
    m=match();m['score']['duration']='EXTRA_TIME'
    rows,rejected=verified_ucl_matches({'matches':[m]},2025,'2026-10-21T00:00:00Z')
    assert not rows and rejected['not_verified_90_minutes']==1

def test_future_result_is_not_training_history():
    m=match();m['utcDate']='2026-10-22T19:00:00Z'
    rows,rejected=verified_ucl_matches({'matches':[m]},2025,'2026-10-21T00:00:00Z')
    assert not rows and rejected['not_before_cutoff']==1

def test_wrong_requested_season_and_duplicate_rejected():
    with pytest.raises(ValueError,match='season'):verified_ucl_matches({'matches':[match()]},2024,'2026-10-21T00:00:00Z')
    with pytest.raises(ValueError,match='duplicate'):verified_ucl_matches({'matches':[match(),match()]},2025,'2026-10-21T00:00:00Z')

def test_stable_team_identity_and_valid_score():
    rows,rejected=verified_ucl_matches({'matches':[match()]},2025,'2026-10-21T00:00:00Z')
    assert rows[0]['home_id']==1 and rows[0]['home_goals']==2 and not rejected
    m=match();m['score']['fullTime']['away']=-1
    assert verified_ucl_matches({'matches':[m]},2025,'2026-10-21T00:00:00Z')[1]['invalid_score']==1
