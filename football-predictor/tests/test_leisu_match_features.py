from __future__ import annotations

import pandas as pd

from world_cup.leisu_match_features import (
    attach_leisu_features_to_fixtures,
    normalize_leisu_team,
)


def test_normalize_leisu_team_maps_chinese_national_team():
    assert normalize_leisu_team("伊朗") == "Iran"
    assert normalize_leisu_team("新西兰") == "New Zealand"


def test_attach_leisu_features_matches_timezone_shifted_fixture():
    fixtures = pd.DataFrame(
        [
            {
                "match_id": 760428,
                "date": "2026-06-15",
                "home_team": "Spain",
                "away_team": "Cape Verde",
            }
        ]
    )
    leisu = pd.DataFrame(
        [
            {
                "leisu_match_id": "4460923",
                "competition": "世界杯",
                "date_text": "06-16",
                "time_text": "00:00",
                "home_team_zh": "西班牙",
                "away_team_zh": "佛得角",
                "detail_url": "https://live.leisu.com/detail-4460923",
                "analysis_url": "https://live.leisu.com/shujufenxi-4460923",
                "intelligence_url": "https://www.leisu.com/guide/swot-4460923",
                "intelligence_count": 25,
            }
        ]
    )

    out = attach_leisu_features_to_fixtures(fixtures, leisu, year=2026)

    assert len(out) == 1
    assert out.loc[0, "leisu_public_match_linked"] == 1
    assert out.loc[0, "leisu_match_id"] == "4460923"
    assert out.loc[0, "leisu_date_delta_days"] == 1
    assert out.loc[0, "leisu_intelligence_count"] == 25
