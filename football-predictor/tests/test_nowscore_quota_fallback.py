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
