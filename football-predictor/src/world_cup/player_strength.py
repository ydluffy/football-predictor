from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from world_cup.player_data import PlayerDataBundle


@dataclass(frozen=True)
class PlayerStrengthConfig:
    age_weight: float = 0.35
    experience_weight: float = 0.45
    starter_weight: float = 0.20
    club_minutes_weight: float = 0.25
    club_attack_weight: float = 0.15
    max_evidence_matches: int = 8
    club_window_days: int = 90


POSITION_PEAK_AGE = {
    "Goalkeeper": 30.0,
    "Defender": 28.0,
    "Midfielder": 27.0,
    "Forward": 27.0,
}


def _age_score(row: pd.Series, as_of_date: pd.Timestamp) -> float:
    birth = pd.to_datetime(row.get("date_of_birth"), errors="coerce")
    if pd.isna(birth):
        return 0.5
    age = (as_of_date - birth).days / 365.25
    peak = POSITION_PEAK_AGE.get(str(row.get("primary_position", "")).strip(), 27.0)
    return float(np.exp(-((age - peak) / 7.5) ** 2))


def _safe_zscore(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").fillna(0.0)
    std = float(numeric.std(ddof=0))
    if std < 1e-9:
        return pd.Series(0.0, index=values.index)
    return (numeric - float(numeric.mean())) / std


def build_player_strengths(
    bundle: PlayerDataBundle,
    *,
    as_of_date: str | pd.Timestamp,
    config: PlayerStrengthConfig | None = None,
) -> pd.DataFrame:
    cfg = config or PlayerStrengthConfig()
    cutoff = pd.Timestamp(as_of_date).normalize()
    players = bundle.players.copy()
    players["national_team"] = players["national_team"].astype(str)
    history = bundle.national_appearances[
        bundle.national_appearances["match_date"].lt(cutoff)
    ].copy()
    if history.empty:
        evidence = pd.DataFrame(
            columns=["player_id", "evidence_matches", "evidence_starts", "evidence_minutes"]
        )
    else:
        evidence = history.groupby("player_id").agg(
            evidence_matches=("match_date", "count"),
            evidence_starts=("started", "sum"),
            evidence_minutes=("minutes", "sum"),
        )
        evidence = evidence.reset_index()
    club_start = cutoff - pd.Timedelta(days=cfg.club_window_days)
    club_history = bundle.club_appearances[
        bundle.club_appearances["match_date"].lt(cutoff)
        & bundle.club_appearances["match_date"].ge(club_start)
    ].copy()
    if club_history.empty:
        club = pd.DataFrame(
            columns=[
                "player_id",
                "club_matches",
                "club_starts",
                "club_minutes",
                "club_goal_contributions",
                "club_xg_xa",
            ]
        )
    else:
        club_history["goal_contributions"] = (
            club_history["goals"] + club_history["assists"]
        )
        club_history["xg_xa"] = club_history["xg"] + club_history["xa"]
        club = club_history.groupby("player_id").agg(
            club_matches=("match_date", "count"),
            club_starts=("started", "sum"),
            club_minutes=("minutes", "sum"),
            club_goal_contributions=("goal_contributions", "sum"),
            club_xg_xa=("xg_xa", "sum"),
        )
        club = club.reset_index()

    out = players.merge(evidence, on="player_id", how="left")
    out = out.merge(club, on="player_id", how="left")
    for column in ("evidence_matches", "evidence_starts", "evidence_minutes"):
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0.0)
    for column in (
        "club_matches",
        "club_starts",
        "club_minutes",
        "club_goal_contributions",
        "club_xg_xa",
    ):
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0.0)
    out["age_score"] = out.apply(_age_score, axis=1, as_of_date=cutoff)
    out["experience_score"] = np.log1p(out["evidence_minutes"] / 90.0) / np.log1p(
        cfg.max_evidence_matches
    )
    out["experience_score"] = out["experience_score"].clip(0.0, 1.0)
    out["starter_score"] = np.log1p(out["evidence_starts"]) / np.log1p(
        cfg.max_evidence_matches
    )
    out["starter_score"] = out["starter_score"].clip(0.0, 1.0)
    out["club_minutes_score"] = (out["club_minutes"] / 900.0).clip(0.0, 1.0)
    out["club_attack_score"] = (
        (out["club_goal_contributions"] + out["club_xg_xa"]) / 8.0
    ).clip(0.0, 1.0)
    weight_sum = (
        cfg.age_weight
        + cfg.experience_weight
        + cfg.starter_weight
        + cfg.club_minutes_weight
        + cfg.club_attack_weight
    )
    out["player_strength_score"] = (
        cfg.age_weight * out["age_score"]
        + cfg.experience_weight * out["experience_score"]
        + cfg.starter_weight * out["starter_score"]
        + cfg.club_minutes_weight * out["club_minutes_score"]
        + cfg.club_attack_weight * out["club_attack_score"]
    ) / weight_sum
    national_confidence = (
        out["evidence_matches"] / cfg.max_evidence_matches
    ).clip(0.0, 1.0)
    club_confidence = (out["club_minutes"] / 900.0).clip(0.0, 1.0)
    out["player_strength_confidence"] = np.maximum(
        national_confidence,
        club_confidence,
    )
    out["relative_player_strength"] = out.groupby("national_team", group_keys=False)[
        "player_strength_score"
    ].apply(_safe_zscore)
    return out[
        [
            "player_id",
            "canonical_name",
            "national_team",
            "primary_position",
            "player_strength_score",
            "relative_player_strength",
            "player_strength_confidence",
            "age_score",
            "experience_score",
            "starter_score",
            "club_minutes_score",
            "club_attack_score",
            "evidence_matches",
            "evidence_starts",
            "evidence_minutes",
            "club_matches",
            "club_starts",
            "club_minutes",
            "club_goal_contributions",
            "club_xg_xa",
        ]
    ].sort_values(["national_team", "relative_player_strength"], ascending=[True, False])


