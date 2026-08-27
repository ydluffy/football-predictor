from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


PENDING_RESULTS = {"", "待赛", "待赛果", "待官方赛果", "待核验", "pending"}
SETTLED_RESULTS = {"命中", "未中", "部分命中", "win", "loss", "partial"}
BINARY_RESULTS = {"命中", "未中", "win", "loss"}
ARCHIVED_RESULTS = {"已替代", "superseded", "archived"}


def _text(value: object) -> str:
    return str(value or "").strip()


def _number(value: object) -> float | None:
    text = _text(value)
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _normalized_selections(value: object) -> str:
    return re.sub(r"\s+", "", _text(value)).casefold()


def _financial_summary(rows: Iterable[dict[str, str]]) -> dict[str, float | int | None]:
    selected = list(rows)
    stakes = [_number(row.get("stake")) for row in selected]
    payouts = [_number(row.get("payout")) for row in selected]
    valid = [
        (stake, payout)
        for stake, payout in zip(stakes, payouts, strict=True)
        if stake is not None and payout is not None
    ]
    total_stake = sum(stake for stake, _ in valid)
    total_payout = sum(payout for _, payout in valid)
    net_profit = total_payout - total_stake
    return {
        "rows": len(selected),
        "priced_rows": len(valid),
        "stake": round(total_stake, 2),
        "payout": round(total_payout, 2),
        "net_profit": round(net_profit, 2),
        "roi": round(net_profit / total_stake, 6) if total_stake else None,
    }


