from __future__ import annotations

from data.external_calendar import build_team_lookup, parse_football_txt


def test_parse_football_txt_infers_season_years():
    text = """
= Test Cup 2024/25
  Tue Dec 31 2024
    20:00  Manchester City FC (ENG) v Arsenal FC (ENG)       2-1 (1-0)
  Wed Jan 8
    20:00  Arsenal FC (ENG)        v Manchester United (ENG) 1-0 (0-0)
"""
    out = parse_football_txt(text, season="2024-25", competition="test")

    assert out["date"].tolist() == ["2024-12-31", "2025-01-08"]
    assert out.loc[0, "home_team_source"] == "Manchester City FC (ENG)"


def test_team_lookup_uses_explicit_aliases_only():
    lookup = build_team_lookup({"Man City", "Arsenal", "Nott'm Forest"})

    assert lookup["manchester city fc"] == "Man City"
    assert lookup["arsenal fc"] == "Arsenal"
    assert lookup["nottingham forest"] == "Nott'm Forest"
    assert "manchester" not in lookup
