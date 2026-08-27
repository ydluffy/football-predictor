from __future__ import annotations

import pandas as pd

from world_cup.public_absence_intelligence import aggregate_public_absences
from world_cup.public_absence_intelligence import normalize_public_absence_intelligence
from world_cup.public_absence_intelligence import public_absence_summary


def test_public_absence_intelligence_normalizes_and_aggregates_verified_rows():
    intelligence = normalize_public_absence_intelligence(
        pd.DataFrame(
            [
                {
                    "date": "2026-06-27",
                    "team": "Germany",
                    "player": "Player A",
                    "status": "Injury",
                    "impact": "1.5",
                    "reason": "hamstring",
                    "source": "transfermarkt",
                    "source_url": "https://www.transfermarkt.com/a",
                    "confidence": "",
                },
                {
                    "date": "2026-06-27",
                    "team": "Germany",
                    "player": "Player A",
                    "status": "doubtful",
                    "impact": "0.5",
                    "reason": "late fitness test",
                    "source": "sports_mole",
                    "source_url": "https://www.sportsmole.co.uk/a",
                    "confidence": "0.65",
                },
                {
                    "date": "2026-06-27",
                    "team": "Ecuador",
                    "player": "Player B",
                    "status": "injured",
                    "impact": "1.0",
                    "reason": "rumour",
                    "source": "unknown_blog",
                    "source_url": "https://example.com",
                    "confidence": "0.4",
                },
            ]
        )
    )
    absences = aggregate_public_absences(intelligence, min_confidence=0.6)
    summary = public_absence_summary(intelligence, absences)

    assert len(intelligence) == 3
    assert len(absences) == 1
    row = absences.iloc[0]
    assert row["team"] == "Germany"
    assert row["status"] == "injured"
    assert row["impact"] == 1.5
    assert row["source"] == "sports_mole+transfermarkt"
    assert "transfermarkt.com" in row["source_url"]
    assert summary["intelligence_rows"] == 3
    assert summary["model_absence_rows"] == 1


def test_public_absence_intelligence_drops_unusable_rows():
    intelligence = normalize_public_absence_intelligence(
        pd.DataFrame(
            [
                {"date": "", "team": "Germany", "player": "A", "status": "injured"},
                {"date": "2026-06-27", "team": "", "player": "A", "status": "injured"},
                {"date": "2026-06-27", "team": "Germany", "player": "", "status": "injured"},
                {"date": "2026-06-27", "team": "Germany", "player": "A", "status": "available"},
            ]
        )
    )

    assert len(intelligence) == 1
    assert intelligence.iloc[0]["status"] == "available"
    assert aggregate_public_absences(intelligence).empty
