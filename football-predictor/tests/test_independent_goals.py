import numpy as np
import pandas as pd
from models.independent_goals import IndependentGoals,score_distribution,aggregate,handicap_probability

def sample():
    return pd.DataFrame({'date':pd.date_range('2020-01-01',periods=12),'home_team':['A','B']*6,'away_team':['B','A']*6,'home_goals':[3,1]*6,'away_goals':[0,2]*6})

def test_odds_columns_cannot_change_training():
    f=sample();a=IndependentGoals.fit(f)
    f['odds_home']=np.arange(len(f))+1;f['odds_away']=999
    b=IndependentGoals.fit(f)
    np.testing.assert_allclose(a.coefficients,b.coefficients)

def test_probabilities_and_integer_handicap_mapping():
    p,tail=score_distribution(1.7,1.1,temperature=1.2);three,nine=aggregate(p)
    assert tail<1e-10
    assert np.isclose(three.sum(),1) and np.isclose(nine.sum(),1)
    np.testing.assert_allclose(three,[nine[5:].sum(),nine[4],nine[:4].sum()])
    rq=handicap_probability(nine,-1)
    np.testing.assert_allclose(rq,[nine[6:].sum(),nine[5],nine[:5].sum()])
    one=np.zeros(9);one[6]=1
    np.testing.assert_allclose(handicap_probability(one,-2),[0,1,0])

def test_unknown_team_uses_finite_shrunk_prior():
    m=IndependentGoals.fit(sample());r=m.rates('new_home','new_away')
    assert np.isfinite(r).all() and (r>0).all()
    p,_=score_distribution(*r);assert np.isclose(p.sum(),1)
