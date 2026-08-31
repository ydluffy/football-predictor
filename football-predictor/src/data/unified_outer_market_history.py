from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from data.api_football_odds_snapshot import SNAPSHOT_COLUMNS


MODEL_HISTORY_COLUMNS = [
    "snapshot_id", "match_id", "date", "captured_at", "commence_time",
    "home_team", "away_team", "home_key", "away_key",
    "external_h2h_home_avg_odds", "external_h2h_draw_avg_odds",
    "external_h2h_away_avg_odds", "external_home_spread_point",
    "external_home_spread_avg_odds", "external_away_spread_avg_odds",
    "external_over_avg_odds", "external_under_avg_odds", "snapshot_type",
    "source", "source_snapshot_dir", "mapping_status", "before_kickoff",
    "complete_for_shadow_inference",
]


def _truthy(value: object) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1", "yes"}


def _record_id(*parts: object) -> str:
    material = "|".join(str(part) for part in parts)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or not path.stat().st_size:
        return pd.DataFrame()
    try:
        return pd.read_csv(path, low_memory=False)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _paired_spreads(odds: pd.DataFrame) -> pd.DataFrame:
    spreads = odds[odds["market_key"].astype(str).eq("spreads")].copy()
    if spreads.empty:
        return pd.DataFrame()
    keys = ["event_id", "bookmaker_key"]
    home = spreads[spreads["outcome_label"].astype(str).eq("home_spread")].copy()
    away = spreads[spreads["outcome_label"].astype(str).eq("away_spread")].copy()
    home["home_handicap"] = pd.to_numeric(home["point"], errors="coerce")
    away["home_handicap"] = -pd.to_numeric(away["point"], errors="coerce")
    home["home_odds"] = pd.to_numeric(home["price"], errors="coerce")
    away["away_odds"] = pd.to_numeric(away["price"], errors="coerce")
    paired = home.merge(
        away[keys + ["home_handicap", "away_odds"]],
        on=keys + ["home_handicap"],
        how="inner",
    )
    paired = paired[(paired["home_odds"] > 1.0) & (paired["away_odds"] > 1.0)].copy()
    paired["price_balance_score"] = (paired["home_odds"] / paired["away_odds"]).map(
        lambda value: abs(math.log(value)) if value > 0 else float("nan")
    )
    return paired


def _summary_value(summary: pd.DataFrame, event_id: str, market: str, point: float | None = None) -> pd.Series:
    rows = summary[
        summary["event_id"].astype(str).eq(event_id)
        & summary["market_key"].astype(str).eq(market)
    ].copy()
    if point is not None and not rows.empty:
        numeric = pd.to_numeric(rows["point"], errors="coerce")
        rows = rows[(numeric - point).abs().le(1e-9)]
    return rows.iloc[0] if not rows.empty else pd.Series(dtype=object)


