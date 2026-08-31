from __future__ import annotations

import hashlib
import json
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from data.api_football_prematch import (
    api_football_frames_to_prematch_intelligence,
    build_api_football_match_mapping,
)
from data.competition_registry import load_team_alias_registry, normalize_alias
from data.prematch_intelligence import REQUIRED_COLUMNS
from world_cup.api_football_adapter import (
    api_fixture_rows_to_frame,
    injury_rows_to_absences,
    lineup_rows_to_realtime_lineups,
)


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _archive(payload: dict[str, Any], path: Path) -> str:
    content = _canonical(payload); digest = hashlib.sha256(content).hexdigest()
    target = path.with_name(f"{path.stem}_{digest[:12]}.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() != content:
            raise RuntimeError(f"immutable archive collision: {target}")
    else:
        part = target.with_suffix(".json.part"); part.write_bytes(content); part.replace(target)
    return str(target.resolve())


def _team_key(value: object) -> str:
    registry = load_team_alias_registry()
    return normalize_alias(registry.resolve(value) or str(value or ""))


def _fixture_dates(scan_fixtures: pd.DataFrame, fallback_date: str) -> list[str]:
    """Return the local calendar dates actually covered by the Sporttery window."""
    if "kickoff" not in scan_fixtures.columns:
        return [fallback_date]
    kickoff = pd.to_datetime(scan_fixtures["kickoff"], errors="coerce", utc=True)
    dates = sorted({item.tz_convert("Asia/Shanghai").date().isoformat() for item in kickoff.dropna()})
    return dates or [fallback_date]


def _schedule_load_records(
    *, mapping: pd.DataFrame, calendar: pd.DataFrame, observed_at: pd.Timestamp, window_days: int,
) -> pd.DataFrame:
    if mapping.empty:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)
    history = calendar.drop_duplicates("source_fixture_id", keep="last").copy()
    history["kickoff"] = pd.to_datetime(history["kickoff_time"], errors="coerce", utc=True, format="mixed")
    history["home_key"] = history["home_team"].map(_team_key)
    history["away_key"] = history["away_team"].map(_team_key)
    rows: list[dict[str, Any]] = []
    for _, match in mapping.iterrows():
        kickoff = pd.to_datetime(match["kickoff_at"], errors="coerce", utc=True)
        if pd.isna(kickoff) or observed_at > kickoff:
            continue
        lower = kickoff - pd.Timedelta(days=int(window_days))
        prior = history[history["kickoff"].ge(lower) & history["kickoff"].lt(kickoff)]
        for side in ("home", "away"):
            team = str(match[f"{side}_team"]); key = _team_key(team)
            count = int((prior["home_key"].eq(key) | prior["away_key"].eq(key)).sum())
            material = f"{match['source_fixture_id']}|schedule7d|{team}|{observed_at.isoformat()}"
            rows.append({
                "record_id": f"api-football-{hashlib.sha256(material.encode()).hexdigest()[:20]}",
                "match_id": str(match["match_id"]), "competition_id": str(match["competition_id"]),
                "kickoff_at": kickoff.isoformat(), "observed_at": observed_at.isoformat(),
                "source": "api_football", "source_url": "https://v3.football.api-sports.io/fixtures?date=YYYY-MM-DD",
                "license_status": "account_limited", "team": team,
                "signal_type": "cross_comp_matches_7d", "subject": team, "status": "observed",
                "numeric_value": float(count), "confidence": 0.9, "confirmed": True,
                "expires_at": kickoff.isoformat(),
                "notes": f"Complete API-Football date-calendar count over prior {window_days} days; all competitions returned by account coverage.",
            })
    return pd.DataFrame(rows, columns=REQUIRED_COLUMNS)


