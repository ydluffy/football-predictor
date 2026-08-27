from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _score_parts(score: object) -> tuple[int | None, int | None]:
    match = re.fullmatch(r"\s*(\d+)\s*:\s*(\d+)\s*", str(score or ""))
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _side_from_score(score: object) -> str:
    home, away = _score_parts(score)
    if home is None or away is None:
        return ""
    if home > away:
        return "H"
    if home == away:
        return "D"
    return "A"


def _spf_label(score: object) -> str:
    return {"H": "胜", "D": "平", "A": "负"}.get(_side_from_score(score), "")


def _rqspf_label(score: object, handicap: object) -> str:
    home, away = _score_parts(score)
    if home is None or away is None:
        return ""
    try:
        adjusted_home = home + int(str(handicap).replace("+", ""))
    except ValueError:
        return ""
    if adjusted_home > away:
        return "让胜"
    if adjusted_home == away:
        return "让平"
    return "让负"


def _total_goals_label(score: object) -> str:
    home, away = _score_parts(score)
    if home is None or away is None:
        return ""
    total = home + away
    return "7_plus" if total >= 7 else str(total)


def _half_full_label(half_score: object, full_score: object) -> str:
    half = _side_from_score(half_score)
    full = _side_from_score(full_score)
    return f"{half}-{full}" if half and full else ""


def _normalize_match_number(value: object) -> str:
    match = re.search(r"(\d+)$", str(value or ""))
    return match.group(1) if match else str(value or "")


def _infer_match_number(portfolio: pd.Series) -> str:
    direct = _normalize_match_number(portfolio.get("match_number", ""))
    if direct:
        return direct
    plan_match = re.search(r"_(\d{3})$", str(portfolio.get("plan_id", "")))
    return plan_match.group(1) if plan_match else ""


def _portfolio_tickets(portfolio: pd.Series) -> list[str]:
    raw = str(portfolio.get("tickets") or portfolio.get("selections") or "")
    return [item.strip() for item in re.split(r"[；;]", raw) if item.strip()]


def _parse_choice(value: str) -> tuple[str, float]:
    selection, _, odds = value.partition("@")
    try:
        return selection.strip(), float(odds)
    except ValueError:
        return selection.strip(), 0.0


def parse_ticket_text(ticket_text: str) -> dict[str, object]:
    parts = [part.strip() for part in re.split(r"[｜|]", str(ticket_text or ""))]
    if len(parts) < 4:
        return {
            "role": "",
            "title": "",
            "choices": [],
            "stake": 0.0,
            "unit_stake": 0.0,
            "raw": ticket_text,
        }
    stake_match = re.search(r"([0-9.]+)元\(([0-9.]+)元/项\)", parts[3])
    stake = float(stake_match.group(1)) if stake_match else 0.0
    unit_stake = float(stake_match.group(2)) if stake_match else 0.0
    return {
        "role": parts[0],
        "title": parts[1],
        "choices": [_parse_choice(item) for item in parts[2].split("/") if item.strip()],
        "stake": stake,
        "unit_stake": unit_stake,
        "raw": ticket_text,
    }


def _expected_for_ticket(ticket: dict[str, object], result: pd.Series) -> str:
    title = str(ticket.get("title", ""))
    if "胜平负" in title and "让球" not in title:
        return _spf_label(result.get("full_time_score"))
    if "让球" in title:
        return _rqspf_label(result.get("full_time_score"), result.get("handicap"))
    if "总进球" in title:
        return _total_goals_label(result.get("full_time_score"))
    if "比分" in title:
        return str(result.get("full_time_score") or "")
    if "半全场" in title:
        return _half_full_label(result.get("half_time_score"), result.get("full_time_score"))
    return ""


def evaluate_ticket(ticket_text: str, result: pd.Series) -> dict[str, object]:
    ticket = parse_ticket_text(ticket_text)
    actual = _expected_for_ticket(ticket, result)
    choices = ticket.get("choices", [])
    hit_choice = ""
    hit_odds = 0.0
    for selection, odds in choices:
        normalized = "7_plus" if selection in {"7+", "7_plus"} else selection
        if normalized == actual:
            hit_choice = selection
            hit_odds = float(odds)
            break
    payout = float(ticket.get("unit_stake") or 0.0) * hit_odds if hit_choice else 0.0
    stake = float(ticket.get("stake") or 0.0)
    return {
        "role": ticket.get("role", ""),
        "title": ticket.get("title", ""),
        "actual": actual,
        "choices": "/".join(f"{selection}@{odds:g}" for selection, odds in choices),
        "stake": round(stake, 2),
        "hit": bool(hit_choice),
        "hit_choice": hit_choice,
        "payout": round(payout, 2),
        "net": round(payout - stake, 2),
    }