def apply_club_season_stats(
    strengths: pd.DataFrame,
    club_stats: pd.DataFrame,
    *,
    weight: float = 0.20,
) -> pd.DataFrame:
    if club_stats.empty:
        return strengths
    stats = club_stats.copy()
    for column in ("appearances", "starts_proxy", "goals", "assists", "shots_on_target"):
        stats[column] = pd.to_numeric(stats.get(column, 0.0), errors="coerce").fillna(0.0)
    stats = stats.groupby("player_id").agg(
        club_season_appearances=("appearances", "max"),
        club_season_starts=("starts_proxy", "max"),
        club_season_goals=("goals", "max"),
        club_season_assists=("assists", "max"),
        club_season_sot=("shots_on_target", "max"),
    ).reset_index()
    out = strengths.merge(stats, on="player_id", how="left")
    for column in (
        "club_season_appearances",
        "club_season_starts",
        "club_season_goals",
        "club_season_assists",
        "club_season_sot",
    ):
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0.0)
    out["club_season_activity_score"] = (
        out["club_season_appearances"] / 20.0
    ).clip(0.0, 1.0)
    out["club_season_attack_score"] = (
        (
            out["club_season_goals"]
            + out["club_season_assists"]
            + 0.2 * out["club_season_sot"]
        )
        / 15.0
    ).clip(0.0, 1.0)
    season_score = 0.65 * out["club_season_activity_score"] + 0.35 * out[
        "club_season_attack_score"
    ]
    blend = float(np.clip(weight, 0.0, 0.5))
    out["player_strength_score"] = (
        (1.0 - blend) * out["player_strength_score"] + blend * season_score
    )
    out["player_strength_confidence"] = np.maximum(
        out["player_strength_confidence"],
        out["club_season_activity_score"] * blend,
    )
    out["relative_player_strength"] = out.groupby("national_team", group_keys=False)[
        "player_strength_score"
    ].apply(_safe_zscore)
    return out.sort_values(
        ["national_team", "relative_player_strength"],
        ascending=[True, False],
    )
