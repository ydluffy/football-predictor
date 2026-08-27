from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from world_cup.data import normalize_national_team


INTELLIGENCE_COLUMNS = [
    "date",
    "team",
    "player",
    "player_id",
    "status",
    "impact",
    "reason",
    "source",
    "source_url",
    "confidence",
    "reported_at",
    "updated_at",
    "notes",
]

ABSENCE_COLUMNS = [
    "date",
    "team",
    "player",
    "player_id",
    "status",
    "impact",
    "reason",
    "source",
    "source_url",
    "confidence",
    "updated_at",
    "notes",
]

STATUS_MAP = {
    "": "unknown",
    "unknown": "unknown",
    "injury": "injured",
    "injured": "injured",
    "out": "injured",
    "ruled out": "injured",
    "suspended": "suspended",
    "suspension": "suspended",
    "ban": "suspended",
    "banned": "suspended",
    "doubt": "doubtful",
    "doubtful": "doubtful",
    "questionable": "doubtful",
    "ill": "illness",
    "illness": "illness",
    "unavailable": "unavailable",
    "rested": "rested",
    "available": "available",
}

DEFAULT_SOURCE_CONFIDENCE = {
    "fifa": 0.95,
    "official_team": 0.92,
    "association": 0.9,
    "transfermarkt": 0.8,
    "rotowire": 0.72,
    "sports_mole": 0.68,
    "sofascore": 0.65,
    "fotmob": 0.65,
    "flashscore": 0.62,
    "leisu": 0.58,
    "manual": 0.7,
}

MODEL_STATUSES = {"injured", "suspended", "doubtful", "illness", "unavailable", "rested"}


def empty_public_absence_intelligence() -> pd.DataFrame:
    return pd.DataFrame(columns=INTELLIGENCE_COLUMNS)


def empty_model_absences() -> pd.DataFrame:
    return pd.DataFrame(columns=ABSENCE_COLUMNS)


def _source_default_confidence(source: object) -> float:
    key = str(source or "").strip().casefold()
    return DEFAULT_SOURCE_CONFIDENCE.get(key, 0.55)


def _normalize_status(status: object) -> str:
    normalized = str(status or "").strip().casefold().replace("_", " ")
    return STATUS_MAP.get(normalized, normalized if normalized in MODEL_STATUSES else "unknown")


def normalize_public_absence_intelligence(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for column in INTELLIGENCE_COLUMNS:
        if column not in out.columns:
            out[column] = ""
    for column in ("team", "player", "player_id", "reason", "source", "source_url", "notes"):
        out[column] = out[column].astype("string").fillna("").str.strip()
    out["team"] = out["team"].map(normalize_national_team)
    out["status"] = out["status"].map(_normalize_status)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["date"] = out["date"].dt.date.astype("string").fillna("")
    out["reported_at"] = out["reported_at"].astype("string").fillna("").str.strip()
    out["updated_at"] = out["updated_at"].astype("string").fillna("").str.strip()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    out.loc[out["updated_at"].eq(""), "updated_at"] = now
    out["impact"] = pd.to_numeric(out["impact"], errors="coerce").fillna(1.0).clip(0.0, 3.0)
    confidence = pd.to_numeric(out["confidence"], errors="coerce")
    defaults = out["source"].map(_source_default_confidence)
    out["confidence"] = confidence.fillna(defaults).clip(0.0, 1.0)
    out = out[
        out["date"].ne("")
        & out["team"].ne("")
        & out["player"].ne("")
        & out["status"].ne("unknown")
    ].copy()
    return out[INTELLIGENCE_COLUMNS]


def load_public_absence_intelligence(paths: list[str | Path] | str | Path | None) -> pd.DataFrame:
    if paths is None:
        return empty_public_absence_intelligence()
    if isinstance(paths, (str, Path)):
        paths = [paths]
    frames: list[pd.DataFrame] = []
    for path in paths:
        file_path = Path(path)
        if file_path.exists():
            frames.append(pd.read_csv(file_path))
    if not frames:
        return empty_public_absence_intelligence()
    return normalize_public_absence_intelligence(pd.concat(frames, ignore_index=True))


def aggregate_public_absences(
    intelligence: pd.DataFrame,
    *,
    min_confidence: float = 0.6,
) -> pd.DataFrame:
    if intelligence.empty:
        return empty_model_absences()
    normalized = normalize_public_absence_intelligence(intelligence)
    usable = normalized[
        normalized["status"].isin(MODEL_STATUSES)
        & normalized["confidence"].ge(float(min_confidence))
    ].copy()
    if usable.empty:
        return empty_model_absences()
    usable = usable.sort_values(
        ["date", "team", "player", "confidence", "updated_at"],
        ascending=[True, True, True, False, False],
    )
    rows: list[dict[str, object]] = []
    for (_, team, player), group in usable.groupby(["date", "team", "player"], sort=False):
        best = group.iloc[0]
        sources = sorted(group["source"].dropna().astype(str).unique().tolist())
        urls = sorted(group["source_url"].dropna().astype(str).replace("", pd.NA).dropna().unique().tolist())
        rows.append(
            {
                "date": best["date"],
                "team": team,
                "player": player,
                "player_id": best.get("player_id", ""),
                "status": best["status"],
                "impact": float(group["impact"].max()),
                "reason": best.get("reason", ""),
                "source": "+".join(sources),
                "source_url": " | ".join(urls),
                "confidence": float(group["confidence"].max()),
                "updated_at": best.get("updated_at", ""),
                "notes": best.get("notes", ""),
            }
        )
    return pd.DataFrame(rows, columns=ABSENCE_COLUMNS)


def public_absence_summary(intelligence: pd.DataFrame, absences: pd.DataFrame) -> dict[str, object]:
    return {
        "intelligence_rows": int(len(intelligence)),
        "model_absence_rows": int(len(absences)),
        "teams_with_absences": int(absences["team"].nunique()) if "team" in absences.columns else 0,
        "players_with_absences": int(absences["player"].nunique()) if "player" in absences.columns else 0,
        "sources": sorted(intelligence["source"].dropna().astype(str).unique().tolist())
        if "source" in intelligence.columns and not intelligence.empty
        else [],
    }