def audit_betting_ledger(ledger_path: str | Path) -> dict[str, Any]:
    path = Path(ledger_path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    issues: list[dict[str, Any]] = []
    plan_rows: dict[str, list[int]] = defaultdict(list)
    semantic_rows: dict[tuple[str, str, str], list[int]] = defaultdict(list)

    for row_number, row in enumerate(rows, start=2):
        plan_id = _text(row.get("plan_id"))
        result = _text(row.get("result"))
        if not plan_id:
            issues.append({"severity": "error", "code": "missing_plan_id", "row": row_number})
        else:
            plan_rows[plan_id].append(row_number)

        if result not in PENDING_RESULTS | SETTLED_RESULTS | ARCHIVED_RESULTS:
            issues.append(
                {
                    "severity": "error",
                    "code": "unknown_result",
                    "row": row_number,
                    "plan_id": plan_id,
                    "value": result,
                }
            )

        stake = _number(row.get("stake"))
        if stake is None or stake <= 0:
            issues.append(
                {"severity": "error", "code": "invalid_stake", "row": row_number, "plan_id": plan_id}
            )

        semantic_key = (
            _text(row.get("date")),
            _normalized_selections(row.get("selections")),
            f"{stake:.2f}" if stake is not None else "",
        )
        if semantic_key[0] and semantic_key[1]:
            semantic_rows[semantic_key].append(row_number)

        if result in SETTLED_RESULTS:
            payout = _number(row.get("payout"))
            net_profit = _number(row.get("net_profit"))
            roi = _number(row.get("roi"))
            if payout is None or net_profit is None or roi is None:
                issues.append(
                    {
                        "severity": "error",
                        "code": "incomplete_settlement",
                        "row": row_number,
                        "plan_id": plan_id,
                    }
                )
            elif stake is not None:
                expected_net = payout - stake
                expected_roi = expected_net / stake
                if abs(net_profit - expected_net) > 0.011:
                    issues.append(
                        {
                            "severity": "error",
                            "code": "net_profit_mismatch",
                            "row": row_number,
                            "plan_id": plan_id,
                            "expected": round(expected_net, 4),
                            "actual": net_profit,
                        }
                    )
                if abs(roi - expected_roi) > 0.00011:
                    issues.append(
                        {
                            "severity": "error",
                            "code": "roi_mismatch",
                            "row": row_number,
                            "plan_id": plan_id,
                            "expected": round(expected_roi, 6),
                            "actual": roi,
                        }
                    )

    for plan_id, row_numbers in plan_rows.items():
        if len(row_numbers) > 1:
            issues.append(
                {
                    "severity": "error",
                    "code": "duplicate_plan_id",
                    "plan_id": plan_id,
                    "rows": row_numbers,
                }
            )

    semantic_duplicate_groups: list[dict[str, Any]] = []
    archived_duplicate_groups: list[dict[str, Any]] = []
    for (date, selections, stake), row_numbers in semantic_rows.items():
        if len(row_numbers) < 2:
            continue
        group_rows = [rows[row_number - 2] for row_number in row_numbers]
        group = {
            "date": date,
            "stake": float(stake),
            "rows": row_numbers,
            "plan_ids": [_text(row.get("plan_id")) for row in group_rows],
            "results": [_text(row.get("result")) for row in group_rows],
            "selections": _text(group_rows[0].get("selections")),
        }
        archived = [row for row in group_rows if _text(row.get("result")) in ARCHIVED_RESULTS]
        if archived:
            archived_duplicate_groups.append(group)
        else:
            semantic_duplicate_groups.append(group)
            issues.append({"severity": "warning", "code": "semantic_duplicate", **group})
        pending = [row for row in group_rows if _text(row.get("result")) in PENDING_RESULTS]
        settled = [row for row in group_rows if _text(row.get("result")) in SETTLED_RESULTS]
        if pending and settled:
            issues.append(
                {
                    "severity": "warning",
                    "code": "pending_superseded_by_settled",
                    "date": date,
                    "pending_plan_ids": [_text(row.get("plan_id")) for row in pending],
                    "settled_plan_ids": [_text(row.get("plan_id")) for row in settled],
                }
            )

    settled_rows = [row for row in rows if _text(row.get("result")) in SETTLED_RESULTS]
    binary_rows = [row for row in rows if _text(row.get("result")) in BINARY_RESULTS]
    partial_rows = [row for row in rows if _text(row.get("result")) in {"部分命中", "partial"}]
    pending_rows = [row for row in rows if _text(row.get("result")) in PENDING_RESULTS]
    archived_rows = [row for row in rows if _text(row.get("result")) in ARCHIVED_RESULTS]
    severity_counts = Counter(issue["severity"] for issue in issues)
    return {
        "ledger": str(path),
        "rows": len(rows),
        "status_counts": dict(Counter(_text(row.get("result")) or "空白" for row in rows)),
        "pending_plan_ids": [_text(row.get("plan_id")) for row in pending_rows],
        "archived_plan_ids": [_text(row.get("plan_id")) for row in archived_rows],
        "financials": {
            "all_settled": _financial_summary(settled_rows),
            "binary_only": _financial_summary(binary_rows),
            "partial_only": _financial_summary(partial_rows),
        },
        "semantic_duplicate_groups": semantic_duplicate_groups,
        "archived_duplicate_groups": archived_duplicate_groups,
        "issue_counts": {
            "errors": severity_counts["error"],
            "warnings": severity_counts["warning"],
        },
        "issues": issues,
    }


def render_audit_markdown(audit: dict[str, Any]) -> str:
    settled = audit["financials"]["all_settled"]
    binary = audit["financials"]["binary_only"]
    lines = [
        "# 投注台账一致性审计",
        "",
        f"- 台账：`{audit['ledger']}`",
        f"- 总记录：{audit['rows']}",
        f"- 状态分布：{json.dumps(audit['status_counts'], ensure_ascii=False)}",
        f"- 问题：{audit['issue_counts']['errors']} 个错误，{audit['issue_counts']['warnings']} 个警告",
        "",
        "## 财务口径",
        "",
        f"- 全部已结算：投注 {settled['stake']:.2f}，返奖 {settled['payout']:.2f}，净收益 {settled['net_profit']:.2f}，ROI {settled['roi']:.2%}",
        f"- 仅二元命中/未中：投注 {binary['stake']:.2f}，返奖 {binary['payout']:.2f}，净收益 {binary['net_profit']:.2f}，ROI {binary['roi']:.2%}",
        "",
        "## 待处理项",
        "",
    ]
    if not audit["issues"]:
        lines.append("- 未发现问题。")
    for issue in audit["issues"]:
        code = issue["code"]
        if code == "pending_superseded_by_settled":
            lines.append(
                f"- [警告] 待赛方案 {', '.join(issue['pending_plan_ids'])} 已有对应结算方案 "
                f"{', '.join(issue['settled_plan_ids'])}；建议人工确认后归档前者。"
            )
        elif code == "semantic_duplicate":
            lines.append(f"- [警告] 同日同选项同投注额重复：{', '.join(issue['plan_ids'])}。")
        else:
            location = f"（第 {issue['row']} 行）" if "row" in issue else ""
            lines.append(f"- [{issue['severity']}] {code}{location}：{issue.get('plan_id', '')}")
    return "\n".join(lines) + "\n"
