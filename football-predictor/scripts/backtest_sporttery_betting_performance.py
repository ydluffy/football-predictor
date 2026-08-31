from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _money(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0.0)


def _plan_odds(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = float(text)
        return parsed if parsed > 1.0 else None
    except ValueError:
        pass
    if "=" in text:
        try:
            parsed = float(text.rsplit("=", 1)[1].strip())
            return parsed if parsed > 1.0 else None
        except ValueError:
            pass
    factors = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", text)]
    if "*" in text and factors:
        parsed = math.prod(factors)
        return parsed if parsed > 1.0 else None
    return factors[-1] if factors and factors[-1] > 1.0 else None


def _with_plan_odds(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if result.empty:
        result["parsed_plan_odds"] = pd.Series(dtype=float)
        return result
    actual = result.get("actual_odds", pd.Series("", index=result.index)).map(_plan_odds)
    estimated = result.get("estimated_odds", pd.Series("", index=result.index)).map(_plan_odds)
    result["parsed_plan_odds"] = actual.where(actual.notna(), estimated)
    return result


def _summary(frame: pd.DataFrame, stake_col: str, payout_col: str, result_col: str | None = None) -> dict[str, object]:
    if frame.empty:
        return {
            "plans": 0,
            "stake": 0.0,
            "payout": 0.0,
            "net": 0.0,
            "roi": 0.0,
            "hit_rate": 0.0,
        }
    stake = float(_money(frame[stake_col]).sum())
    payout = float(_money(frame[payout_col]).sum())
    hit_rate = 0.0
    if result_col and result_col in frame.columns:
        hit_rate = float((frame[result_col].astype(str) == "命中").mean())
    elif "hit" in frame.columns:
        hit_rate = float(frame["hit"].astype(str).str.lower().eq("true").mean())
    elif "hit_tickets" in frame.columns and "ticket_count" in frame.columns:
        total_tickets = float(_money(frame["ticket_count"]).sum())
        hit_rate = float(_money(frame["hit_tickets"]).sum() / total_tickets) if total_tickets else 0.0
    net = payout - stake
    return {
        "plans": int(len(frame)),
        "stake": round(stake, 2),
        "payout": round(payout, 2),
        "net": round(net, 2),
        "roi": round(net / stake, 4) if stake else 0.0,
        "hit_rate": round(hit_rate, 4),
    }


def _group_summary(frame: pd.DataFrame, group_col: str, stake_col: str, payout_col: str, result_col: str | None = None) -> pd.DataFrame:
    rows = []
    if frame.empty or group_col not in frame.columns:
        return pd.DataFrame(rows)
    for key, group in frame.groupby(group_col, dropna=False):
        rows.append({group_col: key, **_summary(group, stake_col, payout_col, result_col)})
    return pd.DataFrame(rows).sort_values(["net", group_col], ascending=[False, True], kind="mergesort")


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "暂无。"
    lines = [
        "| " + " | ".join(str(column) for column in frame.columns) + " |",
        "| " + " | ".join("---" for _ in frame.columns) + " |",
    ]
    for row in frame.astype(str).itertuples(index=False, name=None):
        lines.append("| " + " | ".join(cell.replace("\n", " ") for cell in row) + " |")
    return "\n".join(lines)


def build_report(
    ledger: pd.DataFrame,
    scenario_summary: pd.DataFrame,
    scenario_details: pd.DataFrame,
    fixed_odds_ledger: pd.DataFrame | None = None,
    fixed_odds_min: float = 6.00,
    fixed_odds_max: float = 10.00,
) -> tuple[str, dict[str, object]]:
    reviewed = ledger[ledger["result"].astype(str).isin(["命中", "未中"])].copy() if not ledger.empty else ledger
    reviewed = _with_plan_odds(reviewed)
    formal_summary = _summary(reviewed, "stake", "payout", "result")
    formal_by_type = _group_summary(reviewed, "plan_type", "stake", "payout", "result")
    fixed_odds_frame = reviewed[
        reviewed["parsed_plan_odds"].ge(fixed_odds_min)
        & reviewed["parsed_plan_odds"].le(fixed_odds_max)
    ].copy()
    fixed_odds_summary = _summary(fixed_odds_frame, "stake", "payout", "result")
    fixed_average_odds = float(fixed_odds_frame["parsed_plan_odds"].mean()) if not fixed_odds_frame.empty else 0.0
    fixed_odds_summary.update(
        {
            "odds_min": fixed_odds_min,
            "odds_max_inclusive": fixed_odds_max,
            "average_odds": round(fixed_average_odds, 4),
            "break_even_hit_rate_at_average_odds": round(1.0 / fixed_average_odds, 4) if fixed_average_odds else 0.0,
        }
    )
    prospective = fixed_odds_ledger if fixed_odds_ledger is not None else pd.DataFrame()
    if not prospective.empty:
        prospective = prospective[prospective["result"].astype(str).isin(["命中", "未中"])].copy()
    prospective_summary = _summary(prospective, "stake", "payout", "result")

    scenario_pack_summary = _summary(scenario_summary, "stake", "payout")
    scenario_by_match = scenario_summary.copy()
    scenario_by_ticket = _group_summary(scenario_details, "title", "stake", "payout")
    scenario_by_role = _group_summary(scenario_details, "role", "stake", "payout")

    combined_stake = formal_summary["stake"] + scenario_pack_summary["stake"]
    combined_payout = formal_summary["payout"] + scenario_pack_summary["payout"]
    combined_net = combined_payout - combined_stake
    combined = {
        "stake": round(combined_stake, 2),
        "payout": round(combined_payout, 2),
        "net": round(combined_net, 2),
        "roi": round(combined_net / combined_stake, 4) if combined_stake else 0.0,
    }

    lines = [
        "# 体彩预测 + 投注方案回测",
        "",
        "## 总览",
        "",
        f"- 正式串关/方向台账：{formal_summary['plans']} 个方案，投入 {formal_summary['stake']:.2f}，返奖 {formal_summary['payout']:.2f}，净收益 {formal_summary['net']:.2f}，ROI {formal_summary['roi']:.2%}，方案命中率 {formal_summary['hit_rate']:.2%}。",
        f"- 同场多玩法剧本包：{scenario_pack_summary['plans']} 个方案包，投入 {scenario_pack_summary['stake']:.2f}，返奖 {scenario_pack_summary['payout']:.2f}，净收益 {scenario_pack_summary['net']:.2f}，ROI {scenario_pack_summary['roi']:.2%}，子票命中率 {scenario_pack_summary['hit_rate']:.2%}。",
        f"- 两类已复盘样本合计：投入 {combined['stake']:.2f}，返奖 {combined['payout']:.2f}，净收益 {combined['net']:.2f}，ROI {combined['roi']:.2%}。",
        "",
        f"## 固定赔率观察基线（{fixed_odds_min:.2f}–{fixed_odds_max:.2f}，含上下限）",
        "",
        f"- 历史命中率：{fixed_odds_summary['hit_rate']:.2%}（{fixed_odds_summary['plans']} 个已结算方案）。",
        f"- 投入 {fixed_odds_summary['stake']:.2f}，返奖 {fixed_odds_summary['payout']:.2f}，净收益 {fixed_odds_summary['net']:.2f}，ROI {fixed_odds_summary['roi']:.2%}。",
        f"- 平均赔率 {fixed_odds_summary['average_odds']:.4f}，对应盈亏平衡命中率约 {fixed_odds_summary['break_even_hit_rate_at_average_odds']:.2%}。",
        "- 这只是从既有不同策略中按赔率区间切出的回顾基线，不是前瞻回测；新增固定赔率方案必须从现在起独立影子记录，防止事后筛选偏差。",
        f"- 独立前瞻影子样本：{prospective_summary['plans']} 个，命中率 {prospective_summary['hit_rate']:.2%}，ROI {prospective_summary['roi']:.2%}，净收益 {prospective_summary['net']:.2f}（虚拟资金）。",
        "",
        "## 正式台账按方案类型",
        "",
        _markdown_table(formal_by_type),
        "",
        "## 同场剧本包按比赛",
        "",
        _markdown_table(scenario_by_match),
        "",
        "## 同场剧本包按子票玩法",
        "",
        _markdown_table(scenario_by_ticket),
        "",
        "## 同场剧本包按投注角色",
        "",
        _markdown_table(scenario_by_role),
        "",
        "## 初步结论",
        "",
        "- 当前正式串关样本波动极大，早期几单盈利较高，但 7月15日 串关全黑暴露出单方向组合的回撤风险。",
        "- 同场剧本包在 7月15日 样本里把原本的大亏压到小亏，说明比分/让球/总进球/半全场的分层保护有实际减亏价值。",
        "- 样本量仍很小，不能判断长期盈利；下一步必须每天固定输出并复盘同场剧本包，至少累计 50-100 个方案包后再判断稳定性。",
        "- 当前最值得保留的是：热门让球防线、比分防冷、客队强势下的总进球/半全场组合；最需要优化的是低比分总进球选择和半全场选项优先级。",
    ]
    metrics = {
        "formal": formal_summary,
        "scenario": scenario_pack_summary,
        "combined": combined,
        "fixed_odds_observation_baseline": fixed_odds_summary,
        "fixed_odds_forward_shadow": prospective_summary,
    }
    return "\n".join(lines) + "\n", metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest Sporttery betting performance from reviewed ledgers.")
    parser.add_argument("--ledger", default="data/manual/betting_plan_ledger.csv")
    parser.add_argument("--scenario-summary", default="data/manual/sporttery_scenario_portfolio_review_2026-07-15_2100_summary.csv")
    parser.add_argument("--scenario-details", default="data/manual/sporttery_scenario_portfolio_review_2026-07-15_2100_details.csv")
    parser.add_argument("--report-output", required=True)
    parser.add_argument("--metrics-output", required=True)
    parser.add_argument("--fixed-odds-ledger", default="data/manual/fixed_odds_shadow_ledger.csv")
    parser.add_argument("--fixed-odds-min", type=float, default=6.00)
    parser.add_argument("--fixed-odds-max", type=float, default=10.00)
    args = parser.parse_args()

    ledger_path = ROOT / args.ledger
    scenario_summary_path = ROOT / args.scenario_summary
    scenario_details_path = ROOT / args.scenario_details
    ledger = pd.read_csv(ledger_path, encoding="utf-8-sig", keep_default_na=False) if ledger_path.exists() else pd.DataFrame()
    scenario_summary = pd.read_csv(scenario_summary_path, encoding="utf-8-sig", keep_default_na=False) if scenario_summary_path.exists() else pd.DataFrame()
    scenario_details = pd.read_csv(scenario_details_path, encoding="utf-8-sig", keep_default_na=False) if scenario_details_path.exists() else pd.DataFrame()
    fixed_odds_path = ROOT / args.fixed_odds_ledger
    fixed_odds_ledger = pd.read_csv(fixed_odds_path, encoding="utf-8-sig", keep_default_na=False) if fixed_odds_path.exists() else pd.DataFrame()

    report, metrics = build_report(
        ledger,
        scenario_summary,
        scenario_details,
        fixed_odds_ledger=fixed_odds_ledger,
        fixed_odds_min=args.fixed_odds_min,
        fixed_odds_max=args.fixed_odds_max,
    )
    report_output = ROOT / args.report_output
    metrics_output = ROOT / args.metrics_output
    report_output.parent.mkdir(parents=True, exist_ok=True)
    metrics_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.write_text(report, encoding="utf-8")
    metrics_output.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "report_output": str(report_output), "metrics_output": str(metrics_output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
