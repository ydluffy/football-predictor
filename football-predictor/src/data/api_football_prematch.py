from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pandas as pd

from data.competition_registry import load_team_alias_registry, normalize_alias
from data.prematch_intelligence import REQUIRED_COLUMNS, normalize_prematch_intelligence


SOURCE = "api_football"
LICENSE_STATUS = "account_limited"
MAPPING_COLUMNS = [
    "source_fixture_id",
    "match_id",
    "competition_id",
    "kickoff_at",
    "home_team",
    "away_team",
]


def _record_id(*parts: object) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:20]
    return f"api-football-{digest}"


def _team_key(value: object) -> str:
    registry = load_team_alias_registry()
    canonical = registry.resolve(value) or str(value or "").strip()
    return normalize_alias(canonical)


def build_api_football_match_mapping(
    local_fixtures: pd.DataFrame,
    api_fixtures: pd.DataFrame,
    *,
    tolerance_minutes: int = 15,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    local_required = {"match_id", "competition_id", "kickoff", "home_team", "away_team"}
    api_required = {"source_fixture_id", "kickoff_time", "home_team", "away_team"}
    local_missing = local_required - set(local_fixtures.columns)
    api_missing = api_required - set(api_fixtures.columns)
    if local_missing:
        raise ValueError(f"local fixtures missing API mapping columns: {sorted(local_missing)}")
    if api_missing:
        raise ValueError(f"API fixtures missing mapping columns: {sorted(api_missing)}")
    api = api_fixtures.copy()
    api["kickoff_parsed"] = pd.to_datetime(api["kickoff_time"], errors="coerce", utc=True)
    api["home_key"] = api["home_team"].map(_team_key)
    api["away_key"] = api["away_team"].map(_team_key)
    rows: list[dict[str, Any]] = []
    unmatched: list[str] = []
    ambiguous: list[str] = []
    tolerance = pd.Timedelta(minutes=int(tolerance_minutes))
    for _, local in local_fixtures.iterrows():
        kickoff = pd.to_datetime(local["kickoff"], errors="coerce", utc=True)
        home_key = _team_key(local.get("home_team_canonical", local["home_team"]))
        away_key = _team_key(local.get("away_team_canonical", local["away_team"]))
        candidates = api[
            api["kickoff_parsed"].notna()
            & api["kickoff_parsed"].sub(kickoff).abs().le(tolerance)
            & api["home_key"].eq(home_key)
            & api["away_key"].eq(away_key)
        ]
        match_id = str(local["match_id"])
        if len(candidates) == 0:
            unmatched.append(match_id)
            continue
        if len(candidates) > 1:
            ambiguous.append(match_id)
            continue
        candidate = candidates.iloc[0]
        rows.append(
            {
                "source_fixture_id": str(candidate["source_fixture_id"]),
                "match_id": match_id,
                "competition_id": str(local["competition_id"]),
                "kickoff_at": kickoff.isoformat(),
                "home_team": str(local.get("home_team_canonical", local["home_team"])),
                "away_team": str(local.get("away_team_canonical", local["away_team"])),
            }
        )
    return pd.DataFrame(rows, columns=MAPPING_COLUMNS), {
        "local_fixture_rows": int(len(local_fixtures)),
        "api_fixture_rows": int(len(api_fixtures)),
        "mapped_rows": int(len(rows)),
        "unmatched_match_ids": unmatched,
        "ambiguous_match_ids": ambiguous,
        "tolerance_minutes": int(tolerance_minutes),
    }


def _canonical_team(
    source_team: object,
    *,
    source_fixture: pd.Series | None,
    mapping: pd.Series,
) -> str:
    value = str(source_team or "").strip()
    if source_fixture is not None:
        if normalize_alias(value) == normalize_alias(source_fixture.get("home_team", "")):
            return str(mapping["home_team"])
        if normalize_alias(value) == normalize_alias(source_fixture.get("away_team", "")):
            return str(mapping["away_team"])
    return value


def api_football_frames_to_prematch_intelligence(
    *,
    fixtures: pd.DataFrame,
    absences: pd.DataFrame,
    lineups: pd.DataFrame,
    mapping: pd.DataFrame,
    observed_at: str | pd.Timestamp,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    required_mapping = {
        "source_fixture_id",
        "match_id",
        "competition_id",
        "kickoff_at",
        "home_team",
        "away_team",
    }
    missing = required_mapping - set(mapping.columns)
    if missing:
        raise ValueError(f"API-Football mapping missing columns: {sorted(missing)}")
    observed = pd.Timestamp(observed_at)
    if observed.tzinfo is None:
        raise ValueError("API-Football observed_at must be timezone-aware")
    fixture_lookup = {
        str(row["source_fixture_id"]): row for _, row in fixtures.iterrows()
    } if not fixtures.empty else {}
    mapping_lookup = {str(row["source_fixture_id"]): row for _, row in mapping.iterrows()}
    records: list[dict[str, Any]] = []
    unmapped_fixture_ids: set[str] = set()

    for _, absence in absences.iterrows():
        source_fixture_id = str(absence.get("source_fixture_id", ""))
        mapped = mapping_lookup.get(source_fixture_id)
        if mapped is None:
            unmapped_fixture_ids.add(source_fixture_id)
            continue
        source_fixture = fixture_lookup.get(source_fixture_id)
        team = _canonical_team(absence.get("team", ""), source_fixture=source_fixture, mapping=mapped)
        subject = str(absence.get("player", "")).strip()
        status = str(absence.get("status", "injured")).strip().lower()
        records.append(
            {
                "record_id": _record_id(source_fixture_id, "absence", team, subject, observed.isoformat()),
                "match_id": str(mapped["match_id"]),
                "competition_id": str(mapped["competition_id"]),
                "kickoff_at": str(mapped["kickoff_at"]),
                "observed_at": observed.isoformat(),
                "source": SOURCE,
                "source_url": f"https://v3.football.api-sports.io/injuries?fixture={source_fixture_id}",
                "license_status": LICENSE_STATUS,
                "team": team,
                "signal_type": "absence",
                "subject": subject,
                "status": status,
                "numeric_value": float(absence.get("impact", 1.0) or 1.0),
                "confidence": 0.8,
                "confirmed": True,
                "expires_at": str(mapped["kickoff_at"]),
                "notes": str(absence.get("reason", "")),
            }
        )

    for _, lineup in lineups.iterrows():
        if str(lineup.get("role", "")).lower() != "starter":
            continue
        source_fixture_id = str(lineup.get("match_id", ""))
        mapped = mapping_lookup.get(source_fixture_id)
        if mapped is None:
            unmapped_fixture_ids.add(source_fixture_id)
            continue
        source_fixture = fixture_lookup.get(source_fixture_id)
        team = _canonical_team(lineup.get("team", ""), source_fixture=source_fixture, mapping=mapped)
        subject = str(lineup.get("player", "")).strip()
        records.append(
            {
                "record_id": _record_id(source_fixture_id, "starter", team, subject, observed.isoformat()),
                "match_id": str(mapped["match_id"]),
                "competition_id": str(mapped["competition_id"]),
                "kickoff_at": str(mapped["kickoff_at"]),
                "observed_at": observed.isoformat(),
                "source": SOURCE,
                "source_url": f"https://v3.football.api-sports.io/fixtures/lineups?fixture={source_fixture_id}",
                "license_status": LICENSE_STATUS,
                "team": team,
                "signal_type": "confirmed_starter",
                "subject": subject,
                "status": "starter",
                "numeric_value": 1.0,
                "confidence": 0.95,
                "confirmed": bool(lineup.get("confirmed", True)),
                "expires_at": str(mapped["kickoff_at"]),
                "notes": "API-Football confirmed starting XI",
            }
        )

    frame = pd.DataFrame(records, columns=REQUIRED_COLUMNS)
    return frame, {
        "mapping_rows": int(len(mapping)),
        "converted_rows": int(len(frame)),
        "absence_rows": int((frame["signal_type"] == "absence").sum()) if not frame.empty else 0,
        "starter_rows": int((frame["signal_type"] == "confirmed_starter").sum()) if not frame.empty else 0,
        "unmapped_fixture_ids": sorted(value for value in unmapped_fixture_ids if value),
    }


def append_validated_prematch_intelligence(
    new_rows: pd.DataFrame,
    *,
    manual_path: str | Path,
    validated_path: str | Path,
) -> dict[str, Any]:
    manual = Path(manual_path)
    if manual.exists() and manual.stat().st_size:
        existing = pd.read_csv(manual, low_memory=False)
    else:
        existing = pd.DataFrame(columns=REQUIRED_COLUMNS)
    combined = pd.concat([existing, new_rows], ignore_index=True, sort=False)
    combined = combined[REQUIRED_COLUMNS].drop_duplicates("record_id", keep="last")
    manual.parent.mkdir(parents=True, exist_ok=True)
    manual_part = manual.with_suffix(manual.suffix + ".part")
    combined.to_csv(manual_part, index=False)
    manual_part.replace(manual)

    validated, validation_audit = normalize_prematch_intelligence(combined)
    validated_file = Path(validated_path)
    validated_file.parent.mkdir(parents=True, exist_ok=True)
    validated_part = validated_file.with_suffix(validated_file.suffix + ".part")
    validated.to_csv(validated_part, index=False)
    validated_part.replace(validated_file)
    return {
        **validation_audit,
        "manual_rows": int(len(combined)),
        "validated_rows": int(len(validated)),
        "manual_path": str(manual.resolve()),
        "validated_path": str(validated_file.resolve()),
    }
