from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from world_cup.data import normalize_national_team


PROFILE_COLUMNS = [
    "source",
    "source_player_id",
    "source_url",
    "player_id",
    "canonical_name",
    "national_team",
    "primary_position",
    "club",
    "market_value_eur",
    "height_cm",
    "preferred_foot",
    "availability_status",
    "availability_reason",
    "profile_updated_at",
    "confidence",
]

AVAILABILITY_MAP = {
    "": "unknown",
    "unknown": "unknown",
    "available": "available",
    "fit": "available",
    "injured": "injured",
    "injury": "injured",
    "suspended": "suspended",
    "suspension": "suspended",
    "doubtful": "doubtful",
    "questionable": "doubtful",
    "unavailable": "unavailable",
}


def empty_external_player_profiles() -> pd.DataFrame:
    return pd.DataFrame(columns=PROFILE_COLUMNS)


def load_external_player_profiles(path: str | Path | None) -> pd.DataFrame:
    if not path:
        return empty_external_player_profiles()
    file_path = Path(path)
    if not file_path.exists():
        return empty_external_player_profiles()
    return normalize_external_player_profiles(pd.read_csv(file_path))


def normalize_external_player_profiles(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for column in PROFILE_COLUMNS:
        if column not in out.columns:
            out[column] = ""
    for column in (
        "source",
        "source_player_id",
        "source_url",
        "player_id",
        "canonical_name",
        "primary_position",
        "club",
        "preferred_foot",
        "availability_reason",
        "profile_updated_at",
    ):
        out[column] = out[column].astype("string").fillna("").str.strip()
    out["national_team"] = out["national_team"].map(normalize_national_team)
    out["market_value_eur"] = pd.to_numeric(out["market_value_eur"], errors="coerce").fillna(0.0)
    out["height_cm"] = pd.to_numeric(out["height_cm"], errors="coerce").fillna(0.0)
    out["confidence"] = pd.to_numeric(out["confidence"], errors="coerce").fillna(0.5).clip(0.0, 1.0)
    status = out["availability_status"].astype("string").fillna("").str.strip().str.casefold()
    out["availability_status"] = status.map(AVAILABILITY_MAP).fillna("unknown")
    out = out[PROFILE_COLUMNS]
    out = out[
        out["player_id"].ne("")
        | out["canonical_name"].ne("")
        | out["source_player_id"].ne("")
    ].copy()
    return out


def profile_source_summary(profiles: pd.DataFrame) -> dict[str, object]:
    if profiles.empty:
        return {
            "rows": 0,
            "players_with_market_value": 0,
            "players_with_availability_signal": 0,
            "sources": [],
        }
    return {
        "rows": int(len(profiles)),
        "players_with_market_value": int(profiles["market_value_eur"].gt(0).sum()),
        "players_with_availability_signal": int(
            (~profiles["availability_status"].isin(["", "unknown", "available"])).sum()
        ),
        "sources": sorted(profiles["source"].dropna().astype(str).unique().tolist()),
    }


def _safe_market_value_score(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").fillna(0.0)
    transformed = np.log1p(numeric.clip(lower=0.0))
    if float(transformed.max()) <= 0.0:
        return pd.Series(0.0, index=values.index)
    return transformed / float(transformed.max())


def apply_external_player_profiles(
    strengths: pd.DataFrame,
    profiles: pd.DataFrame,
    *,
    weight: float = 0.12,
) -> pd.DataFrame:
    if strengths.empty or profiles.empty:
        return strengths
    usable = profiles[profiles["player_id"].astype(str).str.strip().ne("")].copy()
    if usable.empty:
        return strengths
    usable = usable.sort_values(["confidence", "market_value_eur"], ascending=[False, False])
    usable = usable.drop_duplicates("player_id", keep="first")
    enrich = usable[
        [
            "player_id",
            "source",
            "source_url",
            "market_value_eur",
            "height_cm",
            "preferred_foot",
            "availability_status",
            "availability_reason",
            "confidence",
        ]
    ].rename(
        columns={
            "source": "external_profile_source",
            "source_url": "external_profile_url",
            "confidence": "external_profile_confidence",
        }
    )
    out = strengths.merge(enrich, on="player_id", how="left")
    out["market_value_eur"] = pd.to_numeric(out["market_value_eur"], errors="coerce").fillna(0.0)
    out["external_market_value_score"] = _safe_market_value_score(out["market_value_eur"])
    out["external_profile_confidence"] = pd.to_numeric(
        out["external_profile_confidence"],
        errors="coerce",
    ).fillna(0.0)
    blend = float(np.clip(weight, 0.0, 0.35))
    effective_blend = blend * out["external_profile_confidence"].clip(0.0, 1.0)
    out["player_strength_score"] = (
        (1.0 - effective_blend) * out["player_strength_score"]
        + effective_blend * out["external_market_value_score"]
    )
    out["player_strength_confidence"] = np.maximum(
        out["player_strength_confidence"],
        out["external_profile_confidence"] * blend,
    )
    out["relative_player_strength"] = out.groupby("national_team", group_keys=False)[
        "player_strength_score"
    ].transform(lambda series: (series - series.mean()) / series.std(ddof=0) if series.std(ddof=0) > 1e-9 else 0.0)
    return out.sort_values(
        ["national_team", "relative_player_strength"],
        ascending=[True, False],
    )
