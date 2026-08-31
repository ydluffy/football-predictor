from __future__ import annotations

import pandas as pd

from world_cup.realtime_sources import absence_goal_shift
from world_cup.realtime_sources import find_line_movement
from world_cup.realtime_sources import find_realtime_lineup
from world_cup.realtime_sources import find_team_absences
from world_cup.realtime_sources import load_absence_index
from world_cup.realtime_sources import load_line_movement_index
from world_cup.realtime_sources import load_realtime_lineup_index
from world_cup.realtime_sources import load_structured_intelligence_index


def test_realtime_source_indexes_parse_all_core_feeds(tmp_path):
    line_path = tmp_path / "line_movement.csv"
    pd.DataFrame(
        [
            {
                "date": "2026-06-26",
                "home_team": "Ecuador",
                "away_team": "Germany",
                "opening_home_handicap": 0,
                "latest_home_handicap": 1,
                "handicap_line_delta": 1,
                "handicap_movement_direction": "toward_away",
                "favorite_movement": "shallower",
                "snapshots": 2,
            }
        ]
    ).to_csv(line_path, index=False)

    intelligence_path = tmp_path / "intel.csv"
    pd.DataFrame(
        [
            {"match_id": "760468", "category": "injury", "severity": 2},
            {"match_id": "760468", "category": "tactical", "severity": 1},
        ]
    ).to_csv(intelligence_path, index=False)

    absences_path = tmp_path / "absences.csv"
    pd.DataFrame(
        [
            {"date": "2026-06-26", "team": "Germany", "player": "A", "status": "injured", "impact": 2},
            {"date": "2026-06-26", "team": "Ecuador", "player": "B", "status": "doubtful", "impact": 1},
        ]
    ).to_csv(absences_path, index=False)

    lineups_path = tmp_path / "lineups.csv"
    pd.DataFrame(
        [
            {"match_id": "760468", "team": "Germany", "player": f"G{i}", "role": "starter", "confirmed": 1}
            for i in range(11)
        ]
    ).to_csv(lineups_path, index=False)

    movement = find_line_movement(
        load_line_movement_index(line_path),
        date="2026-06-25",
        home_team="Ecuador",
        away_team="Germany",
    )
    intelligence = load_structured_intelligence_index(intelligence_path)["760468"]
    absences = load_absence_index(absences_path)
    germany = find_team_absences(absences, date="2026-06-25", team="Germany")
    ecuador = find_team_absences(absences, date="2026-06-25", team="Ecuador")
    lineup = find_realtime_lineup(
        load_realtime_lineup_index(lineups_path),
        match_id="760468",
        team="Germany",
    )

    assert movement["snapshots"] == 2
    assert intelligence["structured_injury_count"] == 1
    assert germany["absence_weighted_impact"] == 2.0
    assert ecuador["absence_weighted_impact"] == 0.5
    assert absence_goal_shift(ecuador, germany) > 0
    assert lineup["realtime_lineup_confirmed"] == 1
    assert lineup["realtime_starters"] == 11
