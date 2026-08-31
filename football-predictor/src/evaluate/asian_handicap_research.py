from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd


LINE_LABELS = {
    0.0: "平手",
    0.25: "平半",
    0.5: "半球",
    0.75: "半一",
    1.0: "一球",
    1.25: "一球/球半",
    1.5: "球半",
    1.75: "球半/两球",
    2.0: "两球",
    2.25: "两球/两球半",
    2.5: "两球半",
    2.75: "两球半/三球",
    3.0: "三球",
}


@dataclass(frozen=True)
class AsianSettlement:
    result: str
    net_return: float
    component_lines: tuple[float, ...]
    component_results: tuple[str, ...]


def _number(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(parsed) else parsed


def normalize_quarter_line(value: object, *, tolerance: float = 0.011) -> float | None:
    parsed = _number(value)
    if parsed is None:
        return None
    rounded = round(parsed * 4.0) / 4.0
    if abs(parsed - rounded) > tolerance:
        return None
    return 0.0 if abs(rounded) < tolerance else float(rounded)


def exact_line_label(value: object) -> str:
    line = normalize_quarter_line(value)
    if line is None:
        return "未知"
    depth = abs(line)
    return LINE_LABELS.get(depth, f"{depth:g}球")


def split_asian_line(value: object) -> tuple[float, ...]:
    line = normalize_quarter_line(value)
    if line is None:
        raise ValueError(f"invalid Asian handicap line: {value}")
    quarter_units = int(round(line * 4.0))
    if abs(quarter_units) % 2 == 1:
        return (line - 0.25, line + 0.25)
    return (line,)


def _component_result(margin: float, line: float) -> str:
    adjusted = margin + line
    if adjusted > 1e-12:
        return "win"
    if adjusted < -1e-12:
        return "loss"
    return "push"


def settle_asian_handicap(
    home_goals: object,
    away_goals: object,
    home_line: object,
    *,
    side: str,
    decimal_odds: object,
) -> AsianSettlement:
    home = _number(home_goals)
    away = _number(away_goals)
    odds = _number(decimal_odds)
    if home is None or away is None or odds is None or odds <= 1.0:
        raise ValueError("scores and decimal odds must be valid")
    if side not in {"home", "away"}:
        raise ValueError("side must be home or away")

    selected_line = normalize_quarter_line(home_line)
    if selected_line is None:
        raise ValueError(f"invalid Asian handicap line: {home_line}")
    if side == "away":
        selected_line = -selected_line
    margin = home - away if side == "home" else away - home
    components = split_asian_line(selected_line)
    results = tuple(_component_result(margin, line) for line in components)
    weight = 1.0 / len(results)
    net_return = sum(
        weight * (odds - 1.0 if result == "win" else -1.0 if result == "loss" else 0.0)
        for result in results
    )
    counts = {name: results.count(name) for name in ("win", "push", "loss")}
    if counts["win"] == len(results):
        result = "full_win"
    elif counts["loss"] == len(results):
        result = "full_loss"
    elif counts["push"] == len(results):
        result = "push"
    elif counts["win"] and counts["push"]:
        result = "half_win"
    elif counts["loss"] and counts["push"]:
        result = "half_loss"
    else:
        result = "split"
    return AsianSettlement(result, float(net_return), components, results)


def _numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _favorite_side(home_line: float, home_odds: float, away_odds: float) -> str:
    if home_line < 0:
        return "home"
    if home_line > 0:
        return "away"
    return "home" if home_odds <= away_odds else "away"


def build_exact_handicap_dataset(matches: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    required = {"match_id", "date", "season", "league", "home_team", "away_team", "home_goals", "away_goals"}
    missing = required - set(matches.columns)
    if missing:
        raise ValueError(f"missing exact handicap columns: {sorted(missing)}")

    frame = matches.copy()
    fields = {
        "opening_line": "AHh",
        "opening_home_odds": "AvgAHH",
        "opening_away_odds": "AvgAHA",
        "closing_line": "AHCh",
        "closing_home_odds": "AvgCAHH",
        "closing_away_odds": "AvgCAHA",
    }
    for target, source in fields.items():
        frame[target] = _numeric_series(frame, source)
    frame["home_goals"] = pd.to_numeric(frame["home_goals"], errors="coerce")
    frame["away_goals"] = pd.to_numeric(frame["away_goals"], errors="coerce")

    opening_valid = frame[["opening_line", "opening_home_odds", "opening_away_odds"]].notna().all(axis=1)
    closing_valid = frame[["closing_line", "closing_home_odds", "closing_away_odds"]].notna().all(axis=1)
    score_valid = frame[["home_goals", "away_goals"]].notna().all(axis=1)
    usable = frame.loc[opening_valid & score_valid].copy()
    rows: list[dict[str, Any]] = []
    rejected_non_quarter = 0
    for _, row in usable.iterrows():
        opening_line = normalize_quarter_line(row["opening_line"])
        if opening_line is None:
            rejected_non_quarter += 1
            continue
        opening_side = _favorite_side(opening_line, float(row["opening_home_odds"]), float(row["opening_away_odds"]))
        opening_odds = float(row[f"opening_{opening_side}_odds"])
        opening = settle_asian_handicap(
            row["home_goals"], row["away_goals"], opening_line, side=opening_side, decimal_odds=opening_odds
        )
        closing_line = normalize_quarter_line(row["closing_line"]) if pd.notna(row["closing_line"]) else None
        closing_side = ""
        closing_result = ""
        closing_return = np.nan
        movement = np.nan
        movement_quarters = np.nan
        movement_direction = "missing"
        if closing_line is not None and pd.notna(row["closing_home_odds"]) and pd.notna(row["closing_away_odds"]):
            closing_side = _favorite_side(closing_line, float(row["closing_home_odds"]), float(row["closing_away_odds"]))
            closing_odds = float(row[f"closing_{closing_side}_odds"])
            closing = settle_asian_handicap(
                row["home_goals"], row["away_goals"], closing_line, side=closing_side, decimal_odds=closing_odds
            )
            closing_result = closing.result
            closing_return = closing.net_return
            movement = closing_line - opening_line
            movement_quarters = int(round(movement * 4.0))
            movement_direction = "stable" if movement_quarters == 0 else "toward_home" if movement_quarters < 0 else "toward_away"
        rows.append(
            {
                "match_id": row["match_id"],
                "date": row["date"],
                "season": row["season"],
                "league": row["league"],
                "home_team": row["home_team"],
                "away_team": row["away_team"],
                "home_goals": int(row["home_goals"]),
                "away_goals": int(row["away_goals"]),
                "opening_home_line": opening_line,
                "opening_line_depth": abs(opening_line),
                "opening_line_label": exact_line_label(opening_line),
                "opening_favorite_side": opening_side,
                "opening_favorite_odds": opening_odds,
                "opening_favorite_result": opening.result,
                "opening_favorite_net_return": opening.net_return,
                "closing_home_line": closing_line,
                "closing_line_depth": abs(closing_line) if closing_line is not None else np.nan,
                "closing_line_label": exact_line_label(closing_line) if closing_line is not None else "",
                "closing_favorite_side": closing_side,
                "closing_favorite_result": closing_result,
                "closing_favorite_net_return": closing_return,
                "home_line_movement": movement,
                "home_line_movement_quarters": movement_quarters,
                "home_line_movement_direction": movement_direction,
                "opening_market_margin": 1.0 / float(row["opening_home_odds"]) + 1.0 / float(row["opening_away_odds"]) - 1.0,
            }
        )
    dataset = pd.DataFrame(rows)
    audit = {
        "source_rows": int(len(frame)),
        "score_complete_rows": int(score_valid.sum()),
        "opening_complete_rows": int((opening_valid & score_valid).sum()),
        "closing_complete_rows": int((closing_valid & score_valid).sum()),
        "research_rows": int(len(dataset)),
        "rejected_non_quarter_lines": int(rejected_non_quarter),
        "date_min": str(dataset["date"].min()) if not dataset.empty else None,
        "date_max": str(dataset["date"].max()) if not dataset.empty else None,
        "seasons": int(dataset["season"].nunique()) if not dataset.empty else 0,
        "leagues": int(dataset["league"].nunique()) if not dataset.empty else 0,
    }
    return dataset, audit


def summarize_exact_handicaps(
    dataset: pd.DataFrame,
    *,
    group_columns: Iterable[str],
    minimum_observation: int = 100,
) -> pd.DataFrame:
    columns = list(group_columns)
    if dataset.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for keys, group in dataset.groupby(columns, dropna=False, sort=True):
        if not isinstance(keys, tuple):
            keys = (keys,)
        result_counts = group["opening_favorite_result"].value_counts()
        closing_returns = pd.to_numeric(group["closing_favorite_net_return"], errors="coerce").dropna()
        row = dict(zip(columns, keys))
        row.update(
            {
                "matches": int(len(group)),
                "seasons": int(group["season"].nunique()),
                "full_win": int(result_counts.get("full_win", 0)),
                "half_win": int(result_counts.get("half_win", 0)),
                "push": int(result_counts.get("push", 0)),
                "half_loss": int(result_counts.get("half_loss", 0)),
                "full_loss": int(result_counts.get("full_loss", 0)),
                "opening_favorite_roi": float(group["opening_favorite_net_return"].mean()),
                "closing_favorite_roi": float(closing_returns.mean()) if not closing_returns.empty else np.nan,
                "closing_coverage": int(len(closing_returns)),
                "status": "eligible_for_research" if len(group) >= minimum_observation else "observation_only",
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def audit_live_market_archives(
    sporttery_history: pd.DataFrame,
    external_history: pd.DataFrame,
) -> dict[str, Any]:
    sporttery = sporttery_history.copy()
    external = external_history.copy()
    if not sporttery.empty:
        date = sporttery.get("date", pd.Series("", index=sporttery.index)).astype(str)
        number = sporttery.get("match_number", pd.Series("", index=sporttery.index)).astype(str)
        sporttery_fixture_count = int((date + "|" + number).nunique())
        sporttery_snapshot_count = int(
            sporttery.get("captured_at", pd.Series(dtype=str)).dropna().astype(str).nunique()
        )
        sporttery_lines = (
            pd.to_numeric(sporttery.get("home_handicap", pd.Series(dtype=float)), errors="coerce")
            .dropna()
            .value_counts()
            .sort_index()
        )
    else:
        sporttery_fixture_count = 0
        sporttery_snapshot_count = 0
        sporttery_lines = pd.Series(dtype=int)
    if not external.empty:
        external_event_count = int(
            external.get("event_id", pd.Series(dtype=str)).dropna().astype(str).nunique()
        )
        external_snapshot_count = int(
            external.get("captured_at", pd.Series(dtype=str)).dropna().astype(str).nunique()
        )
        external_lines = (
            pd.to_numeric(
                external.get("external_home_spread_point", pd.Series(dtype=float)), errors="coerce"
            )
            .dropna()
            .map(abs)
            .value_counts()
            .sort_index()
        )
    else:
        external_event_count = 0
        external_snapshot_count = 0
        external_lines = pd.Series(dtype=int)
    return {
        "sporttery_rows": int(len(sporttery)),
        "sporttery_unique_fixtures": sporttery_fixture_count,
        "sporttery_snapshot_times": sporttery_snapshot_count,
        "sporttery_line_counts": {str(key): int(value) for key, value in sporttery_lines.items()},
        "external_rows": int(len(external)),
        "external_unique_events": external_event_count,
        "external_snapshot_times": external_snapshot_count,
        "external_line_depth_counts": {str(key): int(value) for key, value in external_lines.items()},
        "time_aligned_pair_count": None,
        "time_aligned_pair_status": "not_yet_available_as_historical_training_data",
    }
