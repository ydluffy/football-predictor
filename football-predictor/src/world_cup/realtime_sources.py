from __future__ import annotations

from pathlib import Path

import pandas as pd

from world_cup.data import normalize_national_team


INTELLIGENCE_CATEGORIES = {
    "injury",
    "suspension",
    "lineup",
    "tactical",
    "motivation",
    "schedule",
    "form",
    "weather",
    "other",
}

ABSENCE_STATUS_WEIGHTS = {
    "injured": 1.0,
    "suspended": 1.0,
    "unavailable": 0.9,
    "doubtful": 0.5,
    "illness": 0.7,
    "rested": 0.4,
}


def _read_optional_csv(path: str | Path | None) -> pd.DataFrame:
    if not path:
        return pd.DataFrame()
    file = Path(path)
    if not file.exists():
        return pd.DataFrame()
    return pd.read_csv(file).fillna("")


def _fixture_key(date: object, home_team: object, away_team: object) -> tuple[str, str, str]:
    return (
        str(pd.Timestamp(date).date()),
        normalize_national_team(home_team),
        normalize_national_team(away_team),
    )


def _find_by_fixture(
    records: dict[tuple[str, str, str], dict[str, object]],
    *,
    date: object,
    home_team: object,
    away_team: object,
    date_tolerance_days: int = 1,
) -> dict[str, object]:
    target = pd.Timestamp(date).normalize()
    home = normalize_national_team(home_team)
    away = normalize_national_team(away_team)
    exact = records.get((str(target.date()), home, away))
    if exact is not None:
        return exact
    candidates: list[tuple[int, dict[str, object]]] = []
    for record_date, record_home, record_away in records:
        if record_home != home or record_away != away:
            continue
        gap = abs((pd.Timestamp(record_date).normalize() - target).days)
        if gap <= date_tolerance_days:
            candidates.append((gap, records[(record_date, record_home, record_away)]))
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1] if candidates else {}


def load_line_movement_index(path: str | Path | None) -> dict[tuple[str, str, str], dict[str, object]]:
    frame = _read_optional_csv(path)
    required = {"date", "home_team", "away_team"}
    if frame.empty or not required <= set(frame.columns):
        return {}
    out: dict[tuple[str, str, str], dict[str, object]] = {}
    for _, row in frame.iterrows():
        out[_fixture_key(row["date"], row["home_team"], row["away_team"])] = row.to_dict()
    return out


def find_line_movement(
    index: dict[tuple[str, str, str], dict[str, object]],
    *,
    date: object,
    home_team: object,
    away_team: object,
) -> dict[str, object]:
    return _find_by_fixture(index, date=date, home_team=home_team, away_team=away_team)


def load_structured_intelligence_index(path: str | Path | None) -> dict[str, dict[str, object]]:
    frame = _read_optional_csv(path)
    if frame.empty or "match_id" not in frame.columns:
        return {}
    if "category" not in frame.columns:
        frame["category"] = "other"
    if "severity" not in frame.columns:
        frame["severity"] = 1.0
    rows = []
    for _, row in frame.iterrows():
        category = str(row.get("category", "other")).strip().lower()
        if category not in INTELLIGENCE_CATEGORIES:
            category = "other"
        try:
            severity = float(row.get("severity", 1.0) or 1.0)
        except (TypeError, ValueError):
            severity = 1.0
        rows.append(
            {
                "match_id": str(row["match_id"]).replace(".0", ""),
                "category": category,
                "severity": max(0.0, min(3.0, severity)),
            }
        )
    normalized = pd.DataFrame(rows)
    index: dict[str, dict[str, object]] = {}
    for match_id, group in normalized.groupby("match_id"):
        summary: dict[str, object] = {
            "structured_intelligence_count": int(len(group)),
            "structured_intelligence_severity": float(group["severity"].sum()),
        }
        for category in sorted(INTELLIGENCE_CATEGORIES):
            subset = group[group["category"].eq(category)]
            summary[f"structured_{category}_count"] = int(len(subset))
            summary[f"structured_{category}_severity"] = float(subset["severity"].sum())
        index[str(match_id)] = summary
    return index


