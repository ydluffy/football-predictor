"""Build the detailed 2026-09-16 review from frozen finals and official results."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-09-16"
RESULTS = ROOT / "data/manual/sporttery_results_2026-09-16.csv"
LEDGER = ROOT / "data/manual/betting_plan_ledger.csv"
FIXED = ROOT / "data/manual/fixed_odds_shadow_ledger.csv"
REPORT = ROOT / "artifacts/reviews/sporttery_full_review_2026-09-16_1300_detailed.md"
AUDIT = ROOT / "artifacts/data/sporttery_full_review_2026-09-16_1300_detailed.json"
FINALS = [
    ROOT / "artifacts/data/sporttery_final_analysis_2026-09-16_1610_001-003.json",
    ROOT / "artifacts/data/sporttery_final_analysis_2026-09-16_2122_004-017.json",
]


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def normalize_spf(value: object) -> str:
    text = str(value or "")
    return {"主胜": "胜", "客胜": "负", "H": "胜", "A": "负", "D": "平"}.get(text, text)


def selection(value: object) -> str:
    return str(value.get("selection") or value.get("pick_label") or "") if isinstance(value, dict) else str(value or "")


def choices(value: object) -> list[str]:
    if isinstance(value, list):
        return [selection(item) if isinstance(item, dict) else str(item[0] if isinstance(item, list) and item else item) for item in value]
    return re.findall(r"(?:^|/)([^/@]+)@", str(value or ""))


def settle_scheme(text: str, official: dict[str, dict[str, str]]) -> tuple[str, list[str]]:
    notes: list[str] = []
    unresolved = False
    hit = True
    legs = [item.strip() for item in re.split(r"\s+\+\s+", text) if item.strip()]
    if not legs:
        return "pending", ["无法解析选择"]
    for leg in legs:
        number_match = re.match(r"(\d{3})", leg)
        picks = re.findall(r"(让胜|让平|让负|主胜|客胜|平)(?=@|$)", leg)
        if not number_match or not picks:
            unresolved = True
            notes.append(f"{leg}=无法解析")
            continue
        number, pick = number_match.group(1), picks[-1]
        if number not in official:
            unresolved = True
            notes.append(f"{number}{pick}=官方赛果待补")
            continue
        actual = official[number]["rqspf_result"] if pick.startswith("让") else normalize_spf(official[number]["spf_result"])
        expected = pick if pick.startswith("让") else normalize_spf(pick)
        leg_hit = expected == actual
        hit &= leg_hit
        notes.append(f"{number}{pick}→{actual}{'✓' if leg_hit else '✗'}")
    if not hit:
        return "miss", notes
    return ("pending" if unresolved else "hit"), notes


def main() -> None:
    official = {
        row["match_number"][-3:]: row
        for row in csv_rows(RESULTS)
        if row["match_number"].startswith("周三") and "001" <= row["match_number"][-3:] <= "017"
    }
    finals = [json.loads(path.read_text(encoding="utf-8")) for path in FINALS]
    predictions = {item["number"]: item for batch in finals for item in batch["matches"]}
    expected = {f"{number:03d}" for number in range(1, 18)}
    missing_results = sorted(expected - set(official))
    missing_predictions = sorted(expected - set(predictions))
    metrics = {key: 0 for key in ("spf_primary", "spf_covered", "rq_primary", "goals_primary", "goals_covered", "score_covered", "half_full_covered")}
    per_match: list[dict[str, object]] = []
    for number in sorted(expected):
        pred = predictions.get(number, {})
        result = official.get(number)
        if not result:
            per_match.append({"number": number, "match": f"{pred.get('home', '')} vs {pred.get('away', '')}", "status": "official_result_pending"})
            continue
        score, half = result["full_time_score"], result["half_time_score"]
        actual_spf = normalize_spf(result["spf_result"])
        primary, defense = selection(pred.get("primary")), selection(pred.get("defense"))
        rq_pick = selection(pred.get("rq_primary") or pred.get("rq_pick"))
        goal_list, score_list, half_list = choices(pred.get("goals")), choices(pred.get("scores")), choices(pred.get("half_full"))
        goals = sum(int(value) for value in score.split(":"))
        h1, h2 = (int(value) for value in half.split(":")); f1, f2 = (int(value) for value in score.split(":"))
        half_full = ("胜" if h1 > h2 else "负" if h1 < h2 else "平") + ("胜" if f1 > f2 else "负" if f1 < f2 else "平")
        checks = {
            "spf_primary": normalize_spf(primary) == actual_spf,
            "spf_covered": actual_spf in {normalize_spf(primary), normalize_spf(defense)},
            "rq_primary": rq_pick == result["rqspf_result"],
            "goals_primary": bool(goal_list) and goal_list[0] == str(goals),
            "goals_covered": str(goals) in goal_list,
            "score_covered": score in score_list,
            "half_full_covered": half_full in half_list,
        }
        for key, value in checks.items(): metrics[key] += bool(value)
        per_match.append({
            "number": number, "competition": result["competition"], "match": f"{result['home_team']} vs {result['away_team']}",
            "half": half, "score": score, "spf": actual_spf, "rqspf": result["rqspf_result"],
            "primary": primary, "defense": defense, "rq_pick": rq_pick, "goals": "/".join(goal_list),
            "scores": "/".join(score_list), "half_full": "/".join(half_list), "actual_goals": goals,
            "actual_half_full": half_full, **checks, "status": "settled",
        })

    formal = [row for row in csv_rows(LEDGER) if row.get("date") == DAY]
    fixed = [row for row in csv_rows(FIXED) if row.get("date") == DAY]
    def amount(row: dict[str, str], key: str) -> float: return float(row.get(key) or 0)
    formal_stake, formal_payout = sum(amount(row, "stake") for row in formal), sum(amount(row, "payout") for row in formal)
    fixed_stake, fixed_payout = sum(amount(row, "stake") for row in fixed), sum(amount(row, "payout") for row in fixed)
    displayed: list[dict[str, object]] = []
    for batch in finals:
        for index, plan in enumerate(batch.get("shadow_schemes") or [], 1):
            text = str(plan.get("selections") or plan.get("selection") or "")
            status, notes = settle_scheme(text, official)
            stake = float(plan.get("stake") or 0); odds = float(plan.get("odds_min") or plan.get("omin") or 0)
            payout = stake * odds if status == "hit" else 0.0
            displayed.append({"batch": batch["scope"], "id": plan.get("plan_id") or plan.get("id") or index,
                              "type": plan.get("plan_type") or plan.get("type") or "影子", "selection": text,
                              "stake": stake, "odds": odds, "result": status, "payout": round(payout, 2),
                              "net": round(payout-stake, 2) if status != "pending" else None, "notes": "；".join(notes)})
    settled_shadow = [item for item in displayed if item["result"] != "pending"]
    shadow_stake = sum(float(item["stake"]) for item in settled_shadow); shadow_payout = sum(float(item["payout"]) for item in settled_shadow)
    reviewed_at = datetime.now().astimezone().replace(microsecond=0).isoformat()
    audit = {
        "schema_version": 1, "sales_day": DAY, "status": "completed_partial_official_result" if missing_results else "completed",
        "reviewed_at": reviewed_at, "official_result_count": len(official), "prediction_count": len(predictions),
        "missing_official_results": missing_results, "missing_predictions": missing_predictions, "metrics": metrics,
        "formal": {"count": len(formal), "hits": sum(row.get("result") == "命中" for row in formal), "stake": formal_stake,
                   "payout": formal_payout, "net": formal_payout-formal_stake, "roi": (formal_payout-formal_stake)/formal_stake if formal_stake else None},
        "fixed_shadow": {"count": len(fixed), "stake": fixed_stake, "payout": fixed_payout,
                         "net": fixed_payout-fixed_stake, "roi": (fixed_payout-fixed_stake)/fixed_stake if fixed_stake else None},
        "displayed_shadow": {"count": len(displayed), "settled": len(settled_shadow), "hits": sum(item["result"] == "hit" for item in settled_shadow),
                             "stake": shadow_stake, "payout": shadow_payout, "net": shadow_payout-shadow_stake,
                             "roi": (shadow_payout-shadow_stake)/shadow_stake if shadow_stake else None},
        "per_match": per_match, "displayed_shadow_plans": displayed,
        "source_results": str(RESULTS.relative_to(ROOT)), "source_final_reports": [str(path.relative_to(ROOT)) for path in FINALS],
        "production_ledger_sha256": hashlib.sha256(LEDGER.read_bytes()).hexdigest(), "production_ledger_write_performed": False,
        "supabase_sync": "not_authorized_for_2026-09-16",
    }
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    total = len(official); mark = lambda value: "命中" if value else "未中"
    lines = ["# 2026-09-16 销售日详细复盘", "", f"- 复盘时间：{reviewed_at}。",
             f"- 中国体彩官方90分钟赛果覆盖：{total}/17；待补：{','.join(missing_results) or '无'}。",
             f"- 已结算场次SPF主选：{metrics['spf_primary']}/{total}；主选+防守覆盖：{metrics['spf_covered']}/{total}；让球主选：{metrics['rq_primary']}/{total}。",
             f"- 总进球首选：{metrics['goals_primary']}/{total}；多选覆盖：{metrics['goals_covered']}/{total}；比分覆盖：{metrics['score_covered']}/{total}；半全场覆盖：{metrics['half_full_covered']}/{total}。",
             "", "## 逐场核实", "", "|编号|赛事|比赛|半/全场|SPF主选|防守覆盖|让球主选|进球/比分/半全场|",
             "|---|---|---|---|---|---|---|---|"]
    for item in per_match:
        if item["status"] != "settled":
            lines.append(f"|{item['number']}|-|{item['match']}|待官方赛果|待结算|待结算|待结算|待结算|"); continue
        lines.append(f"|{item['number']}|{item['competition']}|{item['match']}|{item['half']} / {item['score']}|{item['primary']}→{item['spf']} {mark(item['spf_primary'])}|{item['defense']} {mark(item['spf_covered'])}|{item['rq_pick']}→{item['rqspf']} {mark(item['rq_primary'])}|{item['goals']}→{item['actual_goals']} / {item['scores']}→{item['score']} / {item['half_full']}→{item['actual_half_full']}|")
    formal_roi = (formal_payout-formal_stake)/formal_stake*100 if formal_stake else 0
    shadow_roi = (shadow_payout-shadow_stake)/shadow_stake*100 if shadow_stake else 0
    lines += ["", "## 方案与资金复盘", "",
              f"- 正式方案：{len(formal)}组，{sum(row.get('result') == '命中' for row in formal)}/{len(formal)}命中；投入{formal_stake:.2f}元、返奖{formal_payout:.2f}元、净收益{formal_payout-formal_stake:.2f}元，ROI {formal_roi:.2f}%。",
              f"- 固定赔率独立影子台账：{len(fixed)}组；投入{fixed_stake:.2f}元、返奖{fixed_payout:.2f}元、净收益{fixed_payout-fixed_stake:.2f}元。",
              f"- 报告展示影子：共{len(displayed)}组，已结算{len(settled_shadow)}组、命中{sum(item['result']=='hit' for item in settled_shadow)}组；已结算虚拟投入{shadow_stake:.2f}元、返奖{shadow_payout:.2f}元、净收益{shadow_payout-shadow_stake:.2f}元，ROI {shadow_roi:.2f}%。",
              "", "## 展示影子逐组结算", "", "|批次|方案|选择|虚拟投入|结果|返奖|净收益|", "|---|---|---|---:|---|---:|---:|"]
    for item in displayed:
        net = "待结算" if item["net"] is None else f"{float(item['net']):.2f}"
        lines.append(f"|{item['batch']}|{item['type']}|{item['selection']}|{float(item['stake']):.2f}|{item['result']}|{float(item['payout']):.2f}|{net}|")
    lines += ["", "## 复盘结论", "", "- 正式稳健方案首腿马竞主胜命中，但塞尔塔客胜未中，整票结算未中。",
              "- 014官方赛果当前缺失，涉及014的影子组合保持待结算，不按失败处理。",
              "- 本销售日未授权Supabase同步，只保存本地审计。", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": audit["status"], "official": len(official), "missing": missing_results, "formal": audit["formal"], "report": str(REPORT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
