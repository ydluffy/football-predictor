from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _float(value: object, default: float | None = None) -> float | None:
    try:
        if value == "":
            return default
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if pd.isna(parsed):
        return default
    return parsed


def _best_spread_line(rows: pd.DataFrame) -> pd.Series | None:
    if rows.empty:
        return None
    frame = rows.copy()
    frame["bookmaker_count_num"] = pd.to_numeric(
        frame["bookmaker_count"],
        errors="coerce",
    ).fillna(0)
    frame["abs_point"] = pd.to_numeric(frame["point"], errors="coerce").abs()
    frame = frame.sort_values(
        ["bookmaker_count_num", "abs_point"],
        ascending=[False, True],
    )
    return frame.iloc[0]


def _best_h2h(rows: pd.DataFrame) -> dict[str, object]:
    if rows.empty:
        return {}
    row = rows.iloc[0]
    probs = {
        "home": _float(row.get("home_market_probability")),
        "draw": _float(row.get("draw_market_probability")),
        "away": _float(row.get("away_market_probability")),
    }
    available = {key: value for key, value in probs.items() if value is not None}
    favorite = max(available, key=available.get) if available else ""
    return {
        "h2h_home_probability": probs["home"],
        "h2h_draw_probability": probs["draw"],
        "h2h_away_probability": probs["away"],
        "h2h_favorite": favorite,
        "h2h_favorite_probability": available.get(favorite),
        "h2h_bookmaker_count": row.get("bookmaker_count", ""),
    }


def _totals_25(rows: pd.DataFrame) -> dict[str, object]:
    if rows.empty:
        return {}
    frame = rows[pd.to_numeric(rows["point"], errors="coerce").eq(2.5)]
    if frame.empty:
        return {}
    row = frame.sort_values("bookmaker_count", ascending=False).iloc[0]
    over = _float(row.get("over_avg_odds"))
    under = _float(row.get("under_avg_odds"))
    total_signal = ""
    if over is not None and under is not None:
        total_signal = "over_lean" if over < under else "under_lean"
    return {
        "total_25_over_avg_odds": over,
        "total_25_under_avg_odds": under,
        "total_25_bookmaker_count": row.get("bookmaker_count", ""),
        "total_25_signal": total_signal,
    }


def _spread_side(row: pd.Series) -> str:
    home_odds = _float(row.get("home_spread_avg_odds"))
    away_odds = _float(row.get("away_spread_avg_odds"))
    if home_odds is not None and away_odds is not None:
        return "home" if home_odds < away_odds else "away"
    if home_odds is not None:
        return "home"
    if away_odds is not None:
        return "away"
    return ""


def _classify_spread(row: pd.Series, h2h_favorite: str) -> str:
    point = _float(row.get("point"), 0.0) or 0.0
    side = _spread_side(row)
    if abs(point) < 1e-9:
        return "平手/半球附近，市场认为胜负差很小"
    if abs(point) <= 0.75:
        return "浅盘，偏一球内胜负"
    if abs(point) <= 1.25:
        return "中盘，支持热门赢球但需防只赢一球"
    if abs(point) <= 1.75:
        return "深盘，市场在讨论两球差"
    return "极深盘，需用总进球和阵容确认是否支撑打穿"


def _spread_team_name(row: pd.Series) -> str:
    side = str(row.get("consensus_spread_side", ""))
    if side == "home":
        return str(row.get("home_team", ""))
    if side == "away":
        return str(row.get("away_team", ""))
    return "无"


