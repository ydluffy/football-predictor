import json
import numpy as np
import pandas as pd
import pytest
from models.ucl_domestic import ClubState,chronological_examples
from strategy.ucl_domestic_research import identity_index,resolve_team,predictions,publish_refresh_pointer
from data.competition_registry import TeamAliasRegistry
from strategy.universal_comparison import score_snapshot
from models.independent_goals import score_distribution,aggregate
from strategy.goal_distribution_tracking import forecast_fields,NAMES

def history():
 rows=[]
 for i in range(10):
  rows.append(dict(source_match_id=i,date=f'2025-01-{i+1:02d}T12:00:00+00:00',home_id=1,away_id=2,home_team='A',away_team='B',home_goals=1,away_goals=0,competition='PL',season=2024,stage='REGULAR_SEASON'))
 rows.append(dict(source_match_id=100,date='2025-01-11T20:00:00+00:00',home_id=1,away_id=2,home_team='A',away_team='B',home_goals=3,away_goals=0,competition='CL',season=2024,stage='LEAGUE_STAGE'))
 return pd.DataFrame(rows)

def test_future_result_does_not_change_features():
 f=history();_,x,_,_=chronological_examples(f);f.loc[len(f)-1,'home_goals']=20;_,y,_,_=chronological_examples(f);np.testing.assert_allclose(x,y)

def test_same_day_domestic_result_is_excluded():
 f=history();extra=f.iloc[0].copy();extra.source_match_id=101;extra.date='2025-01-11T10:00:00+00:00';f=pd.concat([f,extra.to_frame().T],ignore_index=True);_,x,_,_=chronological_examples(f);f.loc[len(f)-1,'home_goals']=20;_,y,_,_=chronological_examples(f);np.testing.assert_allclose(x,y)

def test_duplicate_id_rejected():
 f=history();f.loc[1,'source_match_id']=0
 with pytest.raises(ValueError):chronological_examples(f)

def test_stale_domestic_history_rejected():
 _,_,state,_=chronological_examples(history());assert state.features('1','2',pd.Timestamp('2026-01-01',tz='UTC'))[1]=='stale_domestic_history'

def test_restore_preserves_features():
 _,_,state,_=chronological_examples(history());x,_=state.features('1','2',pd.Timestamp('2025-01-12',tz='UTC'));y,_=ClubState.restore(state.as_dict()).features('1','2',pd.Timestamp('2025-01-12',tz='UTC'));np.testing.assert_allclose(x,y)

def test_ambiguous_alias_is_not_resolved():
 registry=TeamAliasRegistry([]);index=identity_index({'1':{'names':['United FC']},'2':{'names':['United FC']}},registry);assert resolve_team('United FC',index,registry) is None

def test_provider_kickoff_mismatch_blocks_even_known_teams():
 _,_,state,_=chronological_examples(history());artifact={'trained_through':'2025-01-11T20:00:00+00:00','state':state.as_dict(),'teams':{'1':{'names':['Alpha FC']},'2':{'names':['Beta FC']}},'model_id':'test'};scan={'fixtures':[{'match_id':'2025-01-12|001','match_number':'001','home_team':'Alpha FC','away_team':'Beta FC','kickoff':'2025-01-12T20:00:00+00:00','competition_id':'UEFA_CHAMPIONS_LEAGUE','sale_status':'on_sale'}]};provider={'matches':[{'homeTeam':{'id':1},'awayTeam':{'id':2},'utcDate':'2025-01-12T21:00:00+00:00','status':'TIMED'}]};rows,skips=predictions(scan,artifact,provider,pd.Timestamp('2025-01-12T12:00:00Z'));assert not rows and skips[0]['reason']=='provider_fixture_or_kickoff_mismatch'

def test_zero_budget_scoring_uses_frozen_probability():
 joint,_=score_distribution(1.5,1.);p3,p9=aggregate(joint);m={'match_number':'001','home_team':'H','away_team':'A','kickoff_time':'2025-01-12T12:00:00Z','handicap_model_id':'test','comparison_probabilities':{'spf':{'independent':p3.tolist()}},**{'margin_probability_'+k:float(v) for k,v in zip(NAMES,p9)},**forecast_fields(joint)};r={'match_number':'001','home_team':'H','away_team':'A','date':'2025-01-12','status':'已完成','full_time_score':'2:0'};review=score_snapshot({'matches':[m],'experiments':[],'protocol_version':'ucl_domestic_probability_only_v1','cohort':'test'},[r]);assert review['settled']==[] and review['unique_matches_scored']==1 and review['goal_distribution_review']['summary']['total_goals']['n']==1

def test_refresh_pointer_ignores_failed_provider_archive(tmp_path):
 cfg=tmp_path/'ucl_domestic_research.json';cfg.write_text(json.dumps({'provider_captured_at':'2026-10-21T06:54:52.677184+00:00','reviewed_aliases':{'里尔':'521'}},ensure_ascii=False),encoding='utf-8')
 failed={'sources':{'CL_2026':{'status':'failed','reason':'network_error'}}}
 assert publish_refresh_pointer(cfg,failed,'2026-10-24T00:00:00+00:00')=={'updated':False,'reason':'provider_archive_not_refreshed'}
 assert json.loads(cfg.read_text(encoding='utf-8'))['provider_captured_at']=='2026-10-21T06:54:52.677184+00:00'

def test_refresh_pointer_advances_only_after_real_refresh(tmp_path):
 cfg=tmp_path/'ucl_domestic_research.json';cfg.write_text(json.dumps({'provider_captured_at':'2026-10-21T06:54:52.677184+00:00','max_provider_age_hours':24,'reviewed_aliases':{'里尔':'521'}},ensure_ascii=False),encoding='utf-8')
 refreshed={'sources':{'CL_2026':{'status':'refreshed','rows':148}}}
 assert publish_refresh_pointer(cfg,refreshed,'2026-10-24T00:00:00+00:00')=={'updated':True,'provider_captured_at':'2026-10-24T00:00:00+00:00'}
 saved=json.loads(cfg.read_text(encoding='utf-8'))
 assert saved['provider_captured_at']=='2026-10-24T00:00:00+00:00' and saved['max_provider_age_hours']==24 and saved['reviewed_aliases']=={'里尔':'521'}
