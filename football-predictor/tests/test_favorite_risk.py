import numpy as np
import pytest
from evaluate.favorite_risk import classify,risk_probabilities,favorite_side,no_vig

def test_loss_draw_and_win_not_cover_are_separate():
    assert classify(0,1,0,-1)['category']=='favorite_loss'
    assert classify(1,1,0,-1)['category']=='favorite_draw'
    assert classify(2,1,0,-1)['category']=='win_not_full_cover'
    assert classify(3,1,0,-1)['category']=='full_cover'

def test_quarter_half_win_not_misreported_full_cover_and_away_orientation():
    assert classify(1,0,0,-.75)['category']=='win_not_full_cover'
    assert classify(2,0,0,-1.25)['category']=='full_cover'
    assert classify(0,1,2,1)['category']=='win_not_full_cover'

def test_unsupported_tail_and_unknown_line():
    assert not classify(5,0,0,-4)['nine_bin_cover_supported']
    assert classify(2,0,0,float('nan'))['category']=='win_handicap_unknown'
    with pytest.raises(ValueError):risk_probabilities(np.ones(9)/9,0,4)

def test_probabilities_partition_and_favorite_defined_before_outcome():
    p=np.array([.05,.05,.05,.05,.2,.3,.2,.05,.05])
    assert np.allclose(risk_probabilities(p,0,1),[.2,.2,.3,.3])
    assert favorite_side(no_vig([1.4,4,8]))==0
    assert favorite_side(no_vig([2.5,3,2.5])) is None
