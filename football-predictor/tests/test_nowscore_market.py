from __future__ import annotations

from datetime import datetime, timedelta, timezone

from data.nowscore_market import (
    align_cp_to_scan,
    asian_line,
    long_asian_line,
    parse_asian_xml,
    parse_change_table,
    parse_cp_page,
    parse_h2h_xml,
    parse_odds_page,
    parse_totals_xml,
    to_outer_rows,
    xml_quotes,
)


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


ASIAN_XML = '''<?xml version="1.0" encoding="utf-8"?><odds issueNum="2026147">
<i>1,5560001,17841227,0.88,0.25,0.96</i><i>3,5560001,17837514,0.80,0.25,1.08</i>
<i>1,5560003,17841160,0.90,0.5,0.88</i></odds>'''

TOTALS_XML = '''<?xml version="1.0" encoding="utf-8"?><odds issueNum="2026147">
<i>1,5560001,20660533,0.81,2.5,0.99</i></odds>'''

H2H_XML = '''<?xml version="1.0" encoding="utf-8"?><odds issueNum="2026147">
<i>1,5560003,22963914,2.11,3.80,2.58,2.11,3.85,2.55</i>
<i>0,5560003,22963110,2.12,3.70,2.60,2.10,3.80,2.55</i></odds>'''

CHANGE_HTML = '''<TABLE cellSpacing=1 cellPadding=0 width=280 align=center bgColor=#aaaaaa border=0>
<TR align=center bgColor=#008AFF height=20><TD colspan=4><FONT color=#ffffff>近5次变化记录</FONT></TD></TR>
<TR align=center bgColor=#008AFF height=20>
<TD width=50><b><FONT color=#ffffff>主队</FONT></b></TD>
<TD width=90><b><FONT color=#ffffff>盘口</FONT></b></TD>
<TD width=50><b><FONT color=#ffffff>客队</FONT></b></TD>
<TD><FONT color=#ffffff><B>变化时间</B></FONT></TD></TR>
<TR align=center bgColor=#ffffff><TD height=22><FONT color=><B>0.88</B></FONT></TD>
<TD><FONT color=>平手/半球</TD><TD><B>0.96</B></TD><TD>10-19 17:56初</TD></TR>
<TR align=center bgColor=#ffffff><TD height=22><FONT color=><B>0.90</B></FONT></TD>
<TD><FONT color=>受平手/半球</TD><TD><B>0.94</B></TD><TD>10-20 09:12</TD></TR>
</TABLE>'''


def test_cp_xml_feeds_match_the_page_handicap_semantics():
    asian = parse_asian_xml(ASIAN_XML)
    assert sorted(asian) == ["5560001", "5560003"]
    first = asian["5560001"][0]
    assert first["bookmaker_id"] == "1"
    assert first["odds_id"] == "17841227"
    assert first["home_handicap"] == -0.25
    assert first["home_odds"] == 1.88
    assert first["away_odds"] == 1.96
    assert asian["5560003"][0]["home_handicap"] == -0.5
    assert parse_totals_xml(TOTALS_XML)["5560001"][0]["over_odds"] == 1.81
    h2h = parse_h2h_xml(H2H_XML)["5560003"]
    assert [row["stage"] for row in h2h] == ["opening", "current", "opening", "current"]
    assert h2h[0]["home_odds"] == 2.11
    assert h2h[1]["away_odds"] == 2.55


def test_xml_quotes_fall_back_to_the_competition_match_id():
    feeds = {"asian": parse_asian_xml(ASIAN_XML), "totals": parse_totals_xml(TOTALS_XML),
             "h2h": parse_h2h_xml(H2H_XML)}
    quotes = xml_quotes(feeds, "5560001", "3000494")
    assert {quote["nowscore_match_id"] for quote in quotes} == {"3000494"}
    assert {quote["market"] for quote in quotes} == {"asian_handicap", "totals"}
    assert xml_quotes(feeds, "", "3000494") == []


def test_change_table_exposes_direction_and_opening_flag():
    rows = parse_change_table(CHANGE_HTML)
    assert len(rows) == 2
    assert rows[0] == {"home_price_raw": "0.88", "handicap_raw": "平手/半球", "away_price_raw": "0.96",
                       "changed_at_raw": "10-19 17:56初", "home_odds": 1.88, "away_odds": 1.96,
                       "handicap": -0.25, "is_opening": True}
    assert rows[1]["handicap"] == 0.25
    assert rows[1]["is_opening"] is False
    assert long_asian_line("三球/三球半") == -3.25
    assert long_asian_line("未知") is None

