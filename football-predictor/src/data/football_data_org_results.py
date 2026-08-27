from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from data.api_football_prematch import build_api_football_match_mapping


RESULT_COLUMNS = [
    "date", "match_number", "competition", "home_team", "away_team",
    "all_home_team", "all_away_team", "handicap", "half_time_score",
    "full_time_score", "spf_result", "rqspf_result", "spf_odds_home",
    "spf_odds_draw", "spf_odds_away", "status", "source_match_id", "source",
]


def _outcome(home: int, away: int, *, handicap: int = 0, prefix: str = "") -> str:
    adjusted = home + handicap
    return f"{prefix}{'胜' if adjusted > away else '平' if adjusted == away else '负'}"


def load_scan_fixtures(path: str | Path) -> pd.DataFrame:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    frame = pd.DataFrame(payload.get("fixtures") or [])
    required = {"match_id", "match_number", "competition_id", "kickoff", "home_team", "away_team"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"scan fixtures missing columns: {sorted(missing)}")
    return frame


def build_sporttery_result_fallback(
    *, scan_fixtures: pd.DataFrame, football_matches: pd.DataFrame,
    official_markets: pd.DataFrame, tolerance_minutes: int = 15,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Map FINISHED matches strictly; unmatched or ambiguous rows never become results."""
    external = football_matches.rename(columns={
        "source_match_id": "source_fixture_id", "kickoff_at": "kickoff_time",
    }).copy()
    mapping, audit = build_api_football_match_mapping(
        scan_fixtures, external, tolerance_minutes=tolerance_minutes,
    )
    if mapping.empty:
        return pd.DataFrame(columns=RESULT_COLUMNS), mapping, {**audit, "result_rows": 0}
    local = scan_fixtures.set_index("match_id", drop=False)
    source = football_matches.set_index(football_matches["source_match_id"].astype(str), drop=False)
    market = official_markets.copy()
    market["match_number"] = market["match_number"].astype(str).str.zfill(3)
    markets = market.drop_duplicates("match_number", keep="last").set_index("match_number", drop=False)
    rows: list[dict[str, Any]] = []
    skipped_not_finished: list[str] = []
    skipped_missing_score: list[str] = []
    for _, mapped in mapping.iterrows():
        source_id = str(mapped["source_fixture_id"])
        remote = source.loc[source_id]
        if str(remote.get("status", "")) != "FINISHED":
            skipped_not_finished.append(source_id)
            continue
        home = pd.to_numeric(remote.get("home_score"), errors="coerce")
        away = pd.to_numeric(remote.get("away_score"), errors="coerce")
        if pd.isna(home) or pd.isna(away):
            skipped_missing_score.append(source_id)
            continue
        fixture = local.loc[str(mapped["match_id"])]
        number = str(fixture["match_number"]).zfill(3)
        odds = markets.loc[number] if number in markets.index else pd.Series(dtype=object)
        try:
            handicap = int(float(odds.get("home_handicap", 0) or 0))
        except (TypeError, ValueError):
            handicap = 0
        h, a = int(home), int(away)
        hh = pd.to_numeric(remote.get("half_home_score"), errors="coerce")
        ha = pd.to_numeric(remote.get("half_away_score"), errors="coerce")
        rows.append({
            "date": str(fixture.get("kickoff", ""))[:10], "match_number": number,
            "competition": fixture.get("competition", ""), "home_team": fixture["home_team"],
            "away_team": fixture["away_team"], "all_home_team": fixture["home_team"],
            "all_away_team": fixture["away_team"], "handicap": handicap,
            "half_time_score": "" if pd.isna(hh) or pd.isna(ha) else f"{int(hh)}:{int(ha)}",
            "full_time_score": f"{h}:{a}", "spf_result": _outcome(h, a),
            "rqspf_result": _outcome(h, a, handicap=handicap, prefix="让"),
            "spf_odds_home": odds.get("spf_odds_home", ""),
            "spf_odds_draw": odds.get("spf_odds_draw", ""),
            "spf_odds_away": odds.get("spf_odds_away", ""), "status": "已完成",
            "source_match_id": source_id, "source": "football_data_org_fallback",
        })
    results = pd.DataFrame(rows, columns=RESULT_COLUMNS)
    return results, mapping, {
        **audit, "result_rows": int(len(results)),
        "skipped_not_finished": skipped_not_finished,
        "skipped_missing_score": skipped_missing_score,
        "settlement_policy": "fallback_only_after_sporttery_official_unavailable",
    }
