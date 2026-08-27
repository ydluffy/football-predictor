from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from data.competition_registry import (
    DEFAULT_COMPETITION_REGISTRY_PATH,
    DEFAULT_TEAM_ALIASES_PATH,
    load_competition_registry,
    load_team_alias_registry,
)


DEFAULT_SOURCE_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "prematch_data_sources.json"
REQUIRED_COLUMNS = [
    "record_id",
    "match_id",
    "competition_id",
    "kickoff_at",
    "observed_at",
    "source",
    "source_url",
    "license_status",
    "team",
    "signal_type",
    "subject",
    "status",
    "numeric_value",
    "confidence",
    "confirmed",
    "expires_at",
    "notes",
]
USABLE_LICENSE_STATUSES = {
    "allowed",
    "manual_verified",
    "account_limited",
    "research_allowed_with_attribution",
}
SUPPORTED_SIGNAL_TYPES = {
    "absence",
    "confirmed_starter",
    "team_strength",
    "prematch_xg",
    "travel_km",
    "timezone_shift_hours",
    "cross_comp_matches_7d",
    "odds_snapshot",
    "historical_team_strength",
}
ABSENCE_STATUSES = {"injured", "suspended", "doubtful", "illness", "unavailable", "rested"}

PREMATCH_FEATURE_COLUMNS = [
    "home_absence_impact",
    "away_absence_impact",
    "absence_impact_diff",
    "home_absence_count",
    "away_absence_count",
    "absence_data_available",
    "home_confirmed_starters",
    "away_confirmed_starters",
    "home_lineup_confirmed",
    "away_lineup_confirmed",
    "both_lineups_confirmed",
    "home_team_strength",
    "away_team_strength",
    "team_strength_diff",
    "team_strength_available",
    "home_prematch_xg",
    "away_prematch_xg",
    "prematch_xg_diff",
    "prematch_xg_sum",
    "prematch_xg_available",
    "home_travel_km",
    "away_travel_km",
    "travel_km_diff",
    "travel_data_available",
    "home_timezone_shift_hours",
    "away_timezone_shift_hours",
    "timezone_shift_diff",
    "timezone_data_available",
    "home_cross_comp_matches_7d",
    "away_cross_comp_matches_7d",
    "cross_comp_matches_7d_diff",
    "cross_comp_schedule_available",
    "intelligence_source_count",
    "latest_intelligence_age_hours",
    "prematch_intelligence_available",
]


def load_prematch_source_config(path: str | Path = DEFAULT_SOURCE_CONFIG_PATH) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if int(payload.get("schema_version", 0)) != 1:
        raise ValueError("unsupported prematch data source schema_version")
    return payload


