from __future__ import annotations

import pandas as pd

from scripts.build_sporttery_fixture_file import build_sporttery_fixtures


def test_build_sporttery_fixtures_normalizes_chinese_team_names():
    markets = pd.DataFrame(
        [
            {
                "date": "2026-06-26",
                "match_number": "055",
                "home_team": "厄瓜多尔",
                "away_team": "德国",
                "source": "lottery.gov.cn:zqspf",
                "kickoff_time": "2026-06-26 04:00",
            }
        ]
    )

    fixtures = build_sporttery_fixtures(markets)

    assert fixtures.loc[0, "match_id"] == "sporttery_2026-06-26_055"
    assert fixtures.loc[0, "home_team"] == "Ecuador"
    assert fixtures.loc[0, "away_team"] == "Germany"
