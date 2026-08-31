from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def _float(value: object) -> float | None:
    try:
        if value == "":
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(parsed):
        return None
    return parsed


def _actual_1x2(home_score: object, away_score: object) -> str:
    home = _float(home_score)
    away = _float(away_score)
    if home is None or away is None:
        return ""
    if home > away:
        return "home"
    if home < away:
        return "away"
    return "draw"


def _asian_spread_result(
    home_score: object,
    away_score: object,
    spread_side: object,
    spread_point: object,
) -> str:
    home = _float(home_score)
    away = _float(away_score)
    point = _float(spread_point)
    side = str(spread_side or "").strip()
    if home is None or away is None or point is None or not side:
        return ""
    margin = home - away
    if side == "away":
        margin = away - home
    adjusted = margin + point
    if adjusted > 1e-12:
        return "cover"
    if adjusted < -1e-12:
        return "fail"
    return "push"


def _mean_hit(frame: pd.DataFrame, column: str) -> float | None:
    if column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    if values.empty:
        return None
    return float(values.mean())


def _format_rate(value: float | None) -> str:
    if value is None:
        return "无样本"
    return f"{value:.1%}"


def _merge_results_by_team(
    research: pd.DataFrame,
    results: pd.DataFrame,
) -> pd.DataFrame:
    result_cols = [
        "date",
        "home_team",
        "away_team",
        "status",
        "home_score",
        "away_score",
        "winner",
        "stage",
    ]
    slim = results[[col for col in result_cols if col in results.columns]].copy()
    return research.merge(
        slim,
        on=["date", "home_team", "away_team"],
        how="left",
        suffixes=("", "_actual"),
    )


def settle_external_handicap(
    external_research: pd.DataFrame,
    results: pd.DataFrame,
) -> pd.DataFrame:
    merged = _merge_results_by_team(external_research, results)
    rows = []
    for _, row in merged.iterrows():
        actual_1x2 = _actual_1x2(row.get("home_score"), row.get("away_score"))
        h2h_pick = str(row.get("h2h_favorite", "") or "")
        spread_result = _asian_spread_result(
            row.get("home_score"),
            row.get("away_score"),
            row.get("consensus_spread_side"),
            row.get("consensus_spread_point"),
        )
        rows.append(
            {
                **row.to_dict(),
                "actual_1x2": actual_1x2,
                "h2h_favorite_hit": (
                    int(h2h_pick == actual_1x2) if h2h_pick and actual_1x2 else None
                ),
                "asian_spread_result": spread_result,
                "asian_favorite_cover_hit": (
                    int(spread_result == "cover") if spread_result else None
                ),
                "finished": int(bool(actual_1x2)),
            }
        )
    return pd.DataFrame(rows)


def summarize_completed_market_research(frame: pd.DataFrame) -> dict[str, object]:
    actual = frame["actual_1x2"].fillna("").astype(str).str.strip()
    finished = frame[actual.ne("")].copy()
    return {
        "rows": len(frame),
        "finished_rows": len(finished),
        "model_1x2_accuracy": _mean_hit(finished, "model_1x2_hit"),
        "external_1x2_accuracy": _mean_hit(finished, "external_1x2_hit"),
        "sporttery_1x2_accuracy": _mean_hit(finished, "sporttery_1x2_hit"),
        "model_handicap_accuracy": _mean_hit(finished, "model_handicap_hit"),
        "sporttery_handicap_accuracy": _mean_hit(finished, "sporttery_handicap_hit"),
        "model_total_bucket_accuracy": _mean_hit(finished, "model_total_bucket_hit"),
    }


def render_report(
    *,
    external_settled: pd.DataFrame,
    completed_market_summary: dict[str, object] | None = None,
) -> str:
    external_finished = external_settled[external_settled["finished"].eq(1)]
    pending = external_settled[external_settled["finished"].eq(0)]
    lines = [
        "# 盘口研究回测报告",
        "",
        "## 外盘让球样本",
        "",
        f"- 外盘让球样本：{len(external_settled)} 场",
        f"- 已完赛可结算：{len(external_finished)} 场",
        f"- 待复盘：{len(pending)} 场",
        f"- 外盘胜平负热门命中率：{_format_rate(_mean_hit(external_finished, 'h2h_favorite_hit'))}",
        f"- 外盘让球热门穿盘率：{_format_rate(_mean_hit(external_finished, 'asian_favorite_cover_hit'))}",
        "",
    ]
    if pending.empty:
        lines.append("当前没有待复盘外盘让球样本。")
    else:
        lines.extend(["### 待复盘清单", ""])
        for _, row in pending.iterrows():
            side = "主队" if row.get("consensus_spread_side") == "home" else "客队"
            lines.append(
                f"- {row.get('date', '')} {row.get('home_team', '')} vs {row.get('away_team', '')}："
                f"{side} {row.get('consensus_spread_point', '')}，"
                f"胜平负热门 {row.get('h2h_favorite', '')}，"
                f"大小球 {row.get('total_25_signal', '')}"
            )
        lines.append("")

    if completed_market_summary is not None:
        lines.extend(
            [
                "## 已完赛市场样本基准",
                "",
                f"- 市场研究总样本：{completed_market_summary['rows']} 场",
                f"- 已完赛：{completed_market_summary['finished_rows']} 场",
                f"- 模型胜平负命中率：{_format_rate(completed_market_summary['model_1x2_accuracy'])}",
                f"- 外盘胜平负命中率：{_format_rate(completed_market_summary['external_1x2_accuracy'])}",
                f"- 体彩胜平负命中率：{_format_rate(completed_market_summary['sporttery_1x2_accuracy'])}",
                f"- 模型让球命中率：{_format_rate(completed_market_summary['model_handicap_accuracy'])}",
                f"- 体彩让球命中率：{_format_rate(completed_market_summary['sporttery_handicap_accuracy'])}",
                f"- 模型总进球单项命中率：{_format_rate(completed_market_summary['model_total_bucket_accuracy'])}",
                "",
            ]
        )

    lines.extend(
        [
            "## 当前判断",
            "",
            "目前不能声称外盘让球模型已经被充分验证，因为真正有外盘让球线的样本还没完赛。",
            "",
            "但已有已完赛市场样本说明一件事：胜平负方向相对容易命中，让球和总进球明显更难。这正是外盘让球研究的价值所在，它不是替代胜平负，而是帮助判断强队能不能打穿、比分差会不会被拉开。",
            "",
            "## 下一步验证",
            "",
            "1. 每次赛前保存外盘让球快照。",
            "2. 赛后自动结算是否穿盘、是否走盘、总进球是否符合大小球方向。",
            "3. 按浅盘、中盘、深盘、小球热、大球热分桶统计。",
            "4. 样本达到 30 场后再判断哪些盘口规则真正有效。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--external-research", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--market-research", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--report-output", required=True)
    args = parser.parse_args()

    external = pd.read_csv(args.external_research)
    results = pd.read_csv(args.results)
    settled = settle_external_handicap(external, results)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    settled.to_csv(output, index=False, encoding="utf-8-sig")

    completed_summary = None
    if args.market_research:
        completed_summary = summarize_completed_market_research(
            pd.read_csv(args.market_research)
        )

    report = render_report(
        external_settled=settled,
        completed_market_summary=completed_summary,
    )
    report_output = Path(args.report_output)
    report_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.write_text(report, encoding="utf-8")
    print(f"Wrote handicap backtest: {output}")
    print(f"Wrote report: {report_output}")


if __name__ == "__main__":
    main()
