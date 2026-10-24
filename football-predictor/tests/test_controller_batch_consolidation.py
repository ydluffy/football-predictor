from datetime import date
from strategy.sporttery_sales_window import group_on_sale_fixtures,build_task_records
from strategy.research_cards import research_cards

def test_overnight_same_window_is_one_eight_match_batch():
    times=['00:30','01:00','02:45','02:45','03:00','03:00','03:15','07:00']
    fixtures=[{'match_number':f'{i+1:03}','home_team':str(i),'away_team':'away','kickoff':f'2026-10-20T{t}:00+08:00','sale_status':'on_sale'} for i,t in enumerate(times)]
    groups=group_on_sale_fixtures(fixtures,sales_day=date(2026,10,19))
    tasks=build_task_records(groups,sales_day=date(2026,10,19))
    assert len(groups)==len(tasks)==1
    assert len(tasks[0]['match_numbers'])==8
    assert tasks[0]['run_at']=='2026-10-19T21:00:00+08:00'

def test_different_daytime_windows_remain_separate():
    fixtures=[{'match_number':str(i),'home_team':'a','away_team':'b','kickoff':f'2026-10-19T{t}:00+08:00','sale_status':'on_sale'} for i,t in enumerate(['15:00','19:00'])]
    assert len(group_on_sale_fixtures(fixtures,sales_day=date(2026,10,19)))==2

def test_named_cards_never_add_exposure_and_missing_is_explicit():
    cards=research_cards({'experiments':[],'allocations':{}})
    assert len(cards)==4
    assert all(c['invested']==0 and c['additional_stake']==0 and c['status']=='empty' for c in cards)