def build_external_handicap_research(summary: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    grouped = summary.groupby(["event_id", "home_team", "away_team", "date", "commence_time"], dropna=False)
    for (event_id, home, away, date, commence_time), group in grouped:
        h2h = _best_h2h(group[group["market_key"].eq("h2h")])
        best_spread = _best_spread_line(group[group["market_key"].eq("spreads")])
        totals = _totals_25(group[group["market_key"].eq("totals")])
        if best_spread is None:
            continue
        point = _float(best_spread.get("point"), 0.0) or 0.0
        spread_side = _spread_side(best_spread)
        rows.append(
            {
                "event_id": event_id,
                "date": date,
                "commence_time": commence_time,
                "home_team": home,
                "away_team": away,
                **h2h,
                "consensus_spread_point": point,
                "consensus_spread_side": spread_side,
                "consensus_spread_bookmaker_count": best_spread.get("bookmaker_count", ""),
                "home_spread_avg_odds": best_spread.get("home_spread_avg_odds", ""),
                "away_spread_avg_odds": best_spread.get("away_spread_avg_odds", ""),
                "spread_interpretation": _classify_spread(
                    best_spread,
                    str(h2h.get("h2h_favorite", "")),
                ),
                **totals,
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["date", "commence_time", "home_team"]).reset_index(drop=True)


def render_report(research: pd.DataFrame) -> str:
    lines = [
        "# 外盘让球盘口研究报告",
        "",
        "## 研究口径",
        "",
        "本报告研究外盘亚洲让球/让分市场的结构信号：盘口深度、盘口侧、胜平负热门、大小球是否支撑打穿。",
        "",
        "重要说明：盘口不是比赛原因，它反映的是机构定价、资金分布和风险控制。当前文件是赛前快照，不是完整历史回测；要验证长期有效性，需要持续保存初盘、赛前 12 小时、赛前 2 小时和临场快照。",
        "",
        "## 当前样本",
        "",
        f"- 有外盘让球样本：{len(research)} 场",
        "",
        "## 盘口解读",
        "",
    ]
    for _, row in research.iterrows():
        favorite = {
            "home": row.get("home_team", ""),
            "away": row.get("away_team", ""),
            "draw": "平局",
            "": "无",
        }.get(str(row.get("h2h_favorite", "")), "")
        lines.extend(
            [
                f"### {row.get('home_team', '')} vs {row.get('away_team', '')}",
                "",
                f"- 胜平负热门：{favorite}，热门概率：{_fmt_pct(row.get('h2h_favorite_probability'))}",
                f"- 共识让球线：{_spread_team_name(row)} {row.get('consensus_spread_point', '')}，覆盖公司数：{row.get('consensus_spread_bookmaker_count', '')}",
                f"- 盘口解释：{row.get('spread_interpretation', '')}",
                f"- 大小 2.5：{row.get('total_25_signal', '') or '无'}，大球均赔 {row.get('total_25_over_avg_odds', '')}，小球均赔 {row.get('total_25_under_avg_odds', '')}",
                f"- 研究提示：{_research_note(row)}",
                "",
            ]
        )
    lines.extend(
        [
            "## 验证方案",
            "",
            "1. 赛前固定保存外盘快照：初盘、赛前 12 小时、赛前 2 小时、临场。",
            "2. 每场赛后结算：90 分钟胜平负、净胜球、是否穿亚洲盘、总进球。",
            "3. 分桶回测：平手/浅盘/中盘/深盘分别统计赢盘率、走盘率、输盘率。",
            "4. 重点验证：胜平负热门但让球不强时，是否更容易小胜或不穿盘。",
            "5. 与模型结合：当模型比分分布和外盘让球冲突时，把该场降为高风险。",
            "",
            "## 可提炼的规则",
            "",
            "- 深盘必须得到大小球支持，否则强队赢球不等于穿盘。",
            "- 浅盘低水比胜平负更能表达机构对一球内走势的防守。",
            "- 让球盘口与胜平负方向一致，方向可信度上升；与大小球一致，比分区间可信度上升。",
            "- 如果胜平负热强队，但亚洲盘只给浅盘或不升盘，重点防强队小胜、平局或赢球不穿。",
        ]
    )
    return "\n".join(lines) + "\n"


def _fmt_pct(value: object) -> str:
    parsed = _float(value)
    if parsed is None:
        return "无"
    return f"{parsed:.1%}"


def _research_note(row: pd.Series) -> str:
    favorite = str(row.get("h2h_favorite", ""))
    point = _float(row.get("consensus_spread_point"), 0.0) or 0.0
    total_signal = str(row.get("total_25_signal", ""))
    if abs(point) >= 1.0 and total_signal == "under_lean":
        return "深盘但小球更热，强队穿盘风险上升。"
    if abs(point) >= 1.0 and total_signal == "over_lean":
        return "深盘配合大球，比分差被打开的概率更高。"
    if abs(point) <= 0.5:
        return "浅盘结构，优先研究一球内胜负、平局和受让保护。"
    if favorite == "draw":
        return "胜平负缺少明确热门，盘口更适合做风险识别。"
    return "胜平负方向与让球深度需结合模型比分分布验证。"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report-output", required=True)
    args = parser.parse_args()

    summary = pd.read_csv(args.summary)
    research = build_external_handicap_research(summary)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    research.to_csv(output, index=False, encoding="utf-8-sig")
    report = render_report(research)
    report_output = Path(args.report_output)
    report_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.write_text(report, encoding="utf-8")
    print(f"Wrote external handicap research: {output}")
    print(f"Wrote report: {report_output}")


if __name__ == "__main__":
    main()
