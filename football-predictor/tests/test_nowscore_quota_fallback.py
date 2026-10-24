from __future__ import annotations

import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import capture_nowscore_market as worker  # noqa: E402


def test_fallback_triggers_for_supported_primary_failures(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(worker, "capture", lambda *args, **kwargs: calls.append(args) or {"status": "complete"})
    scan = {"sales_day": "2026-09-21", "fixtures": []}
    assert worker.capture_on_quota_failure(scan, {"status": "complete"}, tmp_path)["status"] == "not_triggered"
    assert not calls
    for status in ("quota_insufficient", "no_routed_sports", "not_configured", "source_failed", "unmatched", "partial"):
        result = worker.capture_on_external_failure(scan, {"status": status}, tmp_path)
        assert result["status"] == "complete"
        assert result["trigger_status"] == status
    assert len(calls) == 6


def test_fallback_failure_is_non_blocking(monkeypatch, tmp_path):
    def fail(*args, **kwargs):
        raise ValueError("sales day mismatch")
    monkeypatch.setattr(worker, "capture", fail)
    result = worker.capture_on_external_failure({"sales_day": "2026-09-21"}, {"status": "no_routed_sports"}, tmp_path)
    assert result["status"] == "source_failed"
    assert result["reason"] == "ValueError"
    assert result["trigger_status"] == "no_routed_sports"


def test_effective_status_exposes_fallback_without_hiding_primary_failure():
    result = worker.effective_external_status(
        {"status": "no_routed_sports"},
        {"status": "complete", "captured_match_count": 4, "research_eligible_rows": 54},
    )
    assert result["primary_status"] == "no_routed_sports"
    assert result["effective_status"] == "available_via_nowscore"
    assert result["external_data_available"] is True
    assert result["production_model_feature_ready"] is False


def test_offline_capture_only_uses_verified_future_on_sale_fixture(tmp_path):
    local = datetime.now(ZoneInfo("Asia/Shanghai")) + timedelta(hours=2)
    day = local.strftime("%Y-%m-%d")
    kickoff = local.strftime("%Y-%m-%d %H:%M")
    cp = f'''<div>{local.year}年{local.month:02d}月{local.day:02d}日</div><table>
    <tr matchid="88" gamename="英超"><td>010</td><td>英超</td><td title="开赛时间：{kickoff}">{local:%H:%M}</td>
    <td><a id="HomeTeam_1">利兹联</a></td><td>0-0</td><td><a id="GuestTeam_1">水晶宫</a></td><td></td><td></td>
    <td><a href="//live.nowscore.com/odds/match/3003894.htm">亚</a></td></tr></table>'''
    odds = '''<table><tr class="datatr"><td>澳*</td>
    <td>0.93</td><td>半球</td><td>0.91</td><td>0.86</td><td>半/一</td><td>0.98</td>
    <td>1.93</td><td>3.45</td><td>3.28</td><td>1.55</td><td>4.15</td><td>4.45</td>
    <td>0.81</td><td>2.5</td><td>0.99</td><td>0.84</td><td>2.5/3</td><td>0.96</td>
    <td><a href="/odds/3in1Odds.aspx?companyid=1&amp;id=3003894">详</a></td></tr></table>'''
    cp_path = tmp_path / "cp.html"
    cp_path.write_text(cp, encoding="utf-8")
    odds_dir = tmp_path / "odds"
    odds_dir.mkdir()
    (odds_dir / "3003894.html").write_text(odds, encoding="utf-8")
    scan = {"sales_day": day, "fixtures": [
        {"match_id": f"{day}|010", "match_number": "010", "home_team": "利兹联", "away_team": "水晶宫",
         "kickoff": local.isoformat(), "sale_status": "on_sale"},
        {"match_id": f"{day}|011", "match_number": "011", "home_team": "其他", "away_team": "其他",
         "kickoff": local.isoformat(), "sale_status": "stopped"},
    ]}
    result = worker.capture(scan, tmp_path / "output", cp_path, odds_dir)
    assert result["status"] == "complete"
    assert result["eligible_on_sale_matches"] == 1
    assert result["captured_match_count"] == 1
    assert result["research_eligible_rows"] == 0
    with (Path(result["snapshot_dir"]) / "outer_market.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1
    assert rows[0]["eligible_for_research"] == "False"
    assert rows[0]["reject_reason"] == "offline_capture_time_unverified"


ASIAN_XML = '''<?xml version="1.0" encoding="utf-8"?><odds issueNum="2026147">
<i>1,5560001,17841227,0.88,0.25,0.96</i><i>3,5560001,17837514,0.80,0.25,1.08</i></odds>'''
TOTALS_XML = '''<?xml version="1.0" encoding="utf-8"?><odds issueNum="2026147">
<i>1,5560001,20660533,0.81,2.5,0.99</i></odds>'''
H2H_XML = '''<?xml version="1.0" encoding="utf-8"?><odds issueNum="2026147">
<i>1,5560001,22963914,2.11,3.80,2.58,2.11,3.85,2.55</i></odds>'''
CHANGE_HTML = '''<TABLE><TR><TD>近5次变化记录</TD></TR>
<TR><TD>主队</TD><TD>盘口</TD><TD>客队</TD><TD>变化时间</TD></TR>
<TR><TD>0.88</TD><TD>平手/半球</TD><TD>0.96</TD><TD>10-19 17:56初</TD></TR></TABLE>'''


def test_odds_page_failure_falls_back_to_the_cp_feeds(monkeypatch, tmp_path):
    local = datetime.now(ZoneInfo("Asia/Shanghai")) + timedelta(hours=2)
    day = local.strftime("%Y-%m-%d")
    kickoff = local.strftime("%Y-%m-%d %H:%M")
    cp = f'''<div>{local.year}年{local.month:02d}月{local.day:02d}日</div><table>
    <tr matchid="5560001" gamename="日职"><td>001</td><td>日职</td><td title="开赛时间：{kickoff}">{local:%H:%M}</td>
    <td><a id="HomeTeam_1">东京FC</a></td><td>0-0</td><td><a id="GuestTeam_1">柏太阳神</a></td><td></td><td></td>
    <td><a href="//live.nowscore.com/odds/match/3000494.htm">亚</a></td></tr></table>'''
    requested = []

    def fake_read(path, url, session):
        requested.append(url)
        if url == "https://cp.nowscore.com/":
            return cp.encode("utf-8")
        if "/odds/match/" in url:
            raise worker.requests.RequestException("odds page unavailable")
        if "yp101.xml" in url:
            return ASIAN_XML.encode("utf-8")
        if "dx101.xml" in url:
            return TOTALS_XML.encode("utf-8")
        if "op101.xml" in url:
            return H2H_XML.encode("utf-8")
        if "odds.aspx" in url:
            return CHANGE_HTML.encode("utf-8")
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(worker, "_read_html", fake_read)
    scan = {"sales_day": day, "fixtures": [
        {"match_id": f"{day}|001", "match_number": "001", "home_team": "东京FC", "away_team": "柏太阳神",
         "kickoff": local.isoformat(), "sale_status": "on_sale"},
    ]}
    result = worker.capture(scan, tmp_path / "output", change_bookmakers=("1",))
    assert result["status"] == "complete"
    assert result["failures"] == []
    assert result["page_failures"][0]["reason"] == "RequestException"
    assert result["fallback_match_count"] == 1
    assert result["captured_match_count"] == 1
    assert result["research_eligible_rows"] == 2
    assert result["cp_feed_row_counts"] == {"asian": 2, "totals": 1, "h2h": 2}
    assert result["price_change_rows"] == 1
    assert result["price_change_requests"] == 1
    assert not result["change_failures"]
    snapshot = Path(result["snapshot_dir"])
    with (snapshot / "price_changes.csv").open(encoding="utf-8-sig", newline="") as stream:
        changes = list(csv.DictReader(stream))
    assert [row["bookmaker_id"] for row in changes] == ["1"]
    assert changes[0]["handicap"] == "-0.25"
    assert changes[0]["is_opening"] == "True"
    assert changes[0]["match_id"] == f"{day}|001"
    assert (snapshot / "raw" / "cp_asian.xml").exists()
    assert "https://cp.nowscore.com/data/yp101.xml?x=1" in requested


def test_page_failure_without_cp_feed_coverage_is_still_a_failure(monkeypatch, tmp_path):
    local = datetime.now(ZoneInfo("Asia/Shanghai")) + timedelta(hours=2)
    day = local.strftime("%Y-%m-%d")
    kickoff = local.strftime("%Y-%m-%d %H:%M")
    cp = f'''<div>{local.year}年{local.month:02d}月{local.day:02d}日</div><table>
    <tr matchid="5560009" gamename="日职"><td>001</td><td>日职</td><td title="开赛时间：{kickoff}">{local:%H:%M}</td>
    <td><a id="HomeTeam_1">东京FC</a></td><td>0-0</td><td><a id="GuestTeam_1">柏太阳神</a></td><td></td><td></td>
    <td><a href="//live.nowscore.com/odds/match/3000494.htm">亚</a></td></tr></table>'''

    def fake_read(path, url, session):
        if url == "https://cp.nowscore.com/":
            return cp.encode("utf-8")
        if "/odds/match/" in url:
            raise worker.requests.RequestException("odds page unavailable")
        if "yp101.xml" in url:
            return ASIAN_XML.encode("utf-8")
        return b"<odds></odds>"

    monkeypatch.setattr(worker, "_read_html", fake_read)
    scan = {"sales_day": day, "fixtures": [
        {"match_id": f"{day}|001", "match_number": "001", "home_team": "东京FC", "away_team": "柏太阳神",
         "kickoff": local.isoformat(), "sale_status": "on_sale"},
    ]}
    result = worker.capture(scan, tmp_path / "output")
    assert result["status"] == "partial"
    assert result["fallback_match_count"] == 0
    assert result["failures"][0]["reason"] == "RequestException"
