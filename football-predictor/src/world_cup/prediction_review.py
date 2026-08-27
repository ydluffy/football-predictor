from __future__ import annotations

import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from world_cup.data import normalize_national_team


RESULT_LABELS = {"H": "ä¸»èƒœ", "D": "å¹³å±€", "A": "å®¢èƒœ"}
GROUP_STATS_COLUMNS = [
    "group_type",
    "group",
    "matches",
    "result_accuracy",
    "top_score_1_accuracy",
    "top2_score_accuracy",
    "over_2_5_accuracy",
    "handicap_accuracy_on_recommended",
    "mean_logloss",
    "mean_brier",
    "average_actual_probability",
    "average_top_probability",
    "actual_goals_per_match",
    "expected_goals_per_match",
]


def _result_from_score(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "H"
    if home_goals < away_goals:
        return "A"
    return "D"


def _clean_id(value: object) -> str:
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return ""
    return text.removesuffix(".0")


def create_prediction_snapshot(
    prediction_path: str | Path,
    snapshot_dir: str | Path,
    *,
    snapshot_date: str,
) -> dict[str, object]:
    source = Path(prediction_path)
    if not source.exists():
        raise FileNotFoundError(source)
    destination_root = Path(snapshot_dir)
    destination_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    snapshot_name = f"world_cup_prediction_snapshot_{snapshot_date}.csv"
    snapshot_path = destination_root / snapshot_name
    manifest_path = snapshot_path.with_suffix(".json")
    if snapshot_path.exists() and manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    if snapshot_path.exists():
        raise FileExistsError(f"snapshot already exists without manifest: {snapshot_path}")
    shutil.copyfile(source, snapshot_path)
    manifest = {
        "snapshot_date": snapshot_date,
        "created_at": timestamp,
        "source_prediction_path": str(source),
        "snapshot_path": str(snapshot_path),
        "immutable_input_assumption": "Snapshot should be created before matches are settled and used as the audit input for post-match review.",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def load_enhanced_prediction_snapshot(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"match_id": str, "leisu_match_id": str})
    required = {
        "date",
        "match_id",
        "home_team",
        "away_team",
        "adjusted_p_home",
        "adjusted_p_draw",
        "adjusted_p_away",
        "expected_home_goals",
        "expected_away_goals",
        "top_score_1",
        "top_score_2",
        "over_2_5_probability",
        "under_2_5_probability",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"missing enhanced prediction columns: {sorted(missing)}")
    out = frame.copy()
    out["date"] = pd.to_datetime(out["date"], errors="raise")
    out["match_id"] = out["match_id"].map(_clean_id)
    out["home_team"] = out["home_team"].map(normalize_national_team)
    out["away_team"] = out["away_team"].map(normalize_national_team)
    for column in (
        "adjusted_p_home",
        "adjusted_p_draw",
        "adjusted_p_away",
        "expected_home_goals",
        "expected_away_goals",
        "over_2_5_probability",
        "under_2_5_probability",
    ):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    if "leisu_match_id" in out:
        out["leisu_match_id"] = out["leisu_match_id"].map(_clean_id)
    return out


def load_espn_completed_results(scoreboard_path: str | Path) -> pd.DataFrame:
    payload = json.loads(Path(scoreboard_path).read_text(encoding="utf-8"))
    rows: list[dict[str, object]] = []
    for event in payload.get("events") or []:
        competitions = event.get("competitions") or []
        if not competitions:
            continue
        competition = competitions[0]
        status = event.get("status", {}).get("type", {})
        if not status.get("completed"):
            continue
        competitors = competition.get("competitors") or []
        home = next((item for item in competitors if item.get("homeAway") == "home"), None)
        away = next((item for item in competitors if item.get("homeAway") == "away"), None)
        if home is None or away is None:
            continue
        try:
            home_goals = int(home.get("score"))
            away_goals = int(away.get("score"))
        except (TypeError, ValueError):
            continue
        rows.append(
            {
                "match_id": _clean_id(event.get("id")),
                "date": pd.Timestamp(str(event.get("date", ""))[:10]),
                "home_team": normalize_national_team(home.get("team", {}).get("displayName", "")),
                "away_team": normalize_national_team(away.get("team", {}).get("displayName", "")),
                "home_goals": home_goals,
                "away_goals": away_goals,
                "actual_result": _result_from_score(home_goals, away_goals),
                "result_source": "espn_scoreboard",
                "source_url": f"https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary?event={event.get('id')}",
            }
        )
    return pd.DataFrame(rows)


def _predicted_result(row: pd.Series) -> str:
    probabilities = {
        "H": float(row["adjusted_p_home"]),
        "D": float(row["adjusted_p_draw"]),
        "A": float(row["adjusted_p_away"]),
    }
    return max(probabilities, key=probabilities.get)


def _confidence(row: pd.Series) -> str:
    top = max(
        float(row["adjusted_p_home"]),
        float(row["adjusted_p_draw"]),
        float(row["adjusted_p_away"]),
    )
    if top >= 0.70:
        return "é«˜"
    if top >= 0.58:
        return "ä¸­é«˜"
    if top >= 0.48:
        return "ä¸­"
    return "ä½Ž"


def _top_probability(row: pd.Series) -> float:
    return float(
        max(
            row["adjusted_p_home"],
            row["adjusted_p_draw"],
            row["adjusted_p_away"],
        )
    )


def _lineup_status(row: pd.Series) -> str:
    if int(row.get("lineup_adjustment_active", 0) or 0) > 0:
        return "åŒæ–¹é¦–å‘ç¡®è®¤"
    if int(row.get("home_lineup_confirmed", 0) or 0) > 0 or int(row.get("away_lineup_confirmed", 0) or 0) > 0:
        return "éƒ¨åˆ†é¦–å‘ç¡®è®¤"
    return "é¦–å‘æœªå®Œå…¨ç¡®è®¤"


def _leisu_coverage(row: pd.Series) -> str:
    if int(row.get("leisu_public_match_linked", 0) or 0) <= 0:
        return "æœªåŒ¹é…é›·é€Ÿ"
    count = int(row.get("leisu_intelligence_count", 0) or 0)
    if count >= 20:
        return "é›·é€Ÿæƒ…æŠ¥è¾ƒå¤š"
    if count > 0:
        return "é›·é€Ÿæœ‰æƒ…æŠ¥"
    return "é›·é€Ÿæ— æƒ…æŠ¥æ•°"


def _total_pick_label(row: pd.Series) -> str:
    return "å¤§2.5" if bool(row["over_2_5_pick"]) else "å°2.5"


def _risk_flags(row: pd.Series) -> str:
    flags: list[str] = []
    if _top_probability(row) < 0.48:
        flags.append("èƒœå¹³è´Ÿåˆ†æ­§å¤§")
    if int(row.get("lineup_adjustment_active", 0) or 0) <= 0:
        flags.append("é¦–å‘æœªå®Œæ•´ç¡®è®¤")
    if int(row.get("leisu_public_match_linked", 0) or 0) <= 0:
        flags.append("ç¼ºå°‘å›½å†…æƒ…æŠ¥è¦†ç›–")
    expected_total = float(row["expected_home_goals"] + row["expected_away_goals"])
    if 2.2 <= expected_total <= 2.8:
        flags.append("æ€»è¿›çƒä¸´ç•Œ")
    return "ï¼›".join(flags)


def _actual_probability(row: pd.Series) -> float:
    return float(
        {
            "H": row["adjusted_p_home"],
            "D": row["adjusted_p_draw"],
            "A": row["adjusted_p_away"],
        }.get(row["actual_result"], np.nan)
    )


def _handicap_pick(row: pd.Series) -> str:
    if str(row.get("handicap_recommended_key", "") or "").strip():
        return str(row["handicap_recommended_key"])
    diff = float(row["expected_home_goals"]) - float(row["expected_away_goals"])
    if float(row["adjusted_p_home"]) >= 0.64 and diff >= 0.85:
        return "home_minus_1"
    if float(row["adjusted_p_away"]) >= 0.64 and diff <= -0.85:
        return "away_minus_1"
    return "no_bet"


def _actual_handicap_result_key(row: pd.Series) -> str:
    line = float(row.get("handicap_line", 0.0) or 0.0)
    margin = float(row["home_goals"]) + line - float(row["away_goals"])
    if margin > 1e-12:
        return "handicap_home_win"
    if margin < -1e-12:
        return "handicap_away_win"
    return "handicap_draw"


def _handicap_depth_bucket(row: pd.Series) -> str:
    if "handicap_line" not in row or pd.isna(row.get("handicap_line")):
        return "unknown"
    line = float(row.get("handicap_line", 0.0) or 0.0)
    depth = abs(line)
    if depth < 1e-12:
        return "level"
    side = "home_gives" if line < 0 else "home_receives"
    if depth < 1.5:
        return f"{side}_1"
    return f"{side}_2_plus"


def settle_enhanced_predictions(
    predictions: pd.DataFrame,
    completed_results: pd.DataFrame,
) -> pd.DataFrame:
    results = completed_results.copy()
    predictions = predictions.copy()
    if results.empty:
        out = predictions.copy()
        out["settled"] = False
        return out

    results["match_id"] = results["match_id"].map(_clean_id)
    merged = predictions.merge(
        results[
            [
                "match_id",
                "home_goals",
                "away_goals",
                "actual_result",
                "result_source",
                "source_url",
            ]
        ],
        on="match_id",
        how="left",
        validate="many_to_one",
    )
    merged["settled"] = merged["actual_result"].notna()
    merged["predicted_result"] = merged.apply(_predicted_result, axis=1)
    merged["predicted_result_zh"] = merged["predicted_result"].map(RESULT_LABELS)
    merged["actual_result_zh"] = merged["actual_result"].map(RESULT_LABELS)
    merged["confidence"] = merged.apply(_confidence, axis=1)
    merged["top_probability"] = merged.apply(_top_probability, axis=1)
    merged["lineup_status"] = merged.apply(_lineup_status, axis=1)
    merged["leisu_coverage"] = merged.apply(_leisu_coverage, axis=1)
    merged["risk_flags"] = merged.apply(_risk_flags, axis=1)
    merged["result_hit"] = merged["settled"] & merged["predicted_result"].eq(merged["actual_result"])
    merged["actual_probability"] = merged.apply(
        lambda row: _actual_probability(row) if row["settled"] else np.nan,
        axis=1,
    )
    merged["logloss"] = np.where(
        merged["settled"],
        -np.log(merged["actual_probability"].clip(lower=1e-15)),
        np.nan,
    )
    merged["brier"] = np.nan
    for index, row in merged[merged["settled"]].iterrows():
        target = np.array([row["actual_result"] == value for value in ("H", "D", "A")], dtype=float)
        probability = np.array(
            [row["adjusted_p_home"], row["adjusted_p_draw"], row["adjusted_p_away"]],
            dtype=float,
        )
        merged.loc[index, "brier"] = float(np.sum((probability - target) ** 2))

    merged["actual_score"] = np.where(
        merged["settled"],
        merged["home_goals"].astype("Int64").astype(str) + ":" + merged["away_goals"].astype("Int64").astype(str),
        "",
    )
    merged["top_score_1_hit"] = merged["settled"] & merged["top_score_1"].eq(merged["actual_score"])
    merged["top_score_2_hit"] = merged["settled"] & merged["top_score_2"].eq(merged["actual_score"])
    merged["top2_score_hit"] = merged["top_score_1_hit"] | merged["top_score_2_hit"]
    merged["actual_total_goals"] = merged["home_goals"] + merged["away_goals"]
    merged["expected_total_goals"] = merged["expected_home_goals"] + merged["expected_away_goals"]
    merged["over_2_5_pick"] = merged["over_2_5_probability"].ge(merged["under_2_5_probability"])
    merged["total_pick"] = merged.apply(_total_pick_label, axis=1)
    merged["over_2_5_actual"] = merged["actual_total_goals"].ge(3)
    merged["over_2_5_hit"] = merged["settled"] & merged["over_2_5_pick"].eq(merged["over_2_5_actual"])
    merged["handicap_pick"] = merged.apply(_handicap_pick, axis=1)
    if "handicap_recommended_result" not in merged:
        merged["handicap_recommended_result"] = merged["handicap_pick"]
    if "handicap_label" not in merged:
        merged["handicap_label"] = ""
    if "handicap_line_source" not in merged:
        merged["handicap_line_source"] = "unknown"
    merged["handicap_depth_bucket"] = merged.apply(_handicap_depth_bucket, axis=1)
    merged["handicap_hit"] = pd.Series(pd.NA, index=merged.index, dtype="boolean")
    settled = merged["settled"]
    if "handicap_line" in merged and "handicap_recommended_key" in merged:
        merged["actual_handicap_result_key"] = ""
        merged.loc[settled, "actual_handicap_result_key"] = merged[settled].apply(
            _actual_handicap_result_key,
            axis=1,
        )
        has_recommendation = settled & merged["handicap_recommended_key"].astype(str).str.strip().ne("")
        merged.loc[has_recommendation, "handicap_hit"] = merged.loc[
            has_recommendation,
            "handicap_recommended_key",
        ].eq(merged.loc[has_recommendation, "actual_handicap_result_key"])
    else:
        home_minus = settled & merged["handicap_pick"].eq("home_minus_1")
        away_minus = settled & merged["handicap_pick"].eq("away_minus_1")
        merged.loc[home_minus, "handicap_hit"] = (
            merged.loc[home_minus, "home_goals"] - merged.loc[home_minus, "away_goals"]
        ).gt(1)
        merged.loc[away_minus, "handicap_hit"] = (
            merged.loc[away_minus, "away_goals"] - merged.loc[away_minus, "home_goals"]
        ).gt(1)
    return merged


def attach_handicap_line_movement(
    settled: pd.DataFrame,
    line_movement: pd.DataFrame,
) -> pd.DataFrame:
    if line_movement.empty:
        return settled.copy()
    movement = line_movement.copy()
    movement["date"] = pd.to_datetime(movement["date"], errors="raise").dt.date.astype(str)
    movement["home_team"] = movement["home_team"].map(normalize_national_team)
    movement["away_team"] = movement["away_team"].map(normalize_national_team)
    out = settled.copy()
    out["date_key"] = pd.to_datetime(out["date"], errors="raise").dt.date.astype(str)
    out = out.merge(
        movement.drop(columns=["match_id"], errors="ignore"),
        left_on=["date_key", "home_team", "away_team"],
        right_on=["date", "home_team", "away_team"],
        how="left",
        suffixes=("", "_movement"),
    )
    return out.drop(columns=["date_key", "date_movement"], errors="ignore")


def _safe_mean(series: pd.Series) -> float | None:
    values = series.dropna()
    if values.empty:
        return None
    return float(values.mean())


def summarize_group_performance(
    settled: pd.DataFrame,
    group_column: str,
) -> pd.DataFrame:
    if group_column not in settled.columns:
        raise ValueError(f"unknown group column: {group_column}")
    completed = settled[settled["settled"]].copy()
    if completed.empty:
        return pd.DataFrame(columns=GROUP_STATS_COLUMNS)

    rows = []
    for group, data in completed.groupby(group_column, dropna=False, sort=False):
        handicap = data["handicap_hit"].astype("float") if "handicap_hit" in data else pd.Series(dtype=float)
        rows.append(
            {
                "group_type": group_column,
                "group": str(group),
                "matches": int(len(data)),
                "result_accuracy": float(data["result_hit"].mean()),
                "top_score_1_accuracy": float(data["top_score_1_hit"].mean()),
                "top2_score_accuracy": float(data["top2_score_hit"].mean()),
                "over_2_5_accuracy": float(data["over_2_5_hit"].mean()),
                "handicap_accuracy_on_recommended": _safe_mean(handicap),
                "mean_logloss": float(data["logloss"].mean()),
                "mean_brier": float(data["brier"].mean()),
                "average_actual_probability": float(data["actual_probability"].mean()),
                "average_top_probability": float(data["top_probability"].mean()),
                "actual_goals_per_match": float(data["actual_total_goals"].mean()),
                "expected_goals_per_match": float(data["expected_total_goals"].mean()),
            }
        )
    return pd.DataFrame(rows, columns=GROUP_STATS_COLUMNS)


def build_review_group_stats(settled: pd.DataFrame) -> pd.DataFrame:
    groups = [
        "confidence",
        "predicted_result_zh",
        "total_pick",
        "handicap_recommended_result",
        "handicap_label",
        "handicap_line_source",
        "handicap_depth_bucket",
        "handicap_movement_direction",
        "favorite_movement",
        "lineup_status",
        "leisu_coverage",
    ]
    frames = [
        summarize_group_performance(settled, group)
        for group in groups
        if group in settled.columns
    ]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame(columns=GROUP_STATS_COLUMNS)
    return pd.concat(frames, ignore_index=True)


def summarize_enhanced_review(settled: pd.DataFrame) -> dict[str, object]:
    completed = settled[settled["settled"]].copy()
    summary: dict[str, object] = {
        "predictions": int(len(settled)),
        "settled_matches": int(len(completed)),
        "pending_matches": int((~settled["settled"]).sum()),
    }
    if completed.empty:
        return summary
    summary.update(
        {
            "result_accuracy": float(completed["result_hit"].mean()),
            "top_score_1_accuracy": float(completed["top_score_1_hit"].mean()),
            "top2_score_accuracy": float(completed["top2_score_hit"].mean()),
            "over_2_5_accuracy": float(completed["over_2_5_hit"].mean()),
            "handicap_accuracy_on_recommended": _safe_mean(completed["handicap_hit"].astype("float")),
            "mean_logloss": float(completed["logloss"].mean()),
            "uniform_logloss": math.log(3.0),
            "mean_brier": float(completed["brier"].mean()),
            "expected_goals": float(completed["expected_total_goals"].sum()),
            "actual_goals": int(completed["actual_total_goals"].sum()),
            "goal_ratio_actual_to_expected": float(
                completed["actual_total_goals"].sum() / completed["expected_total_goals"].sum()
            ),
            "settled_with_leisu": int(
                completed.get("leisu_public_match_linked", pd.Series(0, index=completed.index))
                .fillna(0)
                .astype(int)
                .sum()
            ),
            "high_confidence_matches": int(completed["confidence"].eq("é«˜").sum()),
            "high_confidence_accuracy": _safe_mean(
                completed.loc[completed["confidence"].eq("é«˜"), "result_hit"].astype("float")
            ),
            "lineup_adjusted_matches": int(
                completed.get("lineup_adjustment_active", pd.Series(0, index=completed.index))
                .fillna(0)
                .astype(int)
                .sum()
            ),
        }
    )
    by_confidence = {}
    for confidence, group in completed.groupby("confidence", sort=False):
        by_confidence[str(confidence)] = {
            "matches": int(len(group)),
            "result_accuracy": float(group["result_hit"].mean()),
            "over_2_5_accuracy": float(group["over_2_5_hit"].mean()),
        }
    summary["by_confidence"] = by_confidence
    group_stats = build_review_group_stats(settled)
    if not group_stats.empty:
        summary["best_groups_by_result_accuracy"] = (
            group_stats.sort_values(["result_accuracy", "matches"], ascending=[False, False])
            .head(5)
            .to_dict(orient="records")
        )
        summary["weak_groups_by_logloss"] = (
            group_stats.sort_values(["mean_logloss", "matches"], ascending=[False, False])
            .head(5)
            .to_dict(orient="records")
        )
    return summary


def _movement_text(row: object) -> str:
    direction = str(getattr(row, "handicap_movement_direction", "") or "")
    favorite = str(getattr(row, "favorite_movement", "") or "")
    if not direction and not favorite:
        return ""
    opening = getattr(row, "opening_home_handicap", "")
    latest = getattr(row, "latest_home_handicap", "")
    try:
        opening_text = f"{float(opening):g}"
        latest_text = f"{float(latest):g}"
    except (TypeError, ValueError):
        opening_text = str(opening or "")
        latest_text = str(latest or "")
    parts = []
    if opening_text or latest_text:
        parts.append(f"{opening_text}->{latest_text}")
    if direction:
        parts.append(direction)
    if favorite:
        parts.append(favorite)
    return " / ".join(parts)


def build_chinese_review_report(settled: pd.DataFrame, summary: dict[str, object]) -> str:
    completed = settled[settled["settled"]].copy()
    lines = [
        "# ä¸–ç•Œæ¯é¢„æµ‹èµ›åŽå¤ç›˜",
        "",
        "## æ ¸å¿ƒæŒ‡æ ‡",
        "",
        f"- é¢„æµ‹åœºæ¬¡ï¼š{summary['predictions']}",
        f"- å·²ç»“ç®—ï¼š{summary['settled_matches']}",
        f"- å¾…ç»“ç®—ï¼š{summary['pending_matches']}",
    ]
    if completed.empty:
        lines.append("- å½“å‰è¿˜æ²¡æœ‰å¯å¤ç›˜çš„å·²å®Œèµ›æ¯”èµ›ã€‚")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            f"- èƒœå¹³è´Ÿå‘½ä¸­çŽ‡ï¼š{summary['result_accuracy']:.1%}",
            f"- ç¬¬ä¸€æ¯”åˆ†å‘½ä¸­çŽ‡ï¼š{summary['top_score_1_accuracy']:.1%}",
            f"- å‰ä¸¤æ¯”åˆ†å‘½ä¸­çŽ‡ï¼š{summary['top2_score_accuracy']:.1%}",
            f"- å¤§å° 2.5 å‘½ä¸­çŽ‡ï¼š{summary['over_2_5_accuracy']:.1%}",
            f"- é«˜ä¿¡å¿ƒåœºæ¬¡ï¼š{summary['high_confidence_matches']}ï¼Œå‘½ä¸­çŽ‡ï¼š"
            f"{summary['high_confidence_accuracy']:.1%}"
            if summary.get("high_confidence_accuracy") is not None
            else f"- é«˜ä¿¡å¿ƒåœºæ¬¡ï¼š{summary['high_confidence_matches']}ï¼Œå‘½ä¸­çŽ‡ï¼šæš‚æ— ",
            f"- Log Lossï¼š{summary['mean_logloss']:.4f}ï¼ˆå‡åŒ€åŸºçº¿ {summary['uniform_logloss']:.4f}ï¼‰",
            f"- å®žé™…/é¢„æœŸè¿›çƒæ¯”ï¼š{summary['goal_ratio_actual_to_expected']:.2f}",
            "",
            "## å·²ç»“ç®—æ¯”èµ›",
            "",
            "| æ—¥æœŸ | æ¯”èµ› | é¢„æµ‹ | å®žé™… | èƒœå¹³è´Ÿ | æ¯”åˆ†1 | æ¯”åˆ†å‰2 | å¤§å°çƒ | è®©çƒç›˜ | è®©çƒæŽ¨è | è®©çƒ | é›·é€Ÿæƒ…æŠ¥ |",
            "| --- | --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- | ---: |",
        ]
    )
    for row in completed.itertuples(index=False):
        leisu_count = getattr(row, "leisu_intelligence_count", 0)
        leisu_text = "" if pd.isna(leisu_count) else str(int(leisu_count))
        handicap_hit = getattr(row, "handicap_hit", pd.NA)
        handicap_text = "æš‚æ— " if pd.isna(handicap_hit) else "å‘½ä¸­" if bool(handicap_hit) else "æœªä¸­"
        lines.append(
            f"| {pd.Timestamp(row.date).date()} | {row.home_team} vs {row.away_team} | "
            f"{row.predicted_result_zh} | {row.actual_score} | "
            f"{'å‘½ä¸­' if row.result_hit else 'æœªä¸­'} | "
            f"{'å‘½ä¸­' if row.top_score_1_hit else 'æœªä¸­'} | "
            f"{'å‘½ä¸­' if row.top2_score_hit else 'æœªä¸­'} | "
            f"{'å‘½ä¸­' if row.over_2_5_hit else 'æœªä¸­'} | "
            f"{getattr(row, 'handicap_label', '')} | "
            f"{getattr(row, 'handicap_recommended_result', '')} | "
            f"{handicap_text} | {leisu_text} |"
        )
    movement_rows = [
        row for row in completed.itertuples(index=False) if _movement_text(row)
    ]
    if movement_rows:
        lines.extend(
            [
                "",
                "## 体彩盘口变化",
                "",
                "| 日期 | 比赛 | 初盘->最新盘 | 方向 | 加深/变浅 |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for row in movement_rows:
            lines.append(
                f"| {pd.Timestamp(row.date).date()} | {row.home_team} vs {row.away_team} | "
                f"{getattr(row, 'opening_home_handicap', '')}->{getattr(row, 'latest_home_handicap', '')} | "
                f"{getattr(row, 'handicap_movement_direction', '')} | "
                f"{getattr(row, 'favorite_movement', '')} |"
            )

    group_stats = build_review_group_stats(settled)
    if not group_stats.empty:
        lines.extend(
            [
                "",
                "## åˆ†ç»„è¡¨çŽ°",
                "",
                "| åˆ†ç»„ç±»åž‹ | åˆ†ç»„ | åœºæ¬¡ | èƒœå¹³è´Ÿå‘½ä¸­ | æ¯”åˆ†å‰2 | å¤§å°çƒ | Log Loss |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in group_stats.itertuples(index=False):
            lines.append(
                f"| {row.group_type} | {row.group} | {row.matches} | "
                f"{row.result_accuracy:.1%} | {row.top2_score_accuracy:.1%} | "
                f"{row.over_2_5_accuracy:.1%} | {row.mean_logloss:.4f} |"
            )
    return "\n".join(lines) + "\n"
