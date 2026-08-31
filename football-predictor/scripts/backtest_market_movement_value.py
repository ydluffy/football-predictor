from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from research_inner_outer_market_patterns import normalize_team
from world_cup.sporttery_markets import build_sporttery_line_movement_features


def parse_score(score: object) -> tuple[int, int] | None:
    parts = re.findall(r"\d+", str(score or ""))
    if len(parts) < 2:
        return None
    return int(parts[0]), int(parts[1])


def spf_actual(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "home"
    if home_goals < away_goals:
        return "away"
    return "draw"


def rqspf_cover_result(home_goals: int, away_goals: int, home_handicap: float) -> str:
    adjusted_home = home_goals + home_handicap
    if adjusted_home > away_goals:
        return "home_cover"
    if adjusted_home < away_goals:
        return "away_cover"
    return "push"


def favorite_side_from_home_line(home_handicap: float | None) -> str:
    if home_handicap is None:
        return ""
    if home_handicap < 0:
        return "home"
    if home_handicap > 0:
        return "away"
    return ""


def favorite_cover_from_result(result: str, favorite_side: str) -> str:
    if not result or not favorite_side:
        return ""
    if result == "push":
        return "push"
    if favorite_side == "home":
        return "cover" if result == "home_cover" else "fail"
    if favorite_side == "away":
        return "cover" if result == "away_cover" else "fail"
    return ""


def load_results(paths: list[Path]) -> pd.DataFrame:
    frames = []
    for path in paths:
        if not path.exists():
            continue
        frame = pd.read_csv(path).fillna("")
        frame["result_source"] = str(path)
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    results = pd.concat(frames, ignore_index=True, sort=False)
    if "full_time_score" not in results.columns:
        return pd.DataFrame()
    results["score_pair"] = results["full_time_score"].map(parse_score)
    results = results[results["score_pair"].notna()].copy()
    if results.empty:
        return results
    results["date"] = pd.to_datetime(results["date"], errors="coerce").dt.date.astype(str)
    results["home_key"] = results["home_team"].map(normalize_team)
    results["away_key"] = results["away_team"].map(normalize_team)
    results["home_goals"] = results["score_pair"].map(lambda item: item[0])
    results["away_goals"] = results["score_pair"].map(lambda item: item[1])
    results["actual_spf"] = [spf_actual(h, a) for h, a in zip(results["home_goals"], results["away_goals"])]
    results["actual_total_goals"] = results["home_goals"] + results["away_goals"]
    sort_cols = [col for col in ["date", "match_number", "home_key", "away_key", "result_source"] if col in results.columns]
    return results.sort_values(sort_cols).drop_duplicates(["date", "home_key", "away_key"], keep="last")


def build_external_movement(history: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame()
    frame = history.copy().fillna("")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.date.astype(str)
    frame["captured_at_sort"] = pd.to_datetime(frame["captured_at"], errors="coerce", utc=True)
    frame["home_key"] = frame["home_team"].map(normalize_team)
    frame["away_key"] = frame["away_team"].map(normalize_team)
    rows: list[dict[str, Any]] = []
    for key, group in frame.sort_values("captured_at_sort").groupby(["date", "home_key", "away_key"], dropna=False):
        first = group.iloc[0]
        latest = group.iloc[-1]
        opening_prob = pd.to_numeric(pd.Series([first.get("external_h2h_favorite_probability", "")]), errors="coerce").iloc[0]
        latest_prob = pd.to_numeric(pd.Series([latest.get("external_h2h_favorite_probability", "")]), errors="coerce").iloc[0]
        opening_line = pd.to_numeric(pd.Series([first.get("external_home_spread_point", "")]), errors="coerce").iloc[0]
        latest_line = pd.to_numeric(pd.Series([latest.get("external_home_spread_point", "")]), errors="coerce").iloc[0]
        prob_delta = None if pd.isna(opening_prob) or pd.isna(latest_prob) else float(latest_prob - opening_prob)
        line_delta = None if pd.isna(opening_line) or pd.isna(latest_line) else float(latest_line - opening_line)
        rows.append(
            {
                "date": key[0],
                "home_key": key[1],
                "away_key": key[2],
                "external_home_team": latest.get("home_team", ""),
                "external_away_team": latest.get("away_team", ""),
                "external_opening_favorite": first.get("external_h2h_favorite", ""),
                "external_latest_favorite": latest.get("external_h2h_favorite", ""),
                "external_opening_favorite_probability": opening_prob,
                "external_latest_favorite_probability": latest_prob,
                "external_favorite_probability_delta": prob_delta,
                "external_opening_home_spread_point": opening_line,
                "external_latest_home_spread_point": latest_line,
                "external_home_spread_point_delta": line_delta,
                "external_opening_total_point": first.get("external_total_point", ""),
                "external_latest_total_point": latest.get("external_total_point", ""),
                "external_snapshot_count": int(len(group)),
                "external_opening_captured_at": first.get("captured_at", ""),
                "external_latest_captured_at": latest.get("captured_at", ""),
            }
        )
    return pd.DataFrame(rows)


def build_dataset(
    sporttery_history: pd.DataFrame,
    external_history: pd.DataFrame,
    results: pd.DataFrame,
) -> pd.DataFrame:
    sporttery_movement = build_sporttery_line_movement_features(sporttery_history)
    if not sporttery_movement.empty:
        sporttery_movement["home_key"] = sporttery_movement["home_team"].map(normalize_team)
        sporttery_movement["away_key"] = sporttery_movement["away_team"].map(normalize_team)
    external_movement = build_external_movement(external_history)

    dataset = results.copy()
    if not sporttery_movement.empty:
        dataset = dataset.merge(
            sporttery_movement,
            on=["date", "home_key", "away_key"],
            how="left",
            suffixes=("", "_sporttery_movement"),
        )
    if not external_movement.empty:
        dataset = dataset.merge(
            external_movement,
            on=["date", "home_key", "away_key"],
            how="left",
        )
    rows = []
    for _, row in dataset.iterrows():
        latest_line = pd.to_numeric(pd.Series([row.get("latest_home_handicap", "")]), errors="coerce").iloc[0]
        sporttery_fav = favorite_side_from_home_line(None if pd.isna(latest_line) else float(latest_line))
        sporttery_cover = ""
        if not pd.isna(latest_line):
            settle = rqspf_cover_result(int(row["home_goals"]), int(row["away_goals"]), float(latest_line))
            sporttery_cover = favorite_cover_from_result(settle, sporttery_fav)
        raw_ext_fav = row.get("external_latest_favorite", "")
        ext_fav = "" if pd.isna(raw_ext_fav) else str(raw_ext_fav or "")
        ext_fav_hit = int(ext_fav == row["actual_spf"]) if ext_fav in {"home", "away", "draw"} else ""
        raw_latest_line = row.get("latest_home_handicap", "")
        has_sporttery = int(not pd.isna(raw_latest_line) and str(raw_latest_line) != "")
        rows.append(
            {
                "sporttery_latest_favorite": sporttery_fav,
                "sporttery_favorite_cover": sporttery_cover,
                "external_latest_favorite_hit": ext_fav_hit,
                "has_sporttery_movement": has_sporttery,
                "has_external_movement": int(ext_fav != ""),
            }
        )
    return pd.concat([dataset.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def summarize(dataset: pd.DataFrame) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "rows": int(len(dataset)),
        "sporttery_coverage": int(dataset["has_sporttery_movement"].sum()) if "has_sporttery_movement" in dataset else 0,
        "external_coverage": int(dataset["has_external_movement"].sum()) if "has_external_movement" in dataset else 0,
    }
    if metrics["sporttery_coverage"]:
        covered = dataset[dataset["has_sporttery_movement"].eq(1)]
        metrics["sporttery_favorite_cover_counts"] = covered["sporttery_favorite_cover"].value_counts().to_dict()
        metrics["sporttery_favorite_movement_counts"] = covered.get("favorite_movement", pd.Series(dtype=str)).value_counts().to_dict()
    if metrics["external_coverage"]:
        external = dataset[dataset["has_external_movement"].eq(1)]
        hit = pd.to_numeric(external["external_latest_favorite_hit"], errors="coerce").dropna()
        metrics["external_latest_favorite_hit_rate"] = float(hit.mean()) if not hit.empty else None
        metrics["external_snapshot_count_distribution"] = external["external_snapshot_count"].value_counts().to_dict()
    return metrics


def render_report(dataset: pd.DataFrame, metrics: dict[str, Any]) -> str:
    lines = [
        "# 盘口时间序列与预测价值回测",
        "",
        "## 本次完成内容",
        "",
        "- 将体彩内盘快照历史整理为盘口变化特征。",
        "- 将 The Odds API 外盘快照归档为可追加历史，并抽取外盘热门、亚洲盘、大小球字段。",
        "- 将盘口时间序列与官方 90 分钟赛果合并，验证盘口变化是否能作为预测信号。",
        "",
        "## 覆盖率",
        "",
        f"- 已完场赛果样本：{metrics.get('rows', 0)} 场",
        f"- 匹配到体彩盘口变化：{metrics.get('sporttery_coverage', 0)} 场",
        f"- 匹配到外盘快照历史：{metrics.get('external_coverage', 0)} 场",
        "",
        "## 当前结论",
        "",
    ]
    if metrics.get("sporttery_coverage", 0):
        lines.append(f"- 体彩热门让球结果分布：{metrics.get('sporttery_favorite_cover_counts', {})}")
        lines.append(f"- 体彩盘口深浅变化分布：{metrics.get('sporttery_favorite_movement_counts', {})}")
    else:
        lines.append("- 体彩盘口变化样本不足，暂不能验证盘口升降与赛果的关系。")
    if metrics.get("external_coverage", 0):
        rate = metrics.get("external_latest_favorite_hit_rate")
        rate_text = "NA" if rate is None else f"{rate:.1%}"
        lines.append(f"- 外盘最新热门 SPF 命中率：{rate_text}")
        lines.append(f"- 外盘快照数量分布：{metrics.get('external_snapshot_count_distribution', {})}")
    else:
        lines.append("- 外盘历史快照覆盖不足，目前只能作为赛前解释层，不能证明长期有效。")
    lines.extend(
        [
            "",
            "## 后续使用规则",
            "",
            "1. 每次抓取外盘后先归档，禁止只覆盖最新 `odds.csv`。",
            "2. 每次抓取体彩后继续追加 `sporttery_handicap_market_history.csv`。",
            "3. 每场赛后只用官方 90 分钟赛果回测，未完场不得误判为未中。",
            "4. 当某个盘口变化桶样本少于 30 场时，只标记为观察信号，不作为强规则。",
            "5. 后续每日预测中，把盘口变化拆成四类信号：方向一致、热门变热、让球变深、大小球变动。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sporttery-history", default="data/manual/sporttery_handicap_market_history.csv")
    parser.add_argument("--external-history", default="data/manual/external_market_snapshot_history.csv")
    parser.add_argument("--results-glob", default="data/external/sporttery_results/*.csv")
    parser.add_argument("--dataset-output", default="data/manual/market_movement_backtest_dataset.csv")
    parser.add_argument("--metrics-output", default="artifacts/data/market_movement_backtest.json")
    parser.add_argument("--report-output", default="artifacts/reviews/market_movement_backtest.md")
    args = parser.parse_args()

    sporttery_history = pd.read_csv(ROOT / args.sporttery_history).fillna("") if (ROOT / args.sporttery_history).exists() else pd.DataFrame()
    external_history = pd.read_csv(ROOT / args.external_history).fillna("") if (ROOT / args.external_history).exists() else pd.DataFrame()
    results = load_results(sorted(ROOT.glob(args.results_glob)))
    dataset = build_dataset(sporttery_history, external_history, results)
    metrics = summarize(dataset)

    dataset_output = ROOT / args.dataset_output
    metrics_output = ROOT / args.metrics_output
    report_output = ROOT / args.report_output
    dataset_output.parent.mkdir(parents=True, exist_ok=True)
    metrics_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(dataset_output, index=False, encoding="utf-8-sig")
    metrics_output.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    report_output.write_text(render_report(dataset, metrics), encoding="utf-8")
    print(json.dumps({"ok": True, "dataset": str(dataset_output), "metrics": str(metrics_output), "report": str(report_output), **metrics}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
