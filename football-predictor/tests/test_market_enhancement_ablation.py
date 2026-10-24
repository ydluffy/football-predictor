import importlib.util
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest
from evaluate.market_enhancement_ablation import class_metrics,aggregate_margin,target_three,build_frame,GROUPS,fit_fold,temperature


def history():
    rows=[]
    for i,day in enumerate(pd.date_range('2020-08-01',periods=20)):
        r={'match_id':str(i),'date':str(day.date()),'season':'2020-21','league':'E0','home_team':'H','away_team':'A','home_goals':i%3,'away_goals':(i+1)%3,'AHh':-.75,'AHCh':-1.}
        for prefix in ('Avg','AvgC'):
            for side,value in zip(('H','D','A'),(2.,3.,4.)):r[prefix+side]=value
        for prefix in ('AvgAH','AvgCAH'):
            r[prefix+'H']=1.9;r[prefix+'A']=1.9
        for prefix in ('Avg','AvgC'):
            r[prefix+'>2.5']=1.8;r[prefix+'<2.5']=2.1
        for book in ('BWC','IWC','PSC','WHC','VCC'):
            for side,v in zip(('H','D','A'),(2.1,3.1,4.1)):r[book+side]=v
        rows.append(r)
    return pd.DataFrame(rows)


def test_rps_penalizes_distant_margin_more_than_adjacent():
    good=np.eye(9)[[4]];near=np.eye(9)[[5]];far=np.eye(9)[[8]]
    assert class_metrics(good,[4],True)[0]['rps']==0
    assert class_metrics(near,[4],True)[0]['rps']<class_metrics(far,[4],True)[0]['rps']


def test_integer_handicap_uses_distribution_not_raw_line_gap():
    p=np.eye(9)[[5]] # home wins exactly one; -1 is handicap draw
    np.testing.assert_allclose(aggregate_margin(p,-1),[[0,1,0]])
    assert target_three(np.array([1]),-1)[0]==1
    assert np.isclose(temperature(np.ones((1,9))/9,.7).sum(),1)


def test_current_score_and_future_season_size_not_model_features():
    f=history();a,audit=build_frame(f);changed=f.copy();changed.loc[19,'home_goals']=9;b,_=build_frame(changed)
    columns=list(GROUPS['plus_team_form'])
    np.testing.assert_allclose(a.loc[a.match_id=='19',columns].to_numpy(float),b.loc[b.match_id=='19',columns].to_numpy(float))
    assert 'season_progress' not in columns and not any('speed' in c for c in columns)
    assert audit['same_cohort_for_all_arms'] is True
    assert np.isclose(a.home_line_strength_delta.iloc[0],.25)


def test_non_quarter_line_is_rejected_not_rounded_into_validity():
    f=history();f.loc[19,'AHCh']=-.3
    a,audit=build_frame(f)
    assert '19' not in set(a.match_id) and audit['quarter_line_rejections']==1


def test_temporal_overlap_rejected_before_fitting():
    f=pd.DataFrame({'date':pd.to_datetime(['2024-01-01'],utc=True)})
    with pytest.raises(AssertionError):fit_fold(f,f,f)


def real_builder():
    folder=Path(__file__).parents[1]/'scripts';sys.path.insert(0,str(folder))
    spec=importlib.util.spec_from_file_location('real_market_builder',folder/'build_real_market_enhancement_dataset.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_missing_prices_and_quarter_totals_keep_missing():
    m=real_builder();assert m.no_vig(['',2,3]) is None
    assert m.no_vig([np.nan,2,3]) is None
    assert m.parse_total('2/2.5')==2.25
    assert np.isnan(m.parse_total('unavailable'))


def test_real_quote_future_stale_and_after_kickoff_blocked():
    m=real_builder();inner='2026-10-19T12:00:00+08:00';kick='2026-10-19T14:00:00+08:00';cutoff='2026-10-19T22:00:00+08:00'
    assert m.verify_capture_window(inner,['2026-10-19T12:01:00+08:00'],kick,cutoff,'2026-10-19T12:02:00+08:00')
    with pytest.raises(ValueError):m.verify_capture_window(inner,['2026-10-19T12:31:00+08:00'],kick,cutoff,'2026-10-19T13:00:00+08:00')
    with pytest.raises(ValueError):m.verify_capture_window(inner,['2026-10-19T14:00:00+08:00'],kick,cutoff,'2026-10-19T15:00:00+08:00')
    with pytest.raises(ValueError):m.verify_capture_window(inner,['2026-10-19T12:01:00+08:00'],kick,cutoff,'2026-10-19T12:00:00+08:00')


def test_different_total_lines_never_average_into_one_price():
    m=real_builder();line,price,n=m.representative_line([(2.25,.8),(2.25,.7),(2.5,.3)],2.5)
    assert line==2.25 and np.isclose(price,.75) and n==2
    assert m.no_vig([]) is None


def test_checkpoint_finalization_mixed_iso_and_real_same_book_speed():
    m=real_builder();f=pd.DataFrame([
        {'match_id':'x','prediction_at':'2026-10-19T10:00:00+00:00','time_delta_minutes':1.,'book_quotes':{'1':[-.5,.5],'2':[-.5,.5]}},
        {'match_id':'x','prediction_at':'2026-10-19T10:30:00.123456+00:00','time_delta_minutes':1.,'book_quotes':{'1':[-.75,.5],'2':[-.75,.5]}}])
    out=m.finalize_snapshot_frame(f)
    assert len(out)==1 and out.iloc[0].observed_common_books==2
    assert np.isclose(out.iloc[0].observed_line_strength_per_hour,.5,rtol=.001)


def test_real_temporal_split_keeps_result_availability_before_next_partition():
    folder=Path(__file__).parents[1]/'scripts';sys.path.insert(0,str(folder))
    from research_real_market_enhancement import temporal_split
    rows=[]
    for day in pd.date_range('2026-09-01',periods=10,tz='UTC'):
        for i in range(30):rows.append({'sales_day':day.date().isoformat(),'at':day+pd.Timedelta(hours=12),'kickoff_at':day+pd.Timedelta(hours=18)})
    f=pd.DataFrame(rows);train,cal,test=temporal_split(f)
    assert (len(train),len(cal),len(test))==(180,60,60)
    assert train.kickoff_at.max()+pd.Timedelta(hours=3)<cal['at'].min()
    f.loc[f.sales_day<'2026-09-07','kickoff_at']=pd.Timestamp('2026-09-08',tz='UTC')
    with pytest.raises(ValueError):temporal_split(f)


def test_real_training_gate_does_not_fit_below_three_hundred(tmp_path,monkeypatch):
    folder=Path(__file__).parents[1]/'scripts';sys.path.insert(0,str(folder))
    import research_real_market_enhancement as runner
    dataset=tmp_path/'data';dataset.mkdir();(dataset/'audit.json').write_text('{}')
    pd.DataFrame({'label_status':['official_completed_unique']*160}).to_csv(dataset/'events.csv',index=False)
    output=tmp_path/'result';monkeypatch.setattr(sys,'argv',['runner','--dataset-directory',str(dataset),'--output-directory',str(output)])
    runner.main();import json
    result=json.loads((output/'summary.json').read_text())
    assert result['status']=='blocked_insufficient_labelled_unique_events' and result['missing_events']==140
    assert not (output/'frozen_development_models.joblib').exists()