def normalize_prematch_intelligence(
    frame: pd.DataFrame,
    *,
    source_config_path: str | Path = DEFAULT_SOURCE_CONFIG_PATH,
    competition_registry_path: str | Path = DEFAULT_COMPETITION_REGISTRY_PATH,
    team_aliases_path: str | Path = DEFAULT_TEAM_ALIASES_PATH,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    out = frame.copy()
    missing = [column for column in REQUIRED_COLUMNS if column not in out.columns]
    if missing:
        raise ValueError(f"prematch intelligence missing columns: {missing}")
    out = out[REQUIRED_COLUMNS].copy()
    for column in (
        "record_id",
        "match_id",
        "competition_id",
        "source",
        "source_url",
        "license_status",
        "team",
        "signal_type",
        "subject",
        "status",
        "notes",
    ):
        out[column] = out[column].astype("string").fillna("").str.strip()
    out["status"] = out["status"].str.lower()
    out["signal_type"] = out["signal_type"].str.lower()
    out["license_status"] = out["license_status"].str.lower()
    for column in ("kickoff_at", "observed_at", "expires_at"):
        out[column] = pd.to_datetime(out[column], errors="coerce", utc=True)
    out["numeric_value"] = pd.to_numeric(out["numeric_value"], errors="coerce")
    out["confidence"] = pd.to_numeric(out["confidence"], errors="coerce").clip(0.0, 1.0)
    out["confirmed"] = (
        out["confirmed"].astype("string").str.lower().map(
            {"1": True, "true": True, "yes": True, "y": True, "0": False, "false": False, "no": False, "n": False}
        )
    )

    config = load_prematch_source_config(source_config_path)
    competition_registry = load_competition_registry(competition_registry_path)
    team_registry = load_team_alias_registry(team_aliases_path)
    resolved_competitions = out["competition_id"].map(competition_registry.resolve)
    competition_known = resolved_competitions.notna()
    out.loc[competition_known, "competition_id"] = resolved_competitions.loc[competition_known].map(
        lambda item: item.competition_id
    )
    resolved_teams = out["team"].map(team_registry.resolve)
    team_alias_known = resolved_teams.notna()
    out.loc[team_alias_known, "team"] = resolved_teams.loc[team_alias_known]
    configured_sources = config.get("sources", {})
    known_source = out["source"].isin(configured_sources)
    source_signal_allowed = pd.Series(False, index=out.index)
    source_license_matches = pd.Series(False, index=out.index)
    for source, policy in configured_sources.items():
        source_mask = out["source"].eq(source)
        allowed_signals = set(policy.get("allowed_signal_types", []))
        source_signal_allowed |= source_mask & out["signal_type"].isin(allowed_signals)
        source_license_matches |= source_mask & out["license_status"].eq(
            str(policy.get("license_status", "")).lower()
        )
    valid = (
        out["record_id"].ne("")
        & out["match_id"].ne("")
        & out["team"].ne("")
        & out["kickoff_at"].notna()
        & out["observed_at"].notna()
        & out["observed_at"].le(out["kickoff_at"])
        & out["signal_type"].isin(SUPPORTED_SIGNAL_TYPES)
        & out["license_status"].isin(USABLE_LICENSE_STATUSES)
        & out["confidence"].notna()
        & out["confirmed"].notna()
        & competition_known
        & known_source
        & source_signal_allowed
        & source_license_matches
    )
    normalized = out.loc[valid].copy()
    normalized["confirmed"] = normalized["confirmed"].astype(bool)
    normalized = normalized.sort_values(["match_id", "observed_at", "record_id"], kind="mergesort")
    normalized = normalized.drop_duplicates("record_id", keep="last").reset_index(drop=True)
    audit = {
        "input_rows": int(len(out)),
        "usable_rows": int(len(normalized)),
        "rejected_rows": int((~valid).sum()),
        "unknown_source_rows": int((~known_source).sum()),
        "unknown_competition_rows": int((~competition_known).sum()),
        "unknown_team_alias_rows": int((~team_alias_known).sum()),
        "source_signal_not_allowed_rows": int((~source_signal_allowed).sum()),
        "license_mismatch_rows": int((~source_license_matches).sum()),
        "post_kickoff_rows": int((out["observed_at"] > out["kickoff_at"]).fillna(False).sum()),
        "missing_timestamp_rows": int((out["observed_at"].isna() | out["kickoff_at"].isna()).sum()),
    }
    return normalized, audit


def _latest_by_subject(records: pd.DataFrame) -> pd.DataFrame:
    if records.empty:
        return records
    keys = ["match_id", "team", "signal_type", "subject", "source"]
    return records.sort_values("observed_at").drop_duplicates(keys, keep="last")


def _team_signal(records: pd.DataFrame, team: str, signal_type: str) -> pd.DataFrame:
    return records[records["team"].eq(team) & records["signal_type"].eq(signal_type)]


def _weighted_latest_value(records: pd.DataFrame) -> tuple[float, bool]:
    usable = records[records["numeric_value"].notna()]
    if usable.empty:
        return 0.0, False
    latest = usable.sort_values(["confidence", "observed_at"], ascending=[False, False]).iloc[0]
    return float(latest["numeric_value"]), True


def build_prematch_intelligence_features(
    fixtures: pd.DataFrame,
    intelligence: pd.DataFrame,
    *,
    source_config_path: str | Path = DEFAULT_SOURCE_CONFIG_PATH,
    default_cutoff_minutes: int = 60,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    fixture_required = {"match_id", "kickoff_at", "home_team", "away_team"}
    missing = fixture_required - set(fixtures.columns)
    if missing:
        raise ValueError(f"fixtures missing prematch columns: {sorted(missing)}")
    normalized, normalize_audit = normalize_prematch_intelligence(
        intelligence, source_config_path=source_config_path
    )
    fixture_frame = fixtures.copy()
    team_registry = load_team_alias_registry()
    for column in ("home_team", "away_team"):
        fixture_frame[column] = fixture_frame[column].map(
            lambda value: team_registry.resolve(value) or str(value or "").strip()
        )
    fixture_frame["kickoff_at"] = pd.to_datetime(fixture_frame["kickoff_at"], errors="coerce", utc=True)
    if fixture_frame["kickoff_at"].isna().any():
        raise ValueError("fixtures contain invalid kickoff_at")
    if "analysis_at" in fixture_frame.columns:
        fixture_frame["analysis_at"] = pd.to_datetime(fixture_frame["analysis_at"], errors="coerce", utc=True)
    else:
        fixture_frame["analysis_at"] = fixture_frame["kickoff_at"] - pd.to_timedelta(
            int(default_cutoff_minutes), unit="minute"
        )
    if fixture_frame["analysis_at"].isna().any():
        raise ValueError("fixtures contain invalid analysis_at")
    if (fixture_frame["analysis_at"] >= fixture_frame["kickoff_at"]).any():
        raise ValueError("analysis_at must be before kickoff_at")

    rows: list[dict[str, float]] = []
    matched_record_ids: set[str] = set()
    for fixture in fixture_frame.itertuples(index=False):
        match_records = normalized[
            normalized["match_id"].eq(str(fixture.match_id))
            & normalized["observed_at"].le(fixture.analysis_at)
            & (normalized["expires_at"].isna() | normalized["expires_at"].ge(fixture.analysis_at))
        ].copy()
        match_records = _latest_by_subject(match_records)
        matched_record_ids.update(match_records["record_id"].astype(str).tolist())
        home = str(fixture.home_team)
        away = str(fixture.away_team)

        home_abs = _team_signal(match_records, home, "absence")
        away_abs = _team_signal(match_records, away, "absence")
        home_abs = home_abs[home_abs["status"].isin(ABSENCE_STATUSES)]
        away_abs = away_abs[away_abs["status"].isin(ABSENCE_STATUSES)]
        home_absence_impact = float(
            (home_abs["numeric_value"].fillna(1.0) * home_abs["confidence"]).sum()
        )
        away_absence_impact = float(
            (away_abs["numeric_value"].fillna(1.0) * away_abs["confidence"]).sum()
        )

        home_lineup = _team_signal(match_records, home, "confirmed_starter")
        away_lineup = _team_signal(match_records, away, "confirmed_starter")
        home_starters = int(home_lineup["confirmed"].sum())
        away_starters = int(away_lineup["confirmed"].sum())
        home_lineup_confirmed = float(home_starters >= 11)
        away_lineup_confirmed = float(away_starters >= 11)

        home_strength, home_strength_available = _weighted_latest_value(
            _team_signal(match_records, home, "team_strength")
        )
        away_strength, away_strength_available = _weighted_latest_value(
            _team_signal(match_records, away, "team_strength")
        )
        home_xg, home_xg_available = _weighted_latest_value(
            _team_signal(match_records, home, "prematch_xg")
        )
        away_xg, away_xg_available = _weighted_latest_value(
            _team_signal(match_records, away, "prematch_xg")
        )
        home_travel, home_travel_available = _weighted_latest_value(
            _team_signal(match_records, home, "travel_km")
        )
        away_travel, away_travel_available = _weighted_latest_value(
            _team_signal(match_records, away, "travel_km")
        )
        home_timezone, home_timezone_available = _weighted_latest_value(
            _team_signal(match_records, home, "timezone_shift_hours")
        )
        away_timezone, away_timezone_available = _weighted_latest_value(
            _team_signal(match_records, away, "timezone_shift_hours")
        )
        home_load, home_load_available = _weighted_latest_value(
            _team_signal(match_records, home, "cross_comp_matches_7d")
        )
        away_load, away_load_available = _weighted_latest_value(
            _team_signal(match_records, away, "cross_comp_matches_7d")
        )
        latest_age = (
            float((fixture.analysis_at - match_records["observed_at"].max()).total_seconds() / 3600.0)
            if not match_records.empty
            else 0.0
        )
        rows.append(
            {
                "home_absence_impact": home_absence_impact,
                "away_absence_impact": away_absence_impact,
                "absence_impact_diff": home_absence_impact - away_absence_impact,
                "home_absence_count": float(len(home_abs)),
                "away_absence_count": float(len(away_abs)),
                "absence_data_available": float(not home_abs.empty or not away_abs.empty),
                "home_confirmed_starters": float(home_starters),
                "away_confirmed_starters": float(away_starters),
                "home_lineup_confirmed": home_lineup_confirmed,
                "away_lineup_confirmed": away_lineup_confirmed,
                "both_lineups_confirmed": min(home_lineup_confirmed, away_lineup_confirmed),
                "home_team_strength": home_strength,
                "away_team_strength": away_strength,
                "team_strength_diff": home_strength - away_strength,
                "team_strength_available": float(home_strength_available and away_strength_available),
                "home_prematch_xg": home_xg,
                "away_prematch_xg": away_xg,
                "prematch_xg_diff": home_xg - away_xg,
                "prematch_xg_sum": home_xg + away_xg,
                "prematch_xg_available": float(home_xg_available and away_xg_available),
                "home_travel_km": home_travel,
                "away_travel_km": away_travel,
                "travel_km_diff": home_travel - away_travel,
                "travel_data_available": float(home_travel_available and away_travel_available),
                "home_timezone_shift_hours": home_timezone,
                "away_timezone_shift_hours": away_timezone,
                "timezone_shift_diff": home_timezone - away_timezone,
                "timezone_data_available": float(home_timezone_available and away_timezone_available),
                "home_cross_comp_matches_7d": home_load,
                "away_cross_comp_matches_7d": away_load,
                "cross_comp_matches_7d_diff": home_load - away_load,
                "cross_comp_schedule_available": float(home_load_available and away_load_available),
                "intelligence_source_count": float(match_records["source"].nunique()),
                "latest_intelligence_age_hours": latest_age,
                "prematch_intelligence_available": float(not match_records.empty),
            }
        )
    features = pd.DataFrame(rows, columns=PREMATCH_FEATURE_COLUMNS, index=fixtures.index)
    audit = {
        **normalize_audit,
        "fixture_rows": int(len(fixtures)),
        "fixtures_with_intelligence": int(features["prematch_intelligence_available"].sum()),
        "fixtures_with_both_lineups": int(features["both_lineups_confirmed"].sum()),
        "matched_record_rows": int(len(matched_record_ids)),
        "unmatched_or_after_cutoff_rows": int(len(normalized) - len(matched_record_ids)),
    }
    return features.replace([np.inf, -np.inf], np.nan).fillna(0.0), audit
