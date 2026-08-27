from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd

from data.api_football_prematch import build_api_football_match_mapping
from data.competition_registry import load_team_alias_registry, normalize_alias
from data.prematch_intelligence import REQUIRED_COLUMNS


def _team_key(value: object) -> str:
    registry = load_team_alias_registry()
    return normalize_alias(registry.resolve(value) or str(value or ""))


def build_schedule_load_intelligence(
    *, scan_fixtures: pd.DataFrame, external_matches: pd.DataFrame, observed_at: object,
    source: str, source_url: str, license_status: str = "account_limited", window_days: int = 7,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    observed = pd.Timestamp(observed_at)
    if observed.tzinfo is None: raise ValueError("observed_at must be timezone-aware")
    observed = observed.tz_convert("UTC")
    external = external_matches.copy()
    mapping, mapping_audit = build_api_football_match_mapping(scan_fixtures, external)
    mapping = mapping[pd.to_datetime(mapping["kickoff_at"], errors="coerce", utc=True).gt(observed)].copy()
    calendar = external.drop_duplicates("source_fixture_id", keep="last").copy()
    calendar["kickoff"] = pd.to_datetime(calendar["kickoff_time"], errors="coerce", utc=True, format="mixed")
    calendar["home_key"] = calendar["home_team"].map(_team_key); calendar["away_key"] = calendar["away_team"].map(_team_key)
    if "status" in calendar:
        calendar = calendar[calendar["status"].astype(str).str.upper().eq("FINISHED")].copy()
    rows: list[dict[str, Any]] = []
    for _, match in mapping.iterrows():
        kickoff = pd.Timestamp(match["kickoff_at"]); lower = kickoff - pd.Timedelta(days=int(window_days))
        prior = calendar[calendar["kickoff"].ge(lower) & calendar["kickoff"].lt(kickoff)]
        for side in ("home", "away"):
            team = str(match[f"{side}_team"]); key = _team_key(team)
            count = int((prior["home_key"].eq(key) | prior["away_key"].eq(key)).sum())
            material = f"{source}|{match['source_fixture_id']}|load|{team}|{observed.isoformat()}"
            rows.append({
                "record_id": f"{source}-{hashlib.sha256(material.encode()).hexdigest()[:20]}",
                "match_id": str(match["match_id"]), "competition_id": str(match["competition_id"]),
                "kickoff_at": kickoff.isoformat(), "observed_at": observed.isoformat(), "source": source,
                "source_url": source_url, "license_status": license_status, "team": team,
                "signal_type": "cross_comp_matches_7d", "subject": team, "status": "observed",
                "numeric_value": float(count), "confidence": 0.8, "confirmed": True,
                "expires_at": kickoff.isoformat(),
                "notes": f"Prior {window_days}-day completed-match count within all competitions accessible to {source}; coverage-limited.",
            })
    frame = pd.DataFrame(rows, columns=REQUIRED_COLUMNS)
    return frame, mapping, {**mapping_audit, "future_mapped_fixtures": int(len(mapping)),
                             "schedule_load_rows": int(len(frame)), "calendar_rows": int(len(calendar)),
                             "coverage_scope": f"all competitions accessible to {source}"}
