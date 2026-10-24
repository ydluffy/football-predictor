import numpy as np
import pandas as pd
import pytest
from models.universal_goals import chronological_features, validate_history, FormHistory, restore_history


def history():
    return pd.DataFrame([dict(league='A',date=str(d.date()),home_team='H',away_team='V',home_goals=1,away_goals=0)
                         for d in pd.date_range('2024-01-01',periods=12)])


def test_future_scores_cannot_change_earlier_features():
    f=history(); rows,x,_,_=chronological_features(f)
    changed=f.copy(); changed.loc[11,'home_goals']=9
    rows2,x2,_,_=chronological_features(changed)
    np.testing.assert_allclose(x,x2)
    assert rows.date.max()==rows2.date.max()


def test_same_day_scores_not_used_and_odds_ignored():
    f=history(); extra=f.iloc[[-1]].copy(); extra.home_team='V';extra.away_team='H'
    a=pd.concat([f,extra],ignore_index=True); a['odds_home']=1.01
    _,x,_,_=chronological_features(a)
    a.loc[len(a)-1,'home_goals']=8; a.odds_home=900
    _,y,_,_=chronological_features(a)
    np.testing.assert_allclose(x,y)


def test_unknown_stale_and_cross_league_are_blocked():
    _,_,s,_=chronological_features(history())
    assert s.features('A','unknown','V',pd.Timestamp('2024-01-13',tz='UTC'))[1]=='insufficient_team_history'
    assert s.features('B','H','V',pd.Timestamp('2024-01-13',tz='UTC'))[1]=='insufficient_team_history'
    assert s.features('A','H','V',pd.Timestamp('2025-01-13',tz='UTC'))[1]=='stale_team_history'


def test_bad_scores_and_duplicate_sources_rejected():
    f=history()
    with pytest.raises(ValueError):validate_history(pd.concat([f,f.iloc[[0]]]))
    f.loc[0,'home_goals']=-1
    with pytest.raises(ValueError):validate_history(f)


def test_mixed_iso_dates_supported_without_day_month_guessing():
    f=history();f.loc[0,'date']='2024-01-01 00:00:00';f.loc[1,'date']='2024-01-02T01:00:00+00:00'
    assert len(validate_history(f))==12


def test_serialized_form_restores_exact_features():
    _,_,s,_=chronological_features(history())
    a={'alpha':s.alpha,'prior':s.prior,'leagues':dict(s.leagues),'teams':[{'league':k[0],'team':k[1],**{c:(v.isoformat() if c=='last' else v) for c,v in st.items()}} for k,st in s.teams.items()]}
    restored=restore_history(a);day=pd.Timestamp('2024-01-13',tz='UTC')
    np.testing.assert_allclose(s.features('A','H','V',day)[0],restored.features('A','H','V',day)[0])
