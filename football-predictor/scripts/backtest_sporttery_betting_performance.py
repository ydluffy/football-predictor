from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _money(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0.0)


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
) -> tuple[str, dict[str, object]]:
    reviewed = ledger[ledger["result"].astype(str).str.len() > 0].copy() if not ledger.empty else ledger
    formal_summary = _summary(reviewed, "stake", "payout", "result")
    formal_by_type = _group_summary(reviewed, "plan_type", "stake", "payout", "result")

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
    }
    return "\n".join(lines) + "\n", metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest Sporttery betting performance from reviewed ledgers.")
    parser.add_argument("--ledger", default="data/manual/betting_plan_ledger.csv")
    parser.add_argument("--scenario-summary", default="data/manual/sporttery_scenario_portfolio_review_2026-07-15_2100_summary.csv")
    parser.add_argument("--scenario-details", default="data/manual/sporttery_scenario_portfolio_review_2026-07-15_2100_details.csv")
    parser.add_argument("--report-output", required=True)
    parser.add_argument("--metrics-output", required=True)
    args = parser.parse_args()

    ledger_path = ROOT / args.ledger
    scenario_summary_path = ROOT / args.scenario_summary
    scenario_details_path = ROOT / args.scenario_details
    ledger = pd.read_csv(ledger_path, encoding="utf-8-sig", keep_default_na=False) if ledger_path.exists() else pd.DataFrame()
    scenario_summary = pd.read_csv(scenario_summary_path, encoding="utf-8-sig", keep_default_na=False) if scenario_summary_path.exists() else pd.DataFrame()
    scenario_details = pd.read_csv(scenario_details_path, encoding="utf-8-sig", keep_default_na=False) if scenario_details_path.exists() else pd.DataFrame()

    report, metrics = build_report(ledger, scenario_summary, scenario_details)
    report_output = ROOT / args.report_output
    metrics_output = ROOT / args.metrics_output
    report_output.parent.mkdir(parents=True, exist_ok=True)
    metrics_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.write_text(report, encoding="utf-8")
    metrics_output.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "report_output": str(report_output), "metrics_output": str(metrics_output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