def collect_api_football_daily_intelligence(
    *, client: Any, scan_fixtures: pd.DataFrame, date: str, observed_at: object,
    raw_root: str | Path, include_lineups: bool = False, include_schedule_load: bool = False,
    schedule_days: int = 7, request_interval_seconds: float = 0.0,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    observed = pd.Timestamp(observed_at)
    if observed.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    observed = observed.tz_convert("UTC")
    raw = Path(raw_root); stamp = observed.strftime("%Y%m%dT%H%M%SZ")
    raw_files: list[str] = []; failures: list[dict[str, str]] = []; calls = 0

    def get(endpoint: str, params: dict[str, Any], label: str) -> dict[str, Any]:
        nonlocal calls
        if calls and request_interval_seconds > 0:
            time.sleep(float(request_interval_seconds))
        payload = client.get(endpoint, params); calls += 1
        if payload.get("errors"):
            raise RuntimeError(f"API-Football {label} payload contains errors")
        raw_files.append(_archive(payload, raw / date / f"{stamp}_{label}.json"))
        return payload

    fixture_dates = _fixture_dates(scan_fixtures, date)
    fixture_frames: list[pd.DataFrame] = []
    for fixture_date in fixture_dates:
        fixtures_payload = get(
            "fixtures", {"date": fixture_date, "timezone": "Asia/Shanghai"}, f"fixtures_{fixture_date}"
        )
        fixture_frames.append(api_fixture_rows_to_frame(fixtures_payload.get("response") or []))
    fixtures = pd.concat(fixture_frames, ignore_index=True) if fixture_frames else api_fixture_rows_to_frame([])
    mapping, mapping_audit = build_api_football_match_mapping(scan_fixtures, fixtures)
    future = mapping[pd.to_datetime(mapping["kickoff_at"], errors="coerce", utc=True).gt(observed)].copy()
    fixture_ids = set(future["source_fixture_id"].astype(str))

    absence_rows: list[dict[str, Any]] = []
    try:
        for fixture_date in fixture_dates:
            injuries_payload = get(
                "injuries", {"date": fixture_date, "timezone": "Asia/Shanghai"}, f"injuries_{fixture_date}"
            )
            absence_rows.extend(
                row for row in injuries_payload.get("response") or []
                if str((row.get("fixture") or {}).get("id", "")) in fixture_ids
            )
    except Exception as exc:
        failures.append({"feed": "injuries", "error": str(exc)})

    lineup_frames: list[pd.DataFrame] = []
    if include_lineups:
        for fixture_id in sorted(fixture_ids):
            try:
                payload = get("fixtures/lineups", {"fixture": fixture_id}, f"lineups_{fixture_id}")
                lineup_frames.append(lineup_rows_to_realtime_lineups(payload.get("response") or [], fixture_id=fixture_id))
            except Exception as exc:
                failures.append({"feed": "lineups", "fixture_id": fixture_id, "error": str(exc)})

    calendar_frames: list[pd.DataFrame] = []
    schedule_dates: list[str] = []
    if include_schedule_load:
        end = pd.Timestamp(max(fixture_dates))
        for offset in range(int(schedule_days), 0, -1):
            day = (end - timedelta(days=offset)).date().isoformat(); schedule_dates.append(day)
            try:
                payload = get("fixtures", {"date": day, "timezone": "Asia/Shanghai"}, f"calendar_{day}")
                calendar_frames.append(api_fixture_rows_to_frame(payload.get("response") or []))
            except Exception as exc:
                failures.append({"feed": "schedule_calendar", "date": day, "error": str(exc)})

    absences = injury_rows_to_absences(absence_rows)
    lineups = pd.concat(lineup_frames, ignore_index=True) if lineup_frames else lineup_rows_to_realtime_lineups([], fixture_id="")
    converted, conversion_audit = api_football_frames_to_prematch_intelligence(
        fixtures=fixtures, absences=absences, lineups=lineups, mapping=future, observed_at=observed,
    )
    schedule_complete = include_schedule_load and len(calendar_frames) == int(schedule_days)
    if schedule_complete:
        calendar = pd.concat(calendar_frames, ignore_index=True) if calendar_frames else pd.DataFrame()
        loads = _schedule_load_records(mapping=future, calendar=calendar, observed_at=observed, window_days=schedule_days)
        converted = pd.concat([converted, loads], ignore_index=True, sort=False)[REQUIRED_COLUMNS]
    else:
        loads = pd.DataFrame(columns=REQUIRED_COLUMNS)
    quota_headers = getattr(client, "last_headers", {})
    return converted, mapping, {
        "schema_version": 1, "source": "api_football", "status": "ok" if not failures else "partial",
        "observed_at": observed.isoformat(), "api_calls": calls, "fixture_dates": fixture_dates,
        "mapping": mapping_audit,
        "future_mapped_fixtures": int(len(future)), "absence_rows": int(len(absences)),
        "starter_rows": int((lineups.get("role", pd.Series(dtype=str)) == "starter").sum()),
        "schedule_dates": schedule_dates, "schedule_calendar_complete": schedule_complete,
        "schedule_load_rows": int(len(loads)), "converted_rows": int(len(converted)),
        "conversion": conversion_audit, "failures": failures, "raw_files": raw_files,
        "quota": {"daily_remaining": str(quota_headers.get("x-ratelimit-requests-remaining", "")),
                  "minute_remaining": str(quota_headers.get("x-ratelimit-remaining", ""))},
    }
