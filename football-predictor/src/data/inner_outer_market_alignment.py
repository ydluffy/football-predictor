from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


PAIR_COLUMNS = [
    "match_id", "sales_day", "match_number", "competition", "home_team", "away_team",
    "kickoff_at", "sporttery_snapshot_id", "sporttery_captured_at", "sporttery_handicap",
    "rqspf_odds_home", "rqspf_odds_draw", "rqspf_odds_away", "outer_snapshot_id",
    "outer_captured_at", "source_fixture_id", "bookmaker_id", "bookmaker_name",
    "outer_home_handicap", "outer_home_odds", "outer_away_odds",
    "sporttery_minus_outer_handicap", "time_delta_minutes", "time_aligned",
]


def _truthy(value: object) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1", "yes"}


def load_sporttery_market_snapshots(index_path: str | Path) -> pd.DataFrame:
    index = pd.read_csv(index_path, dtype=str, keep_default_na=False)
    index = index[index["source_type"].eq("official_markets")].copy()
    frames: list[pd.DataFrame] = []
    for _, item in index.iterrows():
        archive = Path(item["archive_path"])
        if not archive.exists() or not archive.stat().st_size:
            continue
        try:
            frame = pd.read_csv(archive, dtype=str, keep_default_na=False)
        except pd.errors.EmptyDataError:
            # Failed official fetches are intentionally archived as BOM-only
            # evidence.  They must remain auditable without blocking later
            # valid snapshots from the alignment history scan.
            continue
        if frame.empty:
            continue
        frame["snapshot_id"] = item["snapshot_id"]
        frame["captured_at"] = item["captured_at"]
        frame["sales_day"] = item["sales_day"]
        frame["match_number"] = frame["match_number"].astype(str).str.zfill(3)
        frame["match_id"] = frame.get("match_id", "").astype(str).str.strip()
        missing = frame["match_id"].eq("")
        frame.loc[missing, "match_id"] = frame.loc[missing, "sales_day"] + "|" + frame.loc[missing, "match_number"]
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    result = pd.concat(frames, ignore_index=True, sort=False)
    result["captured_parsed"] = pd.to_datetime(result["captured_at"], errors="coerce", utc=True, format="mixed")
    result["kickoff_parsed"] = pd.to_datetime(result["kickoff_time"], errors="coerce", format="mixed")
    naive = result["kickoff_parsed"].dt.tz is None
    if naive:
        result["kickoff_parsed"] = result["kickoff_parsed"].dt.tz_localize("Asia/Shanghai").dt.tz_convert("UTC")
    else:
        result["kickoff_parsed"] = result["kickoff_parsed"].dt.tz_convert("UTC")
    return result[result["captured_parsed"].notna() & result["kickoff_parsed"].notna()
                  & result["captured_parsed"].lt(result["kickoff_parsed"])].copy()


