from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd


TEAM_ALIASES = {
    "阿根廷": "argentina",
    "英格兰": "england",
    "法国": "france",
    "西班牙": "spain",
    "瑞士": "switzerland",
    "哥伦比亚": "colombia",
    "挪威": "norway",
    "美国": "usa",
    "比利时": "belgium",
    "葡萄牙": "portugal",
    "巴西": "brazil",
    "摩洛哥": "morocco",
    "埃及": "egypt",
}


def normalize_team(value: object) -> str:
    text = str(value or "").strip()
    if text in TEAM_ALIASES:
        return TEAM_ALIASES[text]
    text = text.lower()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text)
    return TEAM_ALIASES.get(text, text)


def to_float(value: object, default: float | None = None) -> float | None:
    try:
        if value == "":
            return default
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if pd.isna(parsed):
        return default
    return parsed


def parse_score(score: object) -> tuple[int, int] | None:
    parts = re.findall(r"\d+", str(score or ""))
    if len(parts) < 2:
        return None
    return int(parts[0]), int(parts[1])


def line_label(point: float | None) -> str:
    if point is None:
        return "unknown"
    point = abs(float(point))
    labels = {
        0.0: "平手",
        0.25: "平手/半球",
        0.5: "半球",
        0.75: "半球/一球",
        1.0: "一球",
        1.25: "一球/球半",
        1.5: "球半",
        1.75: "球半/两球",
        2.0: "两球",
        2.25: "两球/两球半",
        2.5: "两球半",
    }
    nearest = min(labels, key=lambda key: abs(key - point))
    if abs(nearest - point) <= 0.01:
        return labels[nearest]
    if point < 0.25:
        return "平手附近"
    if point < 0.75:
        return "浅盘"
    if point < 1.25:
        return "一球附近"
    if point < 1.75:
        return "球半附近"
    return "深盘"


def line_bucket(point: float | None) -> str:
    if point is None:
        return "unknown"
    point = abs(float(point))
    if point <= 0.25:
        return "pk_to_quarter"
    if point <= 0.75:
        return "shallow_half"
    if point <= 1.25:
        return "one_goal"
    if point <= 1.75:
        return "one_and_half"
    return "deep"


