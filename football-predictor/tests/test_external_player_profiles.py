from __future__ import annotations

import pandas as pd

from world_cup.external_player_profiles import apply_external_player_profiles
from world_cup.external_player_profiles import normalize_external_player_profiles
from world_cup.external_player_profiles import profile_source_summary


def test_external_player_profiles_normalize_source_rows():
    profiles = normalize_external_player_profiles(
        pd.DataFrame(
            [
                {
                    "source": "transfermarkt",
                    "source_player_id": "tm-10",
                    "source_url": "https://www.transfermarkt.com/player/profil/spieler/10",
                    "player_id": "p10",
                    "canonical_name": "Player Ten",
                    "national_team": "Germany",
                    "primary_position": "Midfielder",
                    "market_value_eur": "85000000",
                    "height_cm": "181",
                    "availability_status": "Suspension",
                    "confidence": "0.9",
                }
            ]
        )
    )

    summary = profile_source_summary(profiles)

    assert profiles.loc[0, "market_value_eur"] == 85000000
    assert profiles.loc[0, "availability_status"] == "suspended"
    assert profiles.loc[0, "national_team"] == "Germany"
    assert summary["players_with_market_value"] == 1
    assert summary["players_with_availability_signal"] == 1


def test_external_profiles_blend_market_value_into_strengths():
    strengths = pd.DataFrame(
        [
            {
                "player_id": "p1",
                "canonical_name": "A",
                "national_team": "Germany",
                "primary_position": "Forward",
                "player_strength_score": 0.40,
                "relative_player_strength": 0.0,
                "player_strength_confidence": 0.2,
            },
            {
                "player_id": "p2",
                "canonical_name": "B",
                "national_team": "Germany",
                "primary_position": "Forward",
                "player_strength_score": 0.40,
                "relative_player_strength": 0.0,
                "player_strength_confidence": 0.2,
            },
        ]
    )
    profiles = normalize_external_player_profiles(
        pd.DataFrame(
            [
                {
                    "source": "transfermarkt",
                    "player_id": "p1",
                    "canonical_name": "A",
                    "national_team": "Germany",
                    "market_value_eur": 100000000,
                    "confidence": 1.0,
                },
                {
                    "source": "transfermarkt",
                    "player_id": "p2",
                    "canonical_name": "B",
                    "national_team": "Germany",
                    "market_value_eur": 1000000,
                    "confidence": 1.0,
                },
            ]
        )
    )

    enriched = apply_external_player_profiles(strengths, profiles, weight=0.2)
    by_player = enriched.set_index("player_id")

    assert by_player.loc["p1", "player_strength_score"] > by_player.loc["p2", "player_strength_score"]
    assert by_player.loc["p1", "external_profile_source"] == "transfermarkt"
    assert by_player.loc["p1", "player_strength_confidence"] >= 0.2
