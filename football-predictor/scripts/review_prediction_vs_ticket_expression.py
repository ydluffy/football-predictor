from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


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


def diagnose_ticket_expression(row: pd.Series) -> dict[str, str]:
    result = _text(row.get("result"))
    note = _text(row.get("review_note"))
    selections = _text(row.get("selections"))
    net = _num(row.get("net_profit"))

    note_lower = note.lower()
    hit_count = note_lower.count(" hit")
    missed_count = note_lower.count("missed") + note_lower.count("wrong")

    if result == "命中":
        diagnosis = "兑现成功"
        signal_grade = "A"
        issue = "预测和票面表达一致"
        suggestion = "继续记录同类盘口、赔率与赛果，观察是否能稳定复现。"
    elif result == "部分命中":
        diagnosis = "覆盖不足"
        signal_grade = "B" if hit_count >= missed_count else "C"
        issue = "主判断或防线有命中，但预算分配/候选覆盖不足导致未能盈利。"
        suggestion = "保留命中玩法，降低主串比重；把低比分、让球防线和关键比分作为独立回收票。"
    elif hit_count >= 2 and missed_count >= 1:
        diagnosis = "组合结构拖累"
        signal_grade = "B"
        issue = "多个判断方向正确，但串关中混入波动腿，导致整票失效。"
        suggestion = "把高置信两腿拆成2串或单关回收票；第三腿只能进入小额博高票。"
    elif hit_count >= 1 and missed_count >= 1:
        diagnosis = "单点信号有效但票面过重"
        signal_grade = "C"
        issue = "存在命中信号，但没有形成可覆盖成本的独立票。"
        suggestion = "对盘口变化、让球防冷、总进球区间分别建小票，不要全部押在主线串关。"
    else:
        diagnosis = "预测与票面均需复查"
        signal_grade = "D"
        issue = "赛果与投注主线偏差较大，可能是模型判断、盘口解读或数据覆盖不足。"
        suggestion = "回到赛前赔率、外盘盘口、伤停战意和进球环境重新校验，不建议直接加仓同类模式。"

    if "one leg broke" in note_lower:
        suggestion += " 本票明确是一腿拖累，后续同类场景优先拆票而不是三串一。"
    if "market movement" in note_lower and result in {"命中", "部分命中"}:
        suggestion += " 盘口异动信号被验证，后续可提高该信号在防冷票中的权重。"
    if "0:0" in note or "total0" in note_lower or "total 0" in note_lower:
        suggestion += " 低比分剧本要补 0:0 和总进球0，否则会漏掉淘汰赛/强强对话的极低比分。"
    if "let loss hit" in note_lower and net <= 0:
        issue += " 让负方向有效，但回收金额不足。"
        suggestion += " 让负命中却亏损时，应增加让球防线单票权重或减少胜平负主判断。"
    if "score 0:0 not selected" in note_lower:
        suggestion += " 比分矩阵需要在低进球模型下自动加入 0:0。"
    if "总进球" in selections and ("actual4" in note_lower or "total goals=10" in note_lower):
        suggestion += " 总进球区间偏窄时要区分常规2/3球和极端大球，不宜用同一张票覆盖全部剧本。"

    return {
        "diagnosis": diagnosis,
        "prediction_signal_grade": signal_grade,
        "ticket_expression_issue": issue,
        "optimization_suggestion": suggestion,
    }


def review_ledger(ledger: pd.DataFrame, target_date: str | None = None) -> pd.DataFrame:
    frame = ledger.fillna("").copy()
    if target_date:
        frame = frame[frame["date"].astype(str).eq(target_date)].copy()
    rows: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        diagnosis = diagnose_ticket_expression(row)
        rows.append(
            {
                "date": _text(row.get("date")),
                "time_window": _text(row.get("time_window")),
                "plan_id": _text(row.get("plan_id")),
                "plan_type": _text(row.get("plan_type")),
                "stake": _num(row.get("stake")),
                "payout": _num(row.get("payout")),
                "net_profit": _num(row.get("net_profit")),
                "roi": _num(row.get("roi")),
                "result": _text(row.get("result")),
                "selections": _text(row.get("selections")),
                "review_note": _text(row.get("review_note")),
                **diagnosis,
            }
        )
    return pd.DataFrame(rows)


def summarize_review(review: pd.DataFrame) -> dict[str, object]:
    if review.empty:
        return {
            "rows": 0,
            "stake": 0.0,
            "payout": 0.0,
            "net_profit": 0.0,
            "roi": 0.0,
            "diagnosis_counts": {},
        }
    stake = round(float(review["stake"].sum()), 2)
    payout = round(float(review["payout"].sum()), 2)
    net = round(float(review["net_profit"].sum()), 2)
    return {
        "rows": int(len(review)),
        "stake": stake,
        "payout": payout,
        "net_profit": net,
        "roi": round(net / stake, 4) if stake else 0.0,
        "diagnosis_counts": review["diagnosis"].value_counts().to_dict(),
    }


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "暂无可复盘方案。"
    columns = [
        "plan_id",
        "plan_type",
        "stake",
        "payout",
        "net_profit",
        "result",
        "diagnosis",
        "prediction_signal_grade",
        "ticket_expression_issue",
        "optimization_suggestion",
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
    parser.add_argument("--ledger", default="data/manual/betting_plan_ledger.csv")
    parser.add_argument("--date", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--report-output", required=True)
    parser.add_argument("--audit-output", required=True)
    args = parser.parse_args()

    ledger = pd.read_csv(ROOT / args.ledger).fillna("")
    review = review_ledger(ledger, args.date or None)
    summary = summarize_review(review)

    output = ROOT / args.output
    report_output = ROOT / args.report_output
    audit_output = ROOT / args.audit_output
    output.parent.mkdir(parents=True, exist_ok=True)
    report_output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    review.to_csv(output, index=False, encoding="utf-8-sig")
    report_output.write_text(
        "# 预测判断 vs 投注表达深度复盘\n\n"
        f"- 日期：{args.date or '全部'}\n"
        f"- 方案数：{summary['rows']}\n"
        f"- 总投入：{summary['stake']:.2f} 元\n"
        f"- 总返奖：{summary['payout']:.2f} 元\n"
        f"- 净收益：{summary['net_profit']:.2f} 元\n"
        f"- ROI：{summary['roi']:.2%}\n\n"
        "核心看法：本报告把“预测有没有方向感”和“票面有没有把方向表达出来”分开评价。"
        "这样才能发现：有些亏损不是模型完全错，而是串关腿数、玩法覆盖或资金分配错。\n\n"
        + _markdown_table(review)
        + "\n",
        encoding="utf-8",
    )
    audit = {"ok": True, **summary, "output": str(output), "report_output": str(report_output)}
    audit_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
