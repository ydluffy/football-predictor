from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE_BET_UNIT = 2.0


def _num(value: object, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"", "nan", "none", "null", "<na>"} else text


def implied_probability(decimal_odds: float) -> float:
    odds = _num(decimal_odds)
    return round(1.0 / odds, 6) if odds > 1.0 else 0.0


def expected_value(probability: float, decimal_odds: float) -> float:
    prob = max(0.0, min(1.0, _num(probability)))
    odds = _num(decimal_odds)
    if odds <= 1.0:
        return -1.0
    return round(prob * odds - 1.0, 6)


def fractional_kelly(probability: float, decimal_odds: float, fraction: float = 0.25, cap: float = 0.12) -> float:
    prob = max(0.0, min(1.0, _num(probability)))
    odds = _num(decimal_odds)
    if odds <= 1.0:
        return 0.0
    edge = prob * odds - 1.0
    if edge <= 0:
        return 0.0
    full_kelly = edge / (odds - 1.0)
    return round(min(cap, max(0.0, full_kelly * fraction)), 6)


def _candidate_probability(row: pd.Series) -> float:
    model_prob = _num(row.get("model_prob"), -1)
    if model_prob >= 0:
        return max(0.0, min(1.0, model_prob))
    model_edge = _num(row.get("model_edge"), 0.0)
    confidence = _num(row.get("confidence"), 0.0)
    if model_edge:
        base = implied_probability(_candidate_odds(row))
        return max(0.0, min(1.0, base + model_edge + max(0.0, confidence - 0.5) * 0.05))
    market_prob = _num(row.get("market_prob"), -1)
    if market_prob >= 0:
        return max(0.0, min(1.0, market_prob))
    return implied_probability(_candidate_odds(row))


def _candidate_odds(row: pd.Series) -> float:
    odds = _num(row.get("odds"))
    if odds > 1.0:
        return odds
    total_stake = _num(row.get("total_stake"), _num(row.get("stake"), 0.0))
    payout_min = _num(row.get("estimated_payout_min"))
    payout_max = _num(row.get("estimated_payout_max"))
    if total_stake > 0 and (payout_min > 0 or payout_max > 0):
        payout = payout_min if payout_min > 0 else payout_max
        return round(payout / total_stake, 6)
    estimated_odds = _text(row.get("estimated_odds"))
    if "*" not in estimated_odds and "/" not in estimated_odds and "-" not in estimated_odds:
        return _num(estimated_odds)
    return 0.0


def _risk_penalty(row: pd.Series, risk_aversion: float) -> float:
    risk_score = _num(row.get("risk_score"), 0.0)
    confidence = _num(row.get("confidence"), 0.0)
    confidence_penalty = max(0.0, 0.5 - confidence) if confidence else 0.0
    return risk_aversion * (risk_score + confidence_penalty)


