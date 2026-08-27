from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from world_cup.public_absence_intelligence import INTELLIGENCE_COLUMNS
from world_cup.public_absence_intelligence import normalize_public_absence_intelligence


STATUS_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("suspended", ("suspended", "suspension", "ban", "banned", "red card")),
    ("doubtful", ("doubt", "doubtful", "questionable", "late fitness test")),
    ("illness", ("illness", "ill", "flu", "fever")),
    ("rested", ("rested", "rotation", "rest")),
    ("unavailable", ("unavailable", "not available", "absent")),
    (
        "injured",
        (
            "injury",
            "injured",
            "hamstring",
            "muscle",
            "knee",
            "ankle",
            "calf",
            "groin",
            "knock",
            "strain",
        ),
    ),
)

SOURCE_CONFIDENCE = {
    "transfermarkt": 0.8,
    "sports_mole": 0.68,
    "manual": 0.7,
}


def infer_absence_status(text: str) -> str:
    normalized = text.casefold()
    for status, patterns in STATUS_PATTERNS:
        if any(pattern in normalized for pattern in patterns):
            return status
    return "unknown"


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _row(
    *,
    date: str,
    team: str,
    player: str,
    status: str,
    reason: str,
    source: str,
    source_url: str,
    confidence: float | None = None,
    notes: str = "",
) -> dict[str, object]:
    return {
        "date": date,
        "team": _clean(team),
        "player": _clean(player),
        "player_id": "",
        "status": status,
        "impact": 1.0,
        "reason": _clean(reason),
        "source": source,
        "source_url": _clean(source_url),
        "confidence": confidence if confidence is not None else SOURCE_CONFIDENCE.get(source, 0.55),
        "reported_at": "",
        "updated_at": _now(),
        "notes": notes,
    }


def _split_structured_line(line: str) -> list[str]:
    if "|" in line:
        return [_clean(part) for part in line.split("|")]
    if "\t" in line:
        return [_clean(part) for part in line.split("\t")]
    return []


def parse_structured_absence_text(
    text: str,
    *,
    date: str,
    source: str,
    source_url: str = "",
    default_team: str = "",
    confidence: float | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for raw_line in text.splitlines():
        line = _clean(raw_line)
        if not line or line.startswith("#"):
            continue
        parts = _split_structured_line(line)
        if len(parts) >= 4:
            team, player, status_or_reason, reason = parts[:4]
            status = infer_absence_status(f"{status_or_reason} {reason}")
            if status == "unknown":
                status = status_or_reason.casefold().replace(" ", "_")
            rows.append(
                _row(
                    date=date,
                    team=team or default_team,
                    player=player,
                    status=status,
                    reason=reason or status_or_reason,
                    source=source,
                    source_url=parts[4] if len(parts) >= 5 and parts[4] else source_url,
                    confidence=confidence,
                    notes="structured_text",
                )
            )
    return normalize_public_absence_intelligence(pd.DataFrame(rows, columns=INTELLIGENCE_COLUMNS))


def parse_team_news_text(
    text: str,
    *,
    date: str,
    source: str,
    source_url: str = "",
    confidence: float | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    current_team = ""
    for raw_line in text.splitlines():
        line = _clean(raw_line)
        if not line or line.startswith("#"):
            continue
        team_match = re.match(r"^(?P<team>[A-Z][A-Za-z .'-]{2,40})\s*:\s*(?P<body>.+)$", line)
        if team_match:
            current_team = _clean(team_match.group("team"))
            body = team_match.group("body")
        else:
            body = line
        if not current_team:
            continue
        for player, reason in re.findall(r"([A-Z][A-Za-z .'-]{2,60})\s*\(([^)]+)\)", body):
            status = infer_absence_status(reason)
            rows.append(
                _row(
                    date=date,
                    team=current_team,
                    player=player,
                    status=status,
                    reason=reason,
                    source=source,
                    source_url=source_url,
                    confidence=confidence,
                    notes="team_news_parentheses",
                )
            )
        without_patterns = re.findall(
            r"(?:without|missing|absence of)\s+([A-Z][A-Za-z .'-]{2,60})\s+(?:due to|because of|with)\s+([^.;]+)",
            body,
            flags=re.IGNORECASE,
        )
        for player, reason in without_patterns:
            rows.append(
                _row(
                    date=date,
                    team=current_team,
                    player=player,
                    status=infer_absence_status(reason),
                    reason=reason,
                    source=source,
                    source_url=source_url,
                    confidence=confidence,
                    notes="team_news_sentence",
                )
            )
    return normalize_public_absence_intelligence(pd.DataFrame(rows, columns=INTELLIGENCE_COLUMNS))


def parse_public_absence_text_file(
    path: str | Path,
    *,
    date: str,
    source: str,
    source_url: str = "",
    mode: str = "auto",
    default_team: str = "",
    confidence: float | None = None,
) -> pd.DataFrame:
    text = Path(path).read_text(encoding="utf-8")
    if mode == "structured":
        return parse_structured_absence_text(
            text,
            date=date,
            source=source,
            source_url=source_url,
            default_team=default_team,
            confidence=confidence,
        )
    if mode == "team_news":
        return parse_team_news_text(
            text,
            date=date,
            source=source,
            source_url=source_url,
            confidence=confidence,
        )
    structured = parse_structured_absence_text(
        text,
        date=date,
        source=source,
        source_url=source_url,
        default_team=default_team,
        confidence=confidence,
    )
    team_news = parse_team_news_text(
        text,
        date=date,
        source=source,
        source_url=source_url,
        confidence=confidence,
    )
    if structured.empty:
        return team_news
    if team_news.empty:
        return structured
    return normalize_public_absence_intelligence(pd.concat([structured, team_news], ignore_index=True))