def align_inner_outer_markets(
    sporttery: pd.DataFrame, outer: pd.DataFrame, *, max_delta_minutes: int = 30,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if sporttery.empty or outer.empty:
        return pd.DataFrame(columns=PAIR_COLUMNS), {
            "sporttery_rows": int(len(sporttery)), "outer_rows": int(len(outer)),
            "identity_paired_events": 0, "time_aligned_events": 0,
            "time_aligned_pairs": 0, "max_delta_minutes": int(max_delta_minutes),
        }
    inner = sporttery.copy()
    if "captured_parsed" not in inner:
        inner["captured_parsed"] = pd.to_datetime(inner["captured_at"], errors="coerce", utc=True, format="mixed")
    if "kickoff_parsed" not in inner:
        inner["kickoff_parsed"] = pd.to_datetime(inner["kickoff_time"], errors="coerce", utc=True, format="mixed")
    ext = outer.copy()
    ext = ext[
        ext["mapping_status"].eq("mapped")
        & ext["before_kickoff"].map(_truthy)
        & ext["eligible_for_primary_research"].map(_truthy)
        & ext["match_id"].astype(str).str.strip().ne("")
    ].copy()
    ext["captured_parsed"] = pd.to_datetime(ext["captured_at"], errors="coerce", utc=True, format="mixed")
    rows: list[dict[str, Any]] = []
    unmatched_outer: list[str] = []
    for _, item in ext.iterrows():
        candidates = inner[inner["match_id"].astype(str).eq(str(item["match_id"]))].copy()
        if candidates.empty or pd.isna(item["captured_parsed"]):
            unmatched_outer.append(str(item.get("record_id", "")))
            continue
        candidates["delta"] = candidates["captured_parsed"].sub(item["captured_parsed"]).abs()
        selected = candidates.sort_values(["delta", "captured_parsed"]).iloc[0]
        delta_minutes = float(selected["delta"].total_seconds() / 60.0)
        sporttery_handicap = pd.to_numeric(selected.get("home_handicap"), errors="coerce")
        outer_handicap = pd.to_numeric(item.get("home_handicap"), errors="coerce")
        rows.append({
            "match_id": str(item["match_id"]), "sales_day": selected.get("sales_day", ""),
            "match_number": selected.get("match_number", ""), "competition": selected.get("competition", ""),
            "home_team": selected.get("home_team", ""), "away_team": selected.get("away_team", ""),
            "kickoff_at": pd.Timestamp(selected["kickoff_parsed"]).isoformat(),
            "sporttery_snapshot_id": selected.get("snapshot_id", ""),
            "sporttery_captured_at": pd.Timestamp(selected["captured_parsed"]).isoformat(),
            "sporttery_handicap": sporttery_handicap, "rqspf_odds_home": selected.get("rqspf_odds_home", ""),
            "rqspf_odds_draw": selected.get("rqspf_odds_draw", ""), "rqspf_odds_away": selected.get("rqspf_odds_away", ""),
            "outer_snapshot_id": item.get("snapshot_id", ""),
            "outer_captured_at": pd.Timestamp(item["captured_parsed"]).isoformat(),
            "source_fixture_id": item.get("source_fixture_id", ""), "bookmaker_id": item.get("bookmaker_id", ""),
            "bookmaker_name": item.get("bookmaker_name", ""), "outer_home_handicap": outer_handicap,
            "outer_home_odds": item.get("home_odds", ""), "outer_away_odds": item.get("away_odds", ""),
            "sporttery_minus_outer_handicap": sporttery_handicap - outer_handicap,
            "time_delta_minutes": round(delta_minutes, 3), "time_aligned": delta_minutes <= int(max_delta_minutes),
        })
    pairs = pd.DataFrame(rows, columns=PAIR_COLUMNS)
    aligned = pairs[pairs["time_aligned"].map(_truthy)] if not pairs.empty else pairs
    deltas = pd.to_numeric(pairs.get("time_delta_minutes"), errors="coerce")
    return pairs, {
        "sporttery_rows": int(len(inner)), "sporttery_events": int(inner["match_id"].nunique()),
        "outer_rows": int(len(outer)), "outer_primary_eligible_rows": int(len(ext)),
        "outer_primary_events": int(ext["match_id"].nunique()) if not ext.empty else 0,
        "identity_paired_events": int(pairs["match_id"].nunique()) if not pairs.empty else 0,
        "identity_pairs": int(len(pairs)), "time_aligned_events": int(aligned["match_id"].nunique()) if not aligned.empty else 0,
        "time_aligned_pairs": int(len(aligned)), "max_delta_minutes": int(max_delta_minutes),
        "min_delta_minutes": None if deltas.empty else round(float(deltas.min()), 3),
        "median_delta_minutes": None if deltas.empty else round(float(deltas.median()), 3),
        "max_observed_delta_minutes": None if deltas.empty else round(float(deltas.max()), 3),
        "unmatched_outer_records": [value for value in unmatched_outer if value],
    }