def optimize_candidates(
    candidates: pd.DataFrame,
    budget: float = 100.0,
    unit: float = BASE_BET_UNIT,
    risk_aversion: float = 0.15,
    max_per_match: float = 60.0,
) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    for idx, row in candidates.fillna("").iterrows():
        odds = _candidate_odds(row)
        prob = _candidate_probability(row)
        edge = expected_value(prob, odds)
        kelly = fractional_kelly(prob, odds)
        score = round(edge - _risk_penalty(row, risk_aversion), 6)
        rows.append(
            {
                "candidate_id": _text(row.get("candidate_id")) or _text(row.get("title")) or f"C{idx + 1}",
                "match_key": _text(row.get("match_key")) or _text(row.get("match_number")) or f"M{idx + 1}",
                "play_type": _text(row.get("play_type")),
                "selection": _text(row.get("selection")) or _text(row.get("selections")),
                "odds": odds,
                "model_prob": round(prob, 6),
                "market_prob": _num(row.get("market_prob"), implied_probability(odds)),
                "edge": edge,
                "kelly_fraction": kelly,
                "score": score,
                "note": _text(row.get("note")),
            }
        )

    ranked = pd.DataFrame(rows)
    ranked = ranked[(ranked["odds"] > 1.0) & (ranked["edge"] > 0) & (ranked["score"] > 0)].copy()
    if ranked.empty:
        return ranked

    ranked = ranked.sort_values(["score", "edge", "odds"], ascending=[False, False, False], kind="mergesort")
    remaining = float(budget)
    per_match_used: dict[str, float] = {}
    stakes: list[float] = []

    for _, row in ranked.iterrows():
        match_key = str(row["match_key"])
        match_left = max(0.0, max_per_match - per_match_used.get(match_key, 0.0))
        desired = max(unit, budget * float(row["kelly_fraction"]))
        stake = min(desired, remaining, match_left)
        stake = int(stake // unit) * unit
        if stake < unit:
            stake = 0.0
        stakes.append(round(stake, 2))
        remaining = round(remaining - stake, 2)
        per_match_used[match_key] = round(per_match_used.get(match_key, 0.0) + stake, 2)

    ranked["suggested_stake"] = stakes
    ranked = ranked[ranked["suggested_stake"] > 0].copy()
    ranked["estimated_payout"] = (ranked["suggested_stake"] * ranked["odds"]).round(2)
    ranked["expected_profit"] = (ranked["suggested_stake"] * ranked["edge"]).round(2)
    ranked["budget"] = float(budget)
    ranked["unused_budget"] = round(budget - float(ranked["suggested_stake"].sum()), 2)
    return ranked.reset_index(drop=True)


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "暂无正期望候选。"
    columns = [
        "candidate_id",
        "match_key",
        "play_type",
        "selection",
        "odds",
        "model_prob",
        "edge",
        "suggested_stake",
        "estimated_payout",
        "expected_profit",
    ]
    use = frame[[column for column in columns if column in frame.columns]].copy()
    lines = [
        "| " + " | ".join(use.columns) + " |",
        "| " + " | ".join("---" for _ in use.columns) + " |",
    ]
    for row in use.astype(str).itertuples(index=False, name=None):
        lines.append("| " + " | ".join(cell.replace("\n", " ") for cell in row) + " |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates-csv", required=True)
    parser.add_argument("--budget", type=float, default=100.0)
    parser.add_argument("--unit", type=float, default=BASE_BET_UNIT)
    parser.add_argument("--risk-aversion", type=float, default=0.15)
    parser.add_argument("--max-per-match", type=float, default=60.0)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report-output", required=True)
    parser.add_argument("--audit-output", required=True)
    args = parser.parse_args()

    candidates = pd.read_csv(ROOT / args.candidates_csv).fillna("")
    optimized = optimize_candidates(
        candidates,
        budget=args.budget,
        unit=args.unit,
        risk_aversion=args.risk_aversion,
        max_per_match=args.max_per_match,
    )

    output = ROOT / args.output
    report_output = ROOT / args.report_output
    audit_output = ROOT / args.audit_output
    output.parent.mkdir(parents=True, exist_ok=True)
    report_output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    optimized.to_csv(output, index=False, encoding="utf-8-sig")

    total_stake = round(float(optimized["suggested_stake"].sum()) if not optimized.empty else 0.0, 2)
    expected_profit_sum = round(float(optimized["expected_profit"].sum()) if not optimized.empty else 0.0, 2)
    report_output.write_text(
        "# 投注组合优化报告\n\n"
        f"- 预算：{args.budget:.2f} 元\n"
        f"- 建议投入：{total_stake:.2f} 元\n"
        f"- 预期利润合计：{expected_profit_sum:.2f} 元\n"
        f"- 未用预算：{args.budget - total_stake:.2f} 元\n\n"
        "说明：本模块只做概率、赔率、风险约束下的模拟优化，不代表真实收益保证。\n\n"
        + _markdown_table(optimized)
        + "\n",
        encoding="utf-8",
    )
    audit = {
        "ok": True,
        "input_rows": int(len(candidates)),
        "selected_rows": int(len(optimized)),
        "total_stake": total_stake,
        "expected_profit": expected_profit_sum,
        "output": str(output),
        "report_output": str(report_output),
    }
    audit_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