def review_portfolios(portfolios: pd.DataFrame, results: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    results = results.copy()
    results["match_number_norm"] = results["match_number"].map(_normalize_match_number)
    detail_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    for _, portfolio in portfolios.iterrows():
        match_number = _infer_match_number(portfolio)
        matched = results[results["match_number_norm"].eq(match_number)]
        if matched.empty:
            summary_rows.append(
                {
                    "plan_id": portfolio.get("plan_id", ""),
                    "match_number": match_number,
                    "match": portfolio.get("match", ""),
                    "result_status": "待匹配",
                    "stake": portfolio.get("total_stake") or portfolio.get("stake") or 0,
                    "payout": 0.0,
                    "net": 0.0,
                    "roi": "",
                    "hit_tickets": 0,
                    "ticket_count": 0,
                    "note": "未匹配到官方赛果，保持待赛/待官方赛果匹配。",
                }
            )
            continue
        result = matched.iloc[0]
        ticket_texts = _portfolio_tickets(portfolio)
        evaluated = [evaluate_ticket(ticket_text, result) for ticket_text in ticket_texts]
        match_name = (
            str(portfolio.get("match") or "")
            or f"{result.get('home_team', '')} vs {result.get('away_team', '')}"
        )
        for item in evaluated:
            detail_rows.append(
                {
                    "plan_id": portfolio.get("plan_id", ""),
                    "match_number": result.get("match_number", match_number),
                    "match": match_name,
                    "full_time_score": result.get("full_time_score", ""),
                    "half_time_score": result.get("half_time_score", ""),
                    **item,
                }
            )
        stake = round(sum(float(item["stake"]) for item in evaluated), 2)
        payout = round(sum(float(item["payout"]) for item in evaluated), 2)
        net = round(payout - stake, 2)
        summary_rows.append(
            {
                "plan_id": portfolio.get("plan_id", ""),
                "match_number": result.get("match_number", match_number),
                "match": match_name,
                "result_status": "已复盘",
                "full_time_score": result.get("full_time_score", ""),
                "half_time_score": result.get("half_time_score", ""),
                "stake": stake,
                "payout": payout,
                "net": net,
                "roi": round(net / stake, 4) if stake else 0.0,
                "hit_tickets": sum(1 for item in evaluated if item["hit"]),
                "ticket_count": len(evaluated),
                "note": "按体彩90分钟口径逐子票结算；同场多玩法为独立票，不是混合过关。",
            }
        )
    return pd.DataFrame(summary_rows), pd.DataFrame(detail_rows)


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "暂无。"
    lines = [
        "| " + " | ".join(str(column) for column in frame.columns) + " |",
        "| " + " | ".join("---" for _ in frame.columns) + " |",
    ]
    for row in frame.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(str(cell).replace("\n", " ") for cell in row) + " |")
    return "\n".join(lines)


def write_report(path: Path, summary: pd.DataFrame, details: pd.DataFrame) -> None:
    total_stake = pd.to_numeric(summary.get("stake", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
    total_payout = pd.to_numeric(summary.get("payout", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
    net = total_payout - total_stake
    lines = [
        "# 体彩同场剧本包复盘",
        "",
        f"- 方案包数：{len(summary)}",
        f"- 总投入：{total_stake:.2f}",
        f"- 总返奖：{total_payout:.2f}",
        f"- 净收益：{net:.2f}",
        f"- ROI：{(net / total_stake if total_stake else 0):.2%}",
        "",
        "## 方案包汇总",
        "",
        _markdown_table(summary),
        "",
        "## 子票明细",
        "",
        _markdown_table(details),
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Review same-match Sporttery scenario portfolios.")
    parser.add_argument("--portfolio-csv", required=True)
    parser.add_argument("--results-csv", required=True)
    parser.add_argument("--summary-output", required=True)
    parser.add_argument("--detail-output", required=True)
    parser.add_argument("--report-output", required=True)
    parser.add_argument("--audit-output", required=True)
    args = parser.parse_args()

    portfolios = pd.read_csv(ROOT / args.portfolio_csv, encoding="utf-8-sig").fillna("")
    results = pd.read_csv(ROOT / args.results_csv, encoding="utf-8-sig").fillna("")
    summary, details = review_portfolios(portfolios, results)

    summary_output = ROOT / args.summary_output
    detail_output = ROOT / args.detail_output
    report_output = ROOT / args.report_output
    audit_output = ROOT / args.audit_output
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    detail_output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(summary_output, index=False, encoding="utf-8-sig")
    details.to_csv(detail_output, index=False, encoding="utf-8-sig")
    write_report(report_output, summary, details)

    audit = {
        "ok": True,
        "portfolio_rows": int(len(portfolios)),
        "summary_rows": int(len(summary)),
        "detail_rows": int(len(details)),
        "summary_output": str(summary_output),
        "detail_output": str(detail_output),
        "report_output": str(report_output),
    }
    audit_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
