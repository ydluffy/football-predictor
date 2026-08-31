from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from world_cup.player_data import PlayerDataBundle
from world_cup.squad_features import build_fixture_squad_features


@dataclass(frozen=True)
class LineupAdjustmentConfig:
    max_goal_shift: float = 0.10
    strength_scale: float = 0.015
    availability_weight: float = 0.35
    continuity_weight: float = 0.25
    experience_weight: float = 0.20
    chemistry_weight: float = 0.10
    load_weight: float = 0.10
    player_strength_weight: float = 0.25
    player_strength_scale: float = 0.08


def _team_strength(
    features: pd.Series,
    prefix: str,
    config: LineupAdjustmentConfig,
) -> dict[str, float]:
    starters = float(features.get(f"{prefix}_expected_starters", 0.0))
    confirmed = starters >= 10.5
    if not confirmed:
        return {
            f"{prefix}_lineup_confirmed": 0.0,
            f"{prefix}_lineup_strength_score": 0.0,
            f"{prefix}_lineup_confidence": 0.0,
        }

    available_rate = float(features.get(f"{prefix}_starter_available_rate", 0.0))
    if available_rate == 0.0:
        available_rate = 0.5
    continuity = float(features.get(f"{prefix}_previous_lineup_retention", 0.0))
    caps = float(features.get(f"{prefix}_average_national_caps", 0.0))
    shared = float(features.get(f"{prefix}_average_shared_starts", 0.0))
    load_14 = float(features.get(f"{prefix}_starter_recent_load_14", 0.0))

    experience_component = float(np.tanh(caps / 5.0))
    chemistry_component = float(np.tanh(shared / 4.0))
    load_component = -float(np.clip((load_14 - 990.0) / 990.0, 0.0, 1.0))
    player_strength_component = float(
        np.tanh(
            float(features.get(f"{prefix}_lineup_relative_strength", 0.0))
            * config.player_strength_scale
        )
    )
    availability_component = available_rate - 0.5
    continuity_component = continuity - 0.5
    score = (
        config.availability_weight * availability_component
        + config.continuity_weight * continuity_component
        + config.experience_weight * experience_component
        + config.chemistry_weight * chemistry_component
        + config.load_weight * load_component
        + config.player_strength_weight * player_strength_component
    )
    return {
        f"{prefix}_lineup_confirmed": 1.0,
        f"{prefix}_lineup_strength_score": float(score),
        f"{prefix}_lineup_confidence": 1.0,
    }


def build_fixture_lineup_adjustments(
    bundle: PlayerDataBundle,
    fixtures: pd.DataFrame,
    *,
    player_strengths: pd.DataFrame | None = None,
    config: LineupAdjustmentConfig | None = None,
) -> pd.DataFrame:
    cfg = config or LineupAdjustmentConfig()
    squad_features = build_fixture_squad_features(bundle, fixtures)
    if player_strengths is not None and not player_strengths.empty:
        strength_features = build_fixture_lineup_strength_features(
            bundle,
            fixtures,
            player_strengths,
        )
        squad_features = pd.concat(
            [squad_features.reset_index(drop=True), strength_features.reset_index(drop=True)],
            axis=1,
        )
    rows = []
    for _, feature_row in squad_features.iterrows():
        home = _team_strength(feature_row, "home", cfg)
        away = _team_strength(feature_row, "away", cfg)
        diff = home["home_lineup_strength_score"] - away["away_lineup_strength_score"]
        shift = float(np.clip(diff * cfg.strength_scale, -cfg.max_goal_shift, cfg.max_goal_shift))
        both_confirmed = min(
            home["home_lineup_confirmed"],
            away["away_lineup_confirmed"],
        )
        rows.append(
            {
                **home,
                **away,
                "lineup_strength_diff": float(diff),
                "lineup_goal_shift": shift if both_confirmed else 0.0,
                "home_goal_multiplier": float(np.exp(shift)) if both_confirmed else 1.0,
                "away_goal_multiplier": float(np.exp(-shift)) if both_confirmed else 1.0,
                "lineup_adjustment_active": float(both_confirmed),
            }
        )
    return pd.concat(
        [squad_features.reset_index(drop=True), pd.DataFrame(rows)],
        axis=1,
    )


def _lineup_strength_for_team(
    bundle: PlayerDataBundle,
    *,
    team: str,
    as_of_date: pd.Timestamp,
    player_strengths: pd.DataFrame,
) -> dict[str, float]:
    eligible = bundle.squads[
        bundle.squads["team"].eq(team)
        & bundle.squads["snapshot_date"].le(as_of_date)
    ]
    if eligible.empty:
        return {
            "lineup_relative_strength": 0.0,
            "lineup_strength_confidence": 0.0,
        }
    latest = eligible["snapshot_date"].max()
    squad = eligible[eligible["snapshot_date"].eq(latest)].copy()
    starters = squad[squad["role"].eq("starter")]
    if len(starters) < 11:
        return {
            "lineup_relative_strength": 0.0,
            "lineup_strength_confidence": 0.0,
        }
    strength = player_strengths[
        ["player_id", "relative_player_strength", "player_strength_confidence"]
    ].copy()
    merged = starters.merge(strength, on="player_id", how="left")
    return {
        "lineup_relative_strength": float(
            pd.to_numeric(merged["relative_player_strength"], errors="coerce")
            .fillna(0.0)
            .sum()
        ),
        "lineup_strength_confidence": float(
            pd.to_numeric(merged["player_strength_confidence"], errors="coerce")
            .fillna(0.0)
            .mean()
        ),
    }


def build_fixture_lineup_strength_features(
    bundle: PlayerDataBundle,
    fixtures: pd.DataFrame,
    player_strengths: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for fixture in fixtures.itertuples(index=False):
        cutoff = pd.Timestamp(getattr(fixture, "date")).normalize()
        home = _lineup_strength_for_team(
            bundle,
            team=str(getattr(fixture, "home_team")),
            as_of_date=cutoff,
            player_strengths=player_strengths,
        )
        away = _lineup_strength_for_team(
            bundle,
            team=str(getattr(fixture, "away_team")),
            as_of_date=cutoff,
            player_strengths=player_strengths,
        )
        rows.append(
            {
                "home_lineup_relative_strength": home["lineup_relative_strength"],
                "away_lineup_relative_strength": away["lineup_relative_strength"],
                "lineup_relative_strength_diff": (
                    home["lineup_relative_strength"] - away["lineup_relative_strength"]
                ),
                "home_player_strength_confidence": home["lineup_strength_confidence"],
                "away_player_strength_confidence": away["lineup_strength_confidence"],
            }
        )
    return pd.DataFrame(rows, index=fixtures.index)