def h2h_result(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "home"
    if home_goals < away_goals:
        return "away"
    return "draw"


def spread_result(home_goals: int, away_goals: int, home_point: float) -> str:
    adjusted = home_goals + home_point
    if adjusted > away_goals:
        return "home_cover"
    if adjusted < away_goals:
        return "away_cover"
    return "push"


def total_result(total_goals: int, point: float) -> str:
    if total_goals > point:
        return "over"
    if total_goals < point:
        return "under"
    return "push"


def implied_probs(odds: dict[str, float | None]) -> dict[str, float | None]:
    inv = {key: (1.0 / value if value and value > 0 else None) for key, value in odds.items()}
    denom = sum(value for value in inv.values() if value is not None)
    if denom <= 0:
        return {key: None for key in odds}
    return {key: (value / denom if value is not None else None) for key, value in inv.items()}


def side_name(side: str, home: str, away: str) -> str:
    if side == "home":
        return home
    if side == "away":
        return away
    if side == "draw":
        return "draw"
    return ""


@dataclass
class MarketSummary:
    rows: pd.DataFrame
    metrics: dict[str, Any]


def build_external_features(odds: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    grouped = odds.groupby(["event_id", "date", "commence_time", "home_team", "away_team"], dropna=False)

    for (event_id, date, commence_time, home, away), group in grouped:
        h2h = group[group["market_key"].eq("h2h")]
        h2h_avg: dict[str, float | None] = {}
        for label in ("home", "draw", "away"):
            prices = pd.to_numeric(h2h[h2h["outcome_label"].eq(label)]["price"], errors="coerce").dropna()
            h2h_avg[label] = float(prices.mean()) if not prices.empty else None
        h2h_probs = implied_probs(h2h_avg)
        h2h_available = {key: value for key, value in h2h_probs.items() if value is not None}
        h2h_favorite = max(h2h_available, key=h2h_available.get) if h2h_available else ""

        spreads = group[group["market_key"].eq("spreads")].copy()
        spread_choice: dict[str, Any] = {}
        if not spreads.empty:
            spreads["point_num"] = pd.to_numeric(spreads["point"], errors="coerce")
            pair_rows = []
            for bookmaker, book in spreads.groupby("bookmaker_key"):
                home_rows = book[book["outcome_label"].eq("home_spread")]
                away_rows = book[book["outcome_label"].eq("away_spread")]
                if home_rows.empty or away_rows.empty:
                    continue
                for _, home_row in home_rows.iterrows():
                    away_match = away_rows[
                        (away_rows["point_num"] + float(home_row["point_num"])).abs().le(0.01)
                    ]
                    if away_match.empty:
                        continue
                    away_row = away_match.iloc[0]
                    pair_rows.append(
                        {
                            "bookmaker": bookmaker,
                            "home_point": float(home_row["point_num"]),
                            "away_point": float(away_row["point_num"]),
                            "home_odds": to_float(home_row.get("price")),
                            "away_odds": to_float(away_row.get("price")),
                        }
                    )
            if pair_rows:
                pairs = pd.DataFrame(pair_rows)
                counts = pairs.groupby("home_point").size().sort_values(ascending=False)
                best_point = float(counts.index[0])
                selected = pairs[pairs["home_point"].eq(best_point)]
                home_avg = float(selected["home_odds"].mean())
                away_avg = float(selected["away_odds"].mean())
                if abs(best_point) <= 0.01:
                    spread_favorite = "home" if home_avg < away_avg else "away"
                else:
                    spread_favorite = "home" if best_point < 0 else "away"
                spread_choice = {
                    "external_home_spread_point": best_point,
                    "external_line_label": line_label(best_point),
                    "external_line_bucket": line_bucket(best_point),
                    "external_spread_favorite": spread_favorite,
                    "external_spread_bookmaker_count": int(len(selected)),
                    "external_home_spread_avg_odds": home_avg,
                    "external_away_spread_avg_odds": away_avg,
                }

        totals = group[group["market_key"].eq("totals")].copy()
        total_choice: dict[str, Any] = {}
        if not totals.empty:
            totals["point_num"] = pd.to_numeric(totals["point"], errors="coerce")
            point_counts = totals.groupby("point_num")["bookmaker_key"].nunique().sort_values(ascending=False)
            if not point_counts.empty:
                best_total = min(point_counts.index, key=lambda point: (abs(float(point) - 2.5), -point_counts.loc[point]))
                total_rows = totals[totals["point_num"].eq(best_total)]
                over = pd.to_numeric(total_rows[total_rows["outcome_label"].eq("over")]["price"], errors="coerce").dropna()
                under = pd.to_numeric(total_rows[total_rows["outcome_label"].eq("under")]["price"], errors="coerce").dropna()
                over_avg = float(over.mean()) if not over.empty else None
                under_avg = float(under.mean()) if not under.empty else None
                total_choice = {
                    "external_total_point": float(best_total),
                    "external_total_bookmaker_count": int(point_counts.loc[best_total]),
                    "external_over_avg_odds": over_avg,
                    "external_under_avg_odds": under_avg,
                    "external_total_signal": (
                        "over" if over_avg is not None and under_avg is not None and over_avg < under_avg else
                        "under" if over_avg is not None and under_avg is not None else ""
                    ),
                }

        rows.append(
            {
                "event_id": event_id,
                "date": local_match_date(commence_time) or date,
                "utc_date": date,
                "commence_time": commence_time,
                "home_team": home,
                "away_team": away,
                "home_key": normalize_team(home),
                "away_key": normalize_team(away),
                "external_h2h_home_avg_odds": h2h_avg["home"],
                "external_h2h_draw_avg_odds": h2h_avg["draw"],
                "external_h2h_away_avg_odds": h2h_avg["away"],
                "external_h2h_home_probability": h2h_probs["home"],
                "external_h2h_draw_probability": h2h_probs["draw"],
                "external_h2h_away_probability": h2h_probs["away"],
                "external_h2h_favorite": h2h_favorite,
                "external_h2h_favorite_probability": h2h_available.get(h2h_favorite),
                "external_h2h_bookmaker_count": int(h2h["bookmaker_key"].nunique()) if not h2h.empty else 0,
                **spread_choice,
                **total_choice,
            }
        )
    return pd.DataFrame(rows)


def local_match_date(commence_time: object) -> str:
    parsed = pd.to_datetime(commence_time, utc=True, errors="coerce")
    if pd.isna(parsed):
        return ""
    return str((parsed + timedelta(hours=8)).date())


def latest_sporttery_market(files: list[Path]) -> pd.DataFrame:
    frames = []
    for path in files:
        try:
            frame = pd.read_csv(path)
        except Exception:
            continue
        frame["snapshot_file"] = path.name
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    markets = pd.concat(frames, ignore_index=True)
    for column in ("home_team", "away_team"):
        markets[f"{column.split('_')[0]}_key"] = markets[column].map(normalize_team)
    markets["date"] = markets["date"].astype(str)
    markets = markets.sort_values(["date", "match_number", "snapshot_file"])
    return markets.drop_duplicates(["date", "home_key", "away_key"], keep="last")


def build_research_dataset(results: pd.DataFrame, external: pd.DataFrame, sporttery: pd.DataFrame) -> MarketSummary:
    result_rows = results.copy()
    result_rows["home_key"] = result_rows["home_team"].map(normalize_team)
    result_rows["away_key"] = result_rows["away_team"].map(normalize_team)
    result_rows["date"] = result_rows["date"].astype(str)

    merged = result_rows.merge(
        external,
        on=["date", "home_key", "away_key"],
        how="left",
        suffixes=("", "_external"),
    )
    if not sporttery.empty:
        keep_cols = [
            "date",
            "home_key",
            "away_key",
            "home_handicap",
            "spf_odds_home",
            "spf_odds_draw",
            "spf_odds_away",
            "rqspf_odds_home",
            "rqspf_odds_draw",
            "rqspf_odds_away",
            "snapshot_file",
        ]
        available = [col for col in keep_cols if col in sporttery.columns]
        merged = merged.merge(
            sporttery[available],
            on=["date", "home_key", "away_key"],
            how="left",
            suffixes=("", "_sporttery_market"),
        )

    derived = []
    for _, row in merged.iterrows():
        score = parse_score(row.get("full_time_score"))
        if score is None:
            derived.append({})
            continue
        home_goals, away_goals = score
        actual = h2h_result(home_goals, away_goals)
        total_goals = home_goals + away_goals
        home_point = to_float(row.get("external_home_spread_point"))
        total_point = to_float(row.get("external_total_point"))
        ext_fav = str(row.get("external_h2h_favorite") or "")
        spread_fav = str(row.get("external_spread_favorite") or "")
        spread_settle = spread_result(home_goals, away_goals, home_point) if home_point is not None else ""
        total_settle = total_result(total_goals, total_point) if total_point is not None else ""
        favorite_cover = ""
        if spread_settle:
            if spread_fav == "home":
                favorite_cover = "cover" if spread_settle == "home_cover" else "push" if spread_settle == "push" else "fail"
            elif spread_fav == "away":
                favorite_cover = "cover" if spread_settle == "away_cover" else "push" if spread_settle == "push" else "fail"
        sporttery_handicap = to_float(row.get("home_handicap_sporttery_market"))
        if sporttery_handicap is None:
            sporttery_handicap = to_float(row.get("home_handicap"))
        sporttery_gap = None
        if home_point is not None and sporttery_handicap is not None:
            sporttery_gap = home_point - sporttery_handicap
        derived.append(
            {
                "actual_1x2": actual,
                "actual_margin": home_goals - away_goals,
                "actual_total_goals": total_goals,
                "external_h2h_favorite_hit": int(ext_fav == actual) if ext_fav in {"home", "away", "draw"} else "",
                "external_spread_result": spread_settle,
                "external_spread_favorite_cover": favorite_cover,
                "external_total_result": total_settle,
                "external_total_signal_hit": (
                    int(str(row.get("external_total_signal") or "") == total_settle)
                    if str(row.get("external_total_signal") or "") in {"over", "under"} and total_settle in {"over", "under"}
                    else ""
                ),
                "sporttery_vs_external_home_line_gap": sporttery_gap,
                "sporttery_external_line_relation": line_relation(sporttery_handicap, home_point),
            }
        )
    enriched = pd.concat([merged.reset_index(drop=True), pd.DataFrame(derived)], axis=1)
    metrics = summarize(enriched)
    return MarketSummary(rows=enriched, metrics=metrics)


def line_relation(sporttery_home_line: float | None, external_home_line: float | None) -> str:
    if sporttery_home_line is None or external_home_line is None:
        return ""
    diff = external_home_line - sporttery_home_line
    if abs(diff) <= 0.25:
        return "aligned"
    if diff < -0.25:
        return "external_more_home_favored"
    return "sporttery_more_home_favored"


def summarize(frame: pd.DataFrame) -> dict[str, Any]:
    joined = frame[frame["external_h2h_favorite"].notna()].copy()
    metrics: dict[str, Any] = {
        "result_rows": int(len(frame)),
        "external_joined_rows": int(len(joined)),
    }
    if joined.empty:
        return metrics
    hit = pd.to_numeric(joined["external_h2h_favorite_hit"], errors="coerce").dropna()
    cover = joined["external_spread_favorite_cover"].dropna()
    total_hit = pd.to_numeric(joined["external_total_signal_hit"], errors="coerce").dropna()
    metrics["external_h2h_favorite_hit_rate"] = float(hit.mean()) if not hit.empty else None
    metrics["external_total_signal_hit_rate"] = float(total_hit.mean()) if not total_hit.empty else None
    metrics["external_spread_favorite_cover_counts"] = cover.value_counts().to_dict()
    metrics["line_bucket_counts"] = joined["external_line_bucket"].value_counts(dropna=False).to_dict()
    metrics["joined_matches"] = [
        {
            "date": row["date"],
            "match": f"{row['home_team']} vs {row['away_team']}",
            "score": row["full_time_score"],
            "external_favorite": side_name(str(row.get("external_h2h_favorite") or ""), row["home_team"], row["away_team"]),
            "external_line": row.get("external_line_label", ""),
            "spread_cover": row.get("external_spread_favorite_cover", ""),
            "total_signal": row.get("external_total_signal", ""),
            "total_result": row.get("external_total_result", ""),
            "line_relation": row.get("sporttery_external_line_relation", ""),
        }
        for _, row in joined.iterrows()
    ]
    return metrics


def fmt_pct(value: Any) -> str:
    if value is None or value == "":
        return "NA"
    return f"{float(value):.1%}"


def render_report(summary: MarketSummary) -> str:
    rows = summary.rows
    metrics = summary.metrics
    joined = rows[rows["external_h2h_favorite"].notna()].copy()
    lines = [
        "# 内外盘差异与赛果验证研究",
        "",
        "## 这次补强了什么",
        "",
        "这份研究不再只看历史比分分布，而是把外盘 h2h、亚洲让球/让分、大小球，与体彩官方 90 分钟赛果、体彩让球线放到同一张表里验证。",
        "",
        "盘口不是比赛原因，但它是机构定价、资金风险和市场预期的压缩表达。我们后续预测要把它当成独立信号层：方向、让球深度、大小球环境、内外盘分歧分别建模。",
        "",
        "## 当前样本",
        "",
        f"- 赛果样本：{metrics.get('result_rows', 0)} 场",
        f"- 成功匹配外盘样本：{metrics.get('external_joined_rows', 0)} 场",
        f"- 外盘胜平负热门命中率：{fmt_pct(metrics.get('external_h2h_favorite_hit_rate'))}",
        f"- 外盘大小球方向命中率：{fmt_pct(metrics.get('external_total_signal_hit_rate'))}",
        f"- 外盘热门让球结果：{metrics.get('external_spread_favorite_cover_counts', {})}",
        f"- 外盘盘口深度分布：{metrics.get('line_bucket_counts', {})}",
        "",
        "## 已验证比赛",
        "",
    ]
    for _, row in joined.iterrows():
        fav = side_name(str(row.get("external_h2h_favorite") or ""), row["home_team"], row["away_team"])
        spread_fav = side_name(str(row.get("external_spread_favorite") or ""), row["home_team"], row["away_team"])
        relation = row.get("sporttery_external_line_relation", "") or "缺少内盘对照"
        lines.extend(
            [
                f"### {row['date']} {row['home_team']} vs {row['away_team']}，90分钟 {row['full_time_score']}",
                "",
                f"- 外盘胜平负：热门 {fav}，概率 {fmt_pct(row.get('external_h2h_favorite_probability'))}，结果 {'命中' if row.get('external_h2h_favorite_hit') == 1 else '未命中'}",
                f"- 外盘让球：{spread_fav}，主队盘口 {row.get('external_home_spread_point', '')}，盘口标签 {row.get('external_line_label', '')}，热门让球结果 {row.get('external_spread_favorite_cover', '')}",
                f"- 外盘大小球：盘口 {row.get('external_total_point', '')}，市场偏 {row.get('external_total_signal', '')}，实际 {row.get('actual_total_goals', '')} 球，结果 {row.get('external_total_result', '')}",
                f"- 体彩 vs 外盘让球：{relation}",
                "",
            ]
        )
    lines.extend(
        [
            "## 对以后预测的具体用法",
            "",
            "1. 先判方向：模型、体彩胜平负、外盘 h2h 三者一致，方向可信度上调；三者冲突，不能当稳胆。",
            "2. 再判让球：热门赢球不等于打穿。外盘只给平手/浅盘时，强队方向即使对，也要防平、让负或一球小胜。",
            "3. 再判大小球：深盘如果没有大球支持，优先防“赢但不穿”；深盘且大球低赔，才更支持 2 球以上差距。",
            "4. 看内外盘差异：体彩比外盘更深，说明内盘对主队更激进，需要防热；外盘更深，说明国际市场对主队更强，要看是否有阵容/伤停信息支撑。",
            "5. 投注方案层面：方向票、让球防冷票、比分票、总进球票不能混成一个逻辑，要围绕同一个比赛剧本拆开评估成本覆盖。",
            "",
            "## 当前限制",
            "",
            "当前外盘样本还偏少，更多是近期世界杯关键场快照。它已经能用于赛前分析，但还不足以证明长期盈利。下一步必须持续保存初盘、赛前12小时、赛前2小时、临场四类快照，才能验证升盘/降盘/水位变化的真实价值。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--odds", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--sporttery-market-glob", default="data/manual/sporttery_handicap_markets_*.csv")
    parser.add_argument("--output", required=True)
    parser.add_argument("--report-output", required=True)
    parser.add_argument("--metrics-output", required=True)
    args = parser.parse_args()

    odds = pd.read_csv(args.odds)
    results = pd.read_csv(args.results)
    external = build_external_features(odds)
    sporttery_files = sorted(Path().glob(args.sporttery_market_glob))
    sporttery = latest_sporttery_market(sporttery_files)
    summary = build_research_dataset(results, external, sporttery)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    summary.rows.to_csv(output, index=False, encoding="utf-8-sig")

    report_output = Path(args.report_output)
    report_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.write_text(render_report(summary), encoding="utf-8")

    metrics_output = Path(args.metrics_output)
    metrics_output.parent.mkdir(parents=True, exist_ok=True)
    metrics_output.write_text(json.dumps(summary.metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote dataset: {output}")
    print(f"Wrote report: {report_output}")
    print(f"Wrote metrics: {metrics_output}")


if __name__ == "__main__":
    main()
