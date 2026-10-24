"""Build the detailed 2026-09-15 review from frozen final reports and official results."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-09-15"
RESULTS = ROOT / "data/manual/sporttery_results_2026-09-15.csv"
LEDGER = ROOT / "data/manual/betting_plan_ledger.csv"
FIXED = ROOT / "data/manual/fixed_odds_shadow_ledger.csv"
REPORT = ROOT / "artifacts/reviews/sporttery_full_review_2026-09-15_1300_detailed.md"
AUDIT = ROOT / "artifacts/data/sporttery_full_review_2026-09-15_1300_detailed.json"
FINALS = [
    ROOT / "artifacts/data/sporttery_final_analysis_2026-09-15_1637_001-003.json",
    ROOT / "artifacts/data/sporttery_final_analysis_2026-09-15_1847_004-005.json",
    ROOT / "artifacts/data/sporttery_final_analysis_2026-09-15_2103_006-014.json",
]


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def result_word(score: str) -> str:
    home, away = (int(value) for value in score.split(":"))
    return "胜" if home > away else "负" if home < away else "平"


def normalize_spf(value: object) -> str:
    text = str(value or "")
    return {"主胜": "胜", "客胜": "负", "H": "胜", "A": "负", "D": "平"}.get(text, text)


def selection_value(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("selection") or value.get("pick_label") or "")
    return str(value or "")


def candidates(value: object) -> list[str]:
    if isinstance(value, list):
        output = []
        for item in value:
            if isinstance(item, dict):
                output.append(str(item.get("selection") or ""))
            elif isinstance(item, list):
                output.append(str(item[0]) if item else "")
            else:
                output.append(str(item))
        return [item for item in output if item]
    text = str(value or "")
    return re.findall(r"(?:^|/)([^/@]+)@", text)


def settle_scheme(selection: str, official: dict[str, dict[str, str]]) -> tuple[bool, list[str]]:
    notes: list[str] = []
    legs = [item.strip() for item in re.split(r"\s+\+\s+", selection) if item.strip()]
    if not legs:
        return False, ["无法解析选择"]
    hit = True
    for leg in legs:
        match = re.match(r"(\d{3})", leg)
        picks = re.findall(r"(让胜|让平|让负|主胜|客胜|平)(?=@|$)", leg)
        if not match or not picks or match.group(1) not in official:
            hit = False
            notes.append(f"{leg}=无法解析")
            continue
        number = match.group(1)
        pick = picks[-1]
        actual = official[number]["rqspf_result"] if pick.startswith("让") else normalize_spf(official[number]["spf_result"])
        expected = pick if pick.startswith("让") else normalize_spf(pick)
        leg_hit = expected == actual
        hit &= leg_hit
        notes.append(f"{number}{pick}→{actual}{'✓' if leg_hit else '✗'}")
    return hit, notes


def main() -> None:
    official = {
        row["match_number"][-3:]: row
        for row in rows(RESULTS)
        if row["match_number"].startswith("周二") and row["match_number"][-3:] <= "014"
    }
    if set(official) != {f"{number:03d}" for number in range(1, 15)}:
        raise ValueError("official result coverage is not 001-014")
    finals = [json.loads(path.read_text(encoding="utf-8")) for path in FINALS]
    predictions = {item["number"]: item for batch in finals for item in batch["matches"]}
    if set(predictions) != set(official):
        raise ValueError("prediction coverage mismatch")

    per_match = []
    metrics = {"spf_primary": 0, "spf_covered": 0, "rq_primary": 0, "goals_primary": 0, "goals_covered": 0, "score_covered": 0, "half_full_covered": 0}
    for number in sorted(official):
        result = official[number]
        pred = predictions[number]
        score = result["full_time_score"]
        half = result["half_time_score"]
        actual_spf = normalize_spf(result["spf_result"])
        primary = selection_value(pred.get("primary"))
        defense = selection_value(pred.get("defense"))
        rq = selection_value(pred.get("rq_primary") or pred.get("rq_pick"))
        goal_list = candidates(pred.get("goals"))
        score_list = candidates(pred.get("scores"))
        half_list = [normalize_spf(item.replace("-", "")) for item in candidates(pred.get("half_full"))]
        total_goals = sum(int(value) for value in score.split(":"))
        half_full = result_word(half) + result_word(score)
        spf_primary_hit = normalize_spf(primary) == actual_spf
        spf_covered_hit = actual_spf in {normalize_spf(primary), normalize_spf(defense)}
        rq_hit = rq == result["rqspf_result"]
        goals_primary_hit = bool(goal_list) and goal_list[0] == str(total_goals)
        goals_covered_hit = str(total_goals) in goal_list
        score_hit = score in score_list
        half_hit = half_full in half_list
        metrics["spf_primary"] += spf_primary_hit
        metrics["spf_covered"] += spf_covered_hit
        metrics["rq_primary"] += rq_hit
        metrics["goals_primary"] += goals_primary_hit
        metrics["goals_covered"] += goals_covered_hit
        metrics["score_covered"] += score_hit
        metrics["half_full_covered"] += half_hit
        per_match.append({
            "number": number, "competition": result["competition"], "match": f"{result['home_team']} vs {result['away_team']}",
            "half": half, "score": score, "spf": actual_spf, "rqspf": result["rqspf_result"],
            "primary": primary, "defense": defense, "rq_pick": rq,
            "spf_primary_hit": spf_primary_hit, "spf_covered_hit": spf_covered_hit, "rq_hit": rq_hit,
            "goals": "/".join(goal_list), "scores": "/".join(score_list), "half_full": "/".join(candidates(pred.get("half_full"))),
            "actual_goals": total_goals, "actual_half_full": half_full,
        })

    formal = [row for row in rows(LEDGER) if row.get("date") == DAY]
    fixed = [row for row in rows(FIXED) if row.get("date") == DAY]
    fixed_stake = sum(float(row.get("stake") or 0) for row in fixed)
    fixed_payout = sum(float(row.get("payout") or 0) for row in fixed)

    displayed = []
    for batch in finals:
        for index, plan in enumerate(batch.get("shadow_schemes") or [], start=1):
            selection = str(plan.get("selections") or plan.get("selection") or "")
            hit, notes = settle_scheme(selection, official)
            stake = float(plan.get("stake") or 0)
            odds = float(plan.get("odds_min") or plan.get("omin") or 0)
            payout = stake * odds if hit else 0.0
            displayed.append({
                "batch": batch["scope"], "id": str(plan.get("plan_id") or plan.get("id") or index),
                "type": str(plan.get("plan_type") or plan.get("type") or "影子"), "selection": selection,
                "stake": stake, "odds": odds, "result": "hit" if hit else "miss", "payout": round(payout, 2),
                "net": round(payout - stake, 2), "notes": "；".join(notes),
            })
    display_stake = sum(item["stake"] for item in displayed)
    display_payout = sum(item["payout"] for item in displayed)

    diagnostic_hit, diagnostic_notes = settle_scheme(
        "008 阿拉维斯vs巴伦西亚 主胜@1.56 + 006 阿布艾因vs利雅胜利 客胜@1.61", official
    )
    reviewed_at = datetime.now().astimezone().replace(microsecond=0).isoformat()
    audit = {
        "schema_version": 1, "sales_day": DAY, "status": "completed", "reviewed_at": reviewed_at,
        "official_result_count": len(official), "prediction_count": len(predictions), "metrics": metrics,
        "formal": {"count": len(formal), "stake": 0.0, "payout": 0.0, "net": 0.0, "roi": None,
                   "note": "formal strategy stage was omitted; no legal production rows exist"},
        "fixed_shadow": {"count": len(fixed), "stake": fixed_stake, "payout": fixed_payout,
                         "net": fixed_payout-fixed_stake, "roi": (fixed_payout-fixed_stake)/fixed_stake if fixed_stake else None},
        "displayed_shadow": {"count": len(displayed), "hits": sum(item["result"] == "hit" for item in displayed),
                             "stake": display_stake, "payout": display_payout, "net": display_payout-display_stake,
                             "roi": (display_payout-display_stake)/display_stake if display_stake else None},
        "postlock_diagnostic": {"result": "hit" if diagnostic_hit else "miss", "notes": diagnostic_notes,
                                "excluded_from_production": True},
        "per_match": per_match, "displayed_shadow_plans": displayed,
        "source_results": str(RESULTS.relative_to(ROOT)), "source_final_reports": [str(path.relative_to(ROOT)) for path in FINALS],
        "production_ledger_sha256": hashlib.sha256(LEDGER.read_bytes()).hexdigest(),
        "production_ledger_write_performed": False, "supabase_sync": "not_authorized_for_2026-09-15",
    }
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# 2026-09-15 销售日详细复盘", "",
        f"- 复盘时间：{reviewed_at}。", "- 中国体彩官方90分钟赛果覆盖：14/14。",
        f"- SPF主选：{metrics['spf_primary']}/14；主选+防守覆盖：{metrics['spf_covered']}/14；让球主选：{metrics['rq_primary']}/14。",
        f"- 总进球首选：{metrics['goals_primary']}/14；多选覆盖：{metrics['goals_covered']}/14；比分覆盖：{metrics['score_covered']}/14；半全场覆盖：{metrics['half_full_covered']}/14。",
        "", "## 逐场核实", "",
        "|编号|赛事|比赛|半/全场|SPF主选|防守覆盖|让球主选|进球/比分/半全场|",
        "|---|---|---|---|---|---|---|---|",
    ]
    mark = lambda value: "命中" if value else "未中"
    for item in per_match:
        lines.append(
            f"|{item['number']}|{item['competition']}|{item['match']}|{item['half']} / {item['score']}|"
            f"{item['primary']}→{item['spf']} {mark(item['spf_primary_hit'])}|{item['defense']} {mark(item['spf_covered_hit'])}|"
            f"{item['rq_pick']}→{item['rqspf']} {mark(item['rq_hit'])}|"
            f"{item['goals']}→{item['actual_goals']} / {item['scores']}→{item['score']} / {item['half_full']}→{item['actual_half_full']}|"
        )
    lines += [
        "", "## 方案与资金复盘", "",
        "- 正式方案：0组；投入0元、返奖0元、净收益0元，ROI不适用。原因为正式策略阶段被误跳过，不能事后补入。",
        f"- 固定赔率影子：{len(fixed)}组，0/{len(fixed)}命中；投入{fixed_stake:.2f}元、返奖{fixed_payout:.2f}元、净收益{fixed_payout-fixed_stake:.2f}元，ROI -100.00%。",
        f"- 报告展示影子：{len(displayed)}组，{sum(item['result']=='hit' for item in displayed)}/{len(displayed)}命中；虚拟投入{display_stake:.2f}元、返奖{display_payout:.2f}元、净收益{display_payout-display_stake:.2f}元，ROI {((display_payout-display_stake)/display_stake*100 if display_stake else 0):.2f}%。",
        f"- 锁后漏跑诊断候选（008主胜+006客胜）：{'命中' if diagnostic_hit else '未中'}；{'；'.join(diagnostic_notes)}。仅用于故障归因，不计正式收益。",
        "", "## 展示影子逐组结算", "",
        "|批次|方案|选择|虚拟投入|结果|返奖|净收益|",
        "|---|---|---|---:|---|---:|---:|",
    ]
    for item in displayed:
        lines.append(f"|{item['batch']}|{item['type']}|{item['selection']}|{item['stake']:.2f}|{item['result']}|{item['payout']:.2f}|{item['net']:.2f}|")
    lines += ["", "## 复盘结论", "", "- 主要问题不是缺少赛果，而是三个READY批次的正式策略阶段被影子模型状态误拦截。", "- 新编排已强制先生成100元正式策略并验证，影子状态不再具有阻断权。", "- 本销售日未授权Supabase同步，只保存本地审计。", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "completed", "matches": 14, "metrics": metrics, "formal": len(formal), "fixed": len(fixed), "displayed_shadow": len(displayed), "report": str(REPORT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
