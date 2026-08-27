from __future__ import annotations

from strategy.sporttery_sales_window import build_scan_result


def _fixture(competition: str) -> dict[str, str]:
    return {
        "match_number": "001",
        "competition": competition,
        "kickoff": "2026-08-09T19:00:00+08:00",
        "home_team": "横滨水手",
        "away_team": "鹿岛鹿角",
        "spf_odds_home": "2.10",
        "spf_odds_draw": "3.20",
        "spf_odds_away": "3.05",
    }


def test_sales_scan_exposes_competition_and_safe_model_routing() -> None:
    scan = build_scan_result(
        stage="confirm",
        as_of="2026-08-09T11:05:00+08:00",
        sales_day="2026-08-09",
        official_rows=[_fixture("日职联")],
        play_rows=[],
    )

    fixture = scan["fixtures"][0]
    assert fixture["competition_id"] == "JPN_J1_LEAGUE"
    assert fixture["home_team_canonical"] == "Yokohama F. Marinos"
    assert fixture["historical_model_coverage"] is False
    assert fixture["recommended_model_route"] == "market_anchor_fallback"
    assert scan["summary"]["model_fallback_required"] == 1


def test_unknown_competition_is_never_silently_routed_to_club_model() -> None:
    scan = build_scan_result(
        stage="confirm",
        as_of="2026-08-09T11:05:00+08:00",
        sales_day="2026-08-09",
        official_rows=[_fixture("未知测试杯")],
        play_rows=[],
    )

    fixture = scan["fixtures"][0]
    assert fixture["competition_id"] == "UNKNOWN"
    assert fixture["model_route_status"] == "fallback_required"
    assert scan["summary"]["competition_unknown"] == 1
