from __future__ import annotations

from datetime import datetime, timedelta, timezone

from data.nowscore_market import align_cp_to_scan, asian_line, parse_cp_page, parse_odds_page, to_outer_rows


CP = '''<div>2026年09月20日 星期日</div><table>
<tr matchid="88" gamename="英超"><td>010</td><td>英超</td><td title="开赛时间：2026-09-20 21:00">21:00</td>
<td><a id="HomeTeam_1">利兹联</a></td><td>0-0</td><td><a id="GuestTeam_1">水晶宫</a></td><td></td><td></td>
<td><a href="//live.nowscore.com/odds/match/3003894.htm">亚</a></td></tr>
<tr matchid="99" gamename="英超"><td>010</td><td>英超</td><td title="开赛时间：2026-09-21 21:00">21:00</td>
<td><a id="HomeTeam_2">其他队</a></td><td>0-0</td><td><a id="GuestTeam_2">水晶宫</a></td><td></td><td></td>
<td><a href="//live.nowscore.com/odds/match/3003999.htm">亚</a></td></tr></table>'''

MULTI_DAY_CP = '''<div>2026年09月23日 星期三</div><table>
<tr matchid="77" gamename="美职业"><td>003</td><td>美职业</td><td title="开赛时间：2026-09-23 09:30">09:30</td>
<td><a id="HomeTeam_0">西雅图</a></td><td>-</td><td><a id="GuestTeam_0">盐湖城</a></td><td></td><td></td>
<td><a href="//live.nowscore.com/odds/match/3003777.htm">亚</a></td></tr></table>
<div>2026年09月24日 星期四</div><table>
<tr matchid="88" gamename="国际友谊"><td>003</td><td>国际友谊</td><td title="开赛时间：2026-09-24 19:35">19:35</td>
<td><a id="HomeTeam_1">中国</a></td><td>-</td><td><a id="GuestTeam_1">马尔代夫</a></td><td></td><td></td>
<td><a href="//live.nowscore.com/odds/match/3003888.htm">亚</a></td></tr></table>'''

ODDS = '''<table><tr class="datatr"><td>澳*</td>
<td>0.93</td><td>半球</td><td>0.91</td><td>0.86</td><td>半/一</td><td>0.98</td>
<td>1.93</td><td>3.45</td><td>3.28</td><td>1.55</td><td>4.15</td><td>4.45</td>
<td>0.81</td><td>2.5</td><td>0.99</td><td>0.84</td><td>2.5/3</td><td>0.96</td>
<td><a href="/odds/3in1Odds.aspx?companyid=1&amp;id=3003894">详</a></td></tr></table>'''


def test_cp_mapping_uses_team_and_kickoff_to_disambiguate_number():
    day, rows = parse_cp_page(CP)
    assert day == "2026-09-20"
    fixtures = [{"match_id": "2026-09-20|010", "match_number": "010", "home_team": "利兹联",
                 "away_team": "水晶宫", "kickoff": "2026-09-20T21:00:00+08:00"}]
    aligned = align_cp_to_scan(rows, fixtures, day)
    assert aligned[0]["mapping_status"] == "mapped"
    assert aligned[0]["nowscore_match_id"] == "3003894"


def test_cp_page_assigns_each_row_to_its_nearest_sales_day_heading():
    day, rows = parse_cp_page(MULTI_DAY_CP)
    assert day == "2026-09-24"
    assert [row["sales_day"] for row in rows] == ["2026-09-23", "2026-09-24"]
    fixtures = [{"match_id": "2026-09-24|003", "match_number": "003", "home_team": "中国",
                 "away_team": "马尔代夫", "kickoff": "2026-09-24T19:35:00+08:00"}]
    aligned = align_cp_to_scan(rows, fixtures, "2026-09-24")
    assert aligned[0]["mapping_status"] == "mapped"
    assert aligned[0]["nowscore_match_id"] == "3003888"


def test_odds_quotes_and_post_kickoff_gate():
    quotes = parse_odds_page(ODDS, "3003894")
    assert len(quotes) == 6
    current = next(q for q in quotes if q["market"] == "asian_handicap" and q["stage"] == "current")
    assert current["home_handicap"] == -0.75
    assert current["home_odds"] == 1.86
    assert current["bookmaker_id"] == "1"
    fixture = {"match_id": "2026-09-20|010", "nowscore_match_id": "3003894", "kickoff": "2026-09-20T21:00:00+08:00",
               "mapping_status": "mapped", "home_team": "利兹联", "away_team": "水晶宫"}
    kickoff = datetime.fromisoformat(fixture["kickoff"]).astimezone(timezone.utc)
    before = to_outer_rows(quotes, fixture, kickoff - timedelta(minutes=1), "abc", "raw.html")
    after = to_outer_rows(quotes, fixture, kickoff + timedelta(minutes=1), "abc", "raw.html")
    assert before[0]["eligible_for_research"] is True
    assert after[0]["eligible_for_research"] is False
    assert after[0]["reject_reason"] == "post_kickoff"


def test_asian_handicap_sign():
    assert asian_line("半/一") == -0.75
    assert asian_line("*半球") == 0.5
    assert asian_line("平手") == 0
    assert asian_line("unknown") is None