def load_absence_index(path: str | Path | None) -> dict[tuple[str, str], dict[str, object]]:
    frame = _read_optional_csv(path)
    required = {"date", "team", "status"}
    if frame.empty or not required <= set(frame.columns):
        return {}
    if "impact" not in frame.columns:
        frame["impact"] = 1.0
    rows = []
    for _, row in frame.iterrows():
        status = str(row.get("status", "")).strip().lower()
        weight = ABSENCE_STATUS_WEIGHTS.get(status, 0.0)
        try:
            impact = float(row.get("impact", 1.0) or 1.0)
        except (TypeError, ValueError):
            impact = 1.0
        rows.append(
            {
                "date": str(pd.Timestamp(row["date"]).date()),
                "team": normalize_national_team(row["team"]),
                "status": status,
                "weighted_impact": max(0.0, impact) * weight,
            }
        )
    normalized = pd.DataFrame(rows)
    index: dict[tuple[str, str], dict[str, object]] = {}
    for (date, team), group in normalized.groupby(["date", "team"]):
        index[(date, team)] = {
            "absence_count": int(len(group)),
            "absence_weighted_impact": float(group["weighted_impact"].sum()),
            "injury_count": int(group["status"].eq("injured").sum()),
            "suspension_count": int(group["status"].eq("suspended").sum()),
        }
    return index


def find_team_absences(
    index: dict[tuple[str, str], dict[str, object]],
    *,
    date: object,
    team: object,
    date_tolerance_days: int = 1,
) -> dict[str, object]:
    target = pd.Timestamp(date).normalize()
    team_norm = normalize_national_team(team)
    exact = index.get((str(target.date()), team_norm))
    if exact is not None:
        return exact
    candidates: list[tuple[int, dict[str, object]]] = []
    for record_date, record_team in index:
        if record_team != team_norm:
            continue
        gap = abs((pd.Timestamp(record_date).normalize() - target).days)
        if gap <= date_tolerance_days:
            candidates.append((gap, index[(record_date, record_team)]))
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1] if candidates else {}


def load_realtime_lineup_index(path: str | Path | None) -> dict[tuple[str, str], dict[str, object]]:
    frame = _read_optional_csv(path)
    required = {"match_id", "team", "role"}
    if frame.empty or not required <= set(frame.columns):
        return {}
    if "confirmed" not in frame.columns:
        frame["confirmed"] = 1
    rows = []
    for _, row in frame.iterrows():
        role = str(row.get("role", "")).strip().lower()
        confirmed = str(row.get("confirmed", "1")).strip().lower() in {"1", "true", "yes"}
        rows.append(
            {
                "match_id": str(row["match_id"]).replace(".0", ""),
                "team": normalize_national_team(row["team"]),
                "role": role,
                "confirmed": confirmed,
            }
        )
    normalized = pd.DataFrame(rows)
    index: dict[tuple[str, str], dict[str, object]] = {}
    for (match_id, team), group in normalized.groupby(["match_id", "team"]):
        starters = group[group["role"].eq("starter")]
        substitutes = group[group["role"].eq("substitute")]
        index[(str(match_id), team)] = {
            "realtime_lineup_players": int(len(group)),
            "realtime_starters": int(len(starters)),
            "realtime_substitutes": int(len(substitutes)),
            "realtime_lineup_confirmed": int(bool(len(starters) >= 11 and group["confirmed"].all())),
        }
    return index


def find_realtime_lineup(
    index: dict[tuple[str, str], dict[str, object]],
    *,
    match_id: object,
    team: object,
) -> dict[str, object]:
    return index.get((str(match_id).replace(".0", ""), normalize_national_team(team)), {})


def absence_goal_shift(home_absences: dict[str, object], away_absences: dict[str, object]) -> float:
    home_impact = float(home_absences.get("absence_weighted_impact", 0.0) or 0.0)
    away_impact = float(away_absences.get("absence_weighted_impact", 0.0) or 0.0)
    return max(-0.12, min(0.12, (away_impact - home_impact) * 0.015))
