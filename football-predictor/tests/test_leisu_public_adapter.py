from __future__ import annotations

from world_cup.leisu_public_adapter import parse_leisu_home_matches


def test_parse_leisu_home_matches_extracts_world_cup_fixture():
    html = """
    <div class="match-lier"><div class="match-label box_h">
    <div class="time"><span class="timecolor">09:00</span> <span>06-16</span></div>
    <div class="eventname"><a class="link" href="https://www.leisu.com/data/zuqiu/comp-1" target="_blank">世界杯</a> </div>
    <div class="home"><span class="name">伊朗</span></div>
    <div class="td score"><a class="link" href="https://live.leisu.com/detail-4460956" target="_blank"></a></div>
    <div class="away"><span class="name">新西兰</span></div>
    <a class="v-icon" href="https://www.leisu.com/guide/swot-4460956" target="_blank">情报 27</a>
    </div></div>
    """

    out = parse_leisu_home_matches(html, fetched_at="2026-06-16T00:00:00+00:00")

    assert len(out) == 1
    assert out.loc[0, "leisu_match_id"] == "4460956"
    assert out.loc[0, "competition"] == "世界杯"
    assert out.loc[0, "home_team_zh"] == "伊朗"
    assert out.loc[0, "intelligence_count"] == 27