def normalize_the_odds_snapshot(snapshot_dir: str | Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    directory = Path(snapshot_dir)
    audit = json.loads((directory / "audit.json").read_text(encoding="utf-8"))
    alignment = _read_csv(directory / "sporttery_alignment.csv")
    odds = _read_csv(directory / "odds.csv")
    summary = _read_csv(directory / "match_market_summary.csv")
    captured_at = str(audit.get("captured_at") or "")
    snapshot_type = str(audit.get("snapshot_type") or "")
    snapshot_id = f"the_odds_api_{pd.to_datetime(captured_at, utc=True).strftime('%Y%m%dT%H%M%SZ')}_{snapshot_type}"
    outer_rows: list[dict[str, Any]] = []
    model_rows: list[dict[str, Any]] = []
    paired = _paired_spreads(odds) if not odds.empty else pd.DataFrame()

    for _, mapping in alignment.iterrows():
        if str(mapping.get("mapping_status")) != "mapped":
            continue
        event_id = str(mapping.get("event_id") or "")
        event_pairs = paired[paired["event_id"].astype(str).eq(event_id)].copy() if not paired.empty else pd.DataFrame()
        if not event_pairs.empty:
            event_pairs["is_bookmaker_main_line"] = False
            indices = event_pairs.groupby("bookmaker_key")["price_balance_score"].idxmin()
            event_pairs.loc[indices, "is_bookmaker_main_line"] = True
        kickoff = pd.to_datetime(mapping.get("kickoff"), errors="coerce", utc=True)
        captured = pd.to_datetime(captured_at, errors="coerce", utc=True)
        before_kickoff = bool(pd.notna(kickoff) and pd.notna(captured) and captured < kickoff)
        for _, item in event_pairs.iterrows():
            quarter_line = abs(float(item["home_handicap"]) * 4 - round(float(item["home_handicap"]) * 4)) < 1e-8
            primary = bool(item["is_bookmaker_main_line"] and item["price_balance_score"] <= 0.5)
            eligible = before_kickoff and quarter_line
            outer_rows.append({
                "record_id": _record_id(snapshot_id, event_id, item.get("bookmaker_key"), item.get("home_handicap")),
                "snapshot_id": snapshot_id, "captured_at": captured_at, "source": "the_odds_api",
                "source_fixture_id": event_id, "match_id": mapping.get("match_id", ""),
                "competition_id": mapping.get("competition_id", ""), "league_id": mapping.get("sport_key", ""),
                "league_name": mapping.get("competition", ""), "kickoff_at": mapping.get("kickoff", ""),
                "home_team": mapping.get("home_team", ""), "away_team": mapping.get("away_team", ""),
                "bookmaker_id": item.get("bookmaker_key", ""), "bookmaker_name": item.get("bookmaker_title", ""),
                "bet_id": "spreads", "bet_name": "Asian Handicap", "home_handicap": item.get("home_handicap"),
                "away_handicap": -float(item.get("home_handicap")), "home_odds": item.get("home_odds"),
                "away_odds": item.get("away_odds"), "raw_home_value": item.get("outcome_name", ""),
                "raw_away_value": "", "provider_updated_at": item.get("market_last_update", ""),
                "raw_sha256": audit.get("files", {}).get("raw_payload.json", {}).get("sha256", ""),
                "raw_archive_path": str((directory / "raw_payload.json").resolve()),
                "mapping_status": "mapped", "before_kickoff": before_kickoff, "quarter_line": quarter_line,
                "price_balance_score": item.get("price_balance_score"),
                "is_bookmaker_main_line": bool(item.get("is_bookmaker_main_line")),
                "primary_line_price_balanced": bool(item.get("price_balance_score") <= 0.5),
                "eligible_for_research": eligible,
                "eligible_for_primary_research": bool(eligible and primary),
                "reject_reason": "" if eligible else "captured_at_not_before_kickoff_or_non_quarter_handicap",
            })

        h2h = _summary_value(summary, event_id, "h2h")
        main = event_pairs[event_pairs.get("is_bookmaker_main_line", False).astype(bool)] if not event_pairs.empty else pd.DataFrame()
        if not main.empty:
            point_counts = main.groupby("home_handicap").size().sort_values(ascending=False)
            main_point = float(point_counts.index[0])
            primary_rows = main[pd.to_numeric(main["home_handicap"], errors="coerce").eq(main_point)]
            spread_home = float(pd.to_numeric(primary_rows["home_odds"], errors="coerce").mean())
            spread_away = float(pd.to_numeric(primary_rows["away_odds"], errors="coerce").mean())
        else:
            main_point = float("nan"); spread_home = float("nan"); spread_away = float("nan")
        totals = summary[summary["event_id"].astype(str).eq(event_id) & summary["market_key"].astype(str).eq("totals")].copy()
        total_25 = totals[(pd.to_numeric(totals.get("point"), errors="coerce") - 2.5).abs().le(1e-9)] if not totals.empty else pd.DataFrame()
        total = total_25.iloc[0] if not total_25.empty else pd.Series(dtype=object)
        required_odds = [h2h.get("home_avg_odds"), h2h.get("draw_avg_odds"), h2h.get("away_avg_odds"),
                         spread_home, spread_away, total.get("over_avg_odds"), total.get("under_avg_odds")]
        complete = (
            before_kickoff
            and pd.notna(main_point)
            and all(pd.notna(value) and float(value) > 1.0 for value in required_odds)
        )
        model_rows.append({
            "snapshot_id": snapshot_id, "match_id": mapping.get("match_id", ""),
            "date": str(pd.to_datetime(mapping.get("kickoff"), errors="coerce").date()),
            "captured_at": captured_at, "commence_time": mapping.get("kickoff", ""),
            "home_team": mapping.get("external_home_team", ""), "away_team": mapping.get("external_away_team", ""),
            "home_key": "", "away_key": "", "external_h2h_home_avg_odds": h2h.get("home_avg_odds", ""),
            "external_h2h_draw_avg_odds": h2h.get("draw_avg_odds", ""),
            "external_h2h_away_avg_odds": h2h.get("away_avg_odds", ""),
            "external_home_spread_point": main_point, "external_home_spread_avg_odds": spread_home,
            "external_away_spread_avg_odds": spread_away, "external_over_avg_odds": total.get("over_avg_odds", ""),
            "external_under_avg_odds": total.get("under_avg_odds", ""), "snapshot_type": snapshot_type,
            "source": "the_odds_api", "source_snapshot_dir": str(directory.resolve()), "mapping_status": "mapped",
            "before_kickoff": before_kickoff, "complete_for_shadow_inference": complete,
        })
    return (
        pd.DataFrame(outer_rows, columns=SNAPSHOT_COLUMNS),
        pd.DataFrame(model_rows, columns=MODEL_HISTORY_COLUMNS),
        {"snapshot_id": snapshot_id, "outer_rows": len(outer_rows), "model_rows": len(model_rows)},
    )


def build_unified_histories(
    *, api_football_history: str | Path, the_odds_snapshot_root: str | Path,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    api_path = Path(api_football_history)
    api = _read_csv(api_path)
    if api.empty:
        api = pd.DataFrame(columns=SNAPSHOT_COLUMNS)
    else:
        api = api.reindex(columns=SNAPSHOT_COLUMNS)
    outer_frames = [api]
    model_frames: list[pd.DataFrame] = []
    snapshots: list[dict[str, Any]] = []
    root = Path(the_odds_snapshot_root)
    for audit_path in sorted(root.glob("*/audit.json")) if root.exists() else []:
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        if audit.get("status") not in {"complete", "partial"} or audit.get("source") != "the_odds_api":
            continue
        outer, model, info = normalize_the_odds_snapshot(audit_path.parent)
        outer_frames.append(outer); model_frames.append(model); snapshots.append(info)
    unified = pd.concat(outer_frames, ignore_index=True, sort=False).reindex(columns=SNAPSHOT_COLUMNS)
    if not unified.empty:
        unified = unified.drop_duplicates("record_id", keep="last").sort_values(
            ["captured_at", "match_id", "bookmaker_id", "home_handicap"], kind="mergesort"
        )
    model_history = pd.concat(model_frames, ignore_index=True, sort=False).reindex(columns=MODEL_HISTORY_COLUMNS) if model_frames else pd.DataFrame(columns=MODEL_HISTORY_COLUMNS)
    if not model_history.empty:
        model_history = model_history.drop_duplicates(["snapshot_id", "match_id"], keep="last").sort_values(
            ["captured_at", "match_id"], kind="mergesort"
        )
    audit = {
        "schema_version": 1, "status": "ok", "api_football_rows": int(len(api)),
        "the_odds_snapshots": len(snapshots), "the_odds_outer_rows": sum(x["outer_rows"] for x in snapshots),
        "unified_outer_rows": int(len(unified)), "unified_outer_matches": int(unified["match_id"].astype(str).replace("", pd.NA).nunique()),
        "model_history_rows": int(len(model_history)),
        "model_complete_rows": int(model_history["complete_for_shadow_inference"].map(_truthy).sum()) if not model_history.empty else 0,
        "sources": sorted(unified["source"].dropna().astype(str).unique().tolist()) if not unified.empty else [],
        "snapshots": snapshots,
    }
    return unified, model_history, audit
