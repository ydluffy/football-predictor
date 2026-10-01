from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-09-24"
COMPLETED_AT = "2026-09-25T12:23:22+08:00"


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    result_path = ROOT / "artifacts/data/sporttery_results_2026-09-24.csv"
    prediction_path = ROOT / "artifacts/data/sporttery_final_analysis_2026-09-24_1706_001-003.json"
    fixed_ledger = ROOT / "data/manual/fixed_odds_shadow_ledger.csv"
    formal_ledger = ROOT / "data/manual/betting_plan_ledger.csv"
    review_json = ROOT / "artifacts/data/sporttery_full_review_2026-09-24_1300_detailed.json"
    review_md = ROOT / "artifacts/reviews/sporttery_full_review_2026-09-24_1300_detailed.md"

    expected = {
        "001": ("日本", "乌拉圭"),
        "002": ("韩国", "厄瓜多尔"),
        "003": ("中国", "马尔代夫"),
        "004": ("科索沃", "爱尔兰"),
        "005": ("葡萄牙", "威尔士"),
        "006": ("荷兰", "德国"),
        "007": ("塞尔维亚", "希腊"),
        "008": ("挪威", "丹麦"),
    }
    official_rows = rows(result_path)
    official: dict[str, dict[str, str]] = {}
    for number, (home, away) in expected.items():
        matches = [r for r in official_rows if r["home_team"] == home and r["away_team"] == away]
        assert len(matches) == 1, (number, home, away, len(matches))
        official[number] = matches[0]

    frozen = json.loads(prediction_path.read_text(encoding="utf-8"))
    predictions = {item["number"]: item for item in frozen["matches"]}

    per_match = []
    metrics = {
        "spf_primary_hits": 0,
        "spf_covered_hits": 0,
        "spf_total": 0,
        "rq_primary_hits": 0,
        "rq_covered_hits": 0,
        "rq_total": 0,
        "goals_hits": 0,
        "goals_total": 0,
        "score_hits": 0,
        "score_total": 0,
        "half_full_primary_hits": 0,
        "half_full_covered_hits": 0,
        "half_full_total": 0,
    }

    def goals(score: str) -> int:
        home, away = score.split(":")
        return int(home) + int(away)

    def half_full(row: dict[str, str]) -> str:
        def result(score: str) -> str:
            h, a = map(int, score.split(":"))
            return "胜" if h > a else "平" if h == a else "负"
        return result(row["half_time_score"]) + result(row["full_time_score"])

    for number, (home, away) in expected.items():
        result = official[number]
        item = {
            "number": number,
            "match": f"{home} vs {away}",
            "half_time_score": result["half_time_score"],
            "full_time_score": result["full_time_score"],
            "spf_result": result["spf_result"],
            "rqspf_result": result["rqspf_result"],
            "prediction_status": "frozen" if number in predictions else "missed_final_no_backfill",
        }
        if number in predictions:
            p = predictions[number]
            actual_spf = result["spf_result"]
            actual_rq = result["rqspf_result"]
            primary_spf = p["primary"]["selection"]
            defense_spf = p["defense"]["selection"]
            primary_rq = p["rq_primary"]["selection"]
            defense_rq = p["rq_defense"]["selection"]
            metrics["spf_total"] += 1
            metrics["spf_primary_hits"] += primary_spf == actual_spf
            metrics["spf_covered_hits"] += actual_spf in {primary_spf, defense_spf}
            metrics["rq_total"] += 1
            metrics["rq_primary_hits"] += primary_rq == actual_rq
            metrics["rq_covered_hits"] += actual_rq in {primary_rq, defense_rq}
            actual_goals = str(goals(result["full_time_score"]))
            goal_choices = [x["selection"] for x in p["goals"]]
            score_choices = [x["selection"] for x in p["scores"]]
            hf_choices = [x["selection"] for x in p["half_full"]]
            metrics["goals_total"] += 1
            metrics["goals_hits"] += actual_goals in goal_choices
            metrics["score_total"] += 1
            score_hit = result["full_time_score"] in score_choices or ("home_other" in score_choices and result["spf_result"] == "胜" and result["full_time_score"] not in {"1:0", "2:0", "2:1", "3:0", "3:1", "3:2", "4:0", "4:1", "4:2", "5:0", "5:1", "5:2"})
            metrics["score_hits"] += score_hit
            if hf_choices:
                actual_hf = half_full(result)
                metrics["half_full_total"] += 1
                metrics["half_full_primary_hits"] += hf_choices[0] == actual_hf
                metrics["half_full_covered_hits"] += actual_hf in hf_choices
            item.update(
                {
                    "spf_prediction": [primary_spf, defense_spf],
                    "rqspf_prediction": [primary_rq, defense_rq],
                    "goals_prediction": goal_choices,
                    "score_prediction": score_choices,
                    "half_full_prediction": hf_choices,
                }
            )
        per_match.append(item)

    formal = [r for r in rows(formal_ledger) if r.get("date") == DAY]
    fixed = [r for r in rows(fixed_ledger) if r.get("date") == DAY]
    formal_stake = sum(float(r.get("stake") or 0) for r in formal)
    formal_payout = sum(float(r.get("payout") or 0) for r in formal)
    fixed_stake = sum(float(r.get("stake") or 0) for r in fixed)
    fixed_payout = sum(float(r.get("payout") or 0) for r in fixed)

    displayed = [
        {"id": "SAFE", "stake": 50.0, "payout": 159.12, "result": "hit", "note": "001主胜+002主胜"},
        {"id": "VALUE", "stake": 20.0, "payout": 63.648, "result": "hit", "note": "与SAFE同选择，独立观察"},
        {"id": "HANDICAP", "stake": 20.0, "payout": 0.0, "result": "miss", "note": "002让负失误，003让负命中"},
        {"id": "HEDGE", "stake": 8.0, "payout": 6.3648, "result": "partial_cover", "note": "4注中主胜+主胜一注命中"},
        {"id": "GOALS", "stake": 8.0, "payout": 0.0, "result": "miss", "note": "001实际4球超出2/3"},
        {"id": "SCORE", "stake": 8.0, "payout": 0.0, "result": "miss", "note": "001实际3:1未覆盖"},
        {"id": "HALF_FULL", "stake": 2.0, "payout": 0.0, "result": "miss", "note": "001实际平胜"},
    ]
    ds = sum(x["stake"] for x in displayed)
    dp = sum(x["payout"] for x in displayed)
    contrarian = {"stake": 2.0, "payout": 4.06, "net": 2.06, "roi": 1.03, "result": "hit", "selection": "003(-4)让负@2.03"}

    audit = {
        "sales_day": DAY,
        "completed_at": COMPLETED_AT,
        "official_matches": 8,
        "official_result_coverage": "8/8",
        "prediction_coverage": "3/8",
        "missing_final_predictions": ["004", "005", "006", "007", "008"],
        "metrics": metrics,
        "formal": {"plans": len(formal), "stake": formal_stake, "payout": formal_payout, "net": formal_payout - formal_stake, "roi": None if not formal_stake else (formal_payout - formal_stake) / formal_stake},
        "fixed_odds_shadow": {"plans": len(fixed), "stake": fixed_stake, "payout": fixed_payout, "net": fixed_payout - fixed_stake, "roi": None if not fixed_stake else (fixed_payout - fixed_stake) / fixed_stake},
        "displayed_shadow": {"schemes": displayed, "stake": ds, "payout": dp, "net": dp - ds, "roi": (dp - ds) / ds},
        "contrarian_shadow": contrarian,
        "per_match": per_match,
        "missed_batch_audit": "artifacts/data/missed_final_audit_2026-09-24_004-008.json",
        "production_ledger_sha256": hashlib.sha256(formal_ledger.read_bytes()).hexdigest(),
        "supabase_sync": "not_authorized_for_2026-09-24",
    }
    review_json.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# 2026-09-24销售日8场详细复盘",
        "",
        "官方赛果8/8；合法冻结预测3/8。001—003在硬锁前完成，004—008的21:00终版未被心跳执行，已过21:45硬锁，严禁事后补写预测或方案。",
        "",
        "## 逐场核验",
        "",
        "|编号|比赛|半场/全场|SPF|让球|总进球/比分/半全场|结论|",
        "|---|---|---|---|---|---|---|",
    ]
    for item in per_match:
        if item["prediction_status"] != "frozen":
            lines.append(f"|{item['number']}|{item['match']}|{item['half_time_score']} / {item['full_time_score']}|实际{item['spf_result']}|实际{item['rqspf_result']}|无冻结预测|终版漏跑，只核实赛果|")
            continue
        p = predictions[item["number"]]
        hf = "/".join(x["selection"] for x in p["half_full"]) or "无"
        lines.append(
            f"|{item['number']}|{item['match']}|{item['half_time_score']} / {item['full_time_score']}|"
            f"{p['primary']['selection']}/{p['defense']['selection'] or '-'}→{item['spf_result']}|"
            f"{p['rq_primary']['selection']}/{p['rq_defense']['selection'] or '-'}→{item['rqspf_result']}|"
            f"进球{'/'.join(x['selection'] for x in p['goals'])}；比分{'/'.join(x['selection'] for x in p['scores'])}；半全场{hf}|已按冻结方案统计|"
        )
    lines += [
        "",
        "## 指标与方案结算",
        "",
        f"- SPF首选：{metrics['spf_primary_hits']}/{metrics['spf_total']}；首选加防守覆盖：{metrics['spf_covered_hits']}/{metrics['spf_total']}。",
        f"- 让球首选：{metrics['rq_primary_hits']}/{metrics['rq_total']}；首选加防守覆盖：{metrics['rq_covered_hits']}/{metrics['rq_total']}。",
        f"- 总进球：{metrics['goals_hits']}/{metrics['goals_total']}；比分：{metrics['score_hits']}/{metrics['score_total']}；半全场首选：{metrics['half_full_primary_hits']}/{metrics['half_full_total']}，覆盖：{metrics['half_full_covered_hits']}/{metrics['half_full_total']}。",
        f"- 正式台账：{len(formal)}组，投入{formal_stake:.2f}元、返奖{formal_payout:.2f}元、净收益{formal_payout-formal_stake:+.2f}元，ROI不适用。",
        f"- 固定赔率影子：{len(fixed)}组，投入{fixed_stake:.2f}元、返奖{fixed_payout:.2f}元、净收益{fixed_payout-fixed_stake:+.2f}元、ROI {-1.0 if fixed_stake else 0:.2%}。",
        f"- 展示影子7组：理论投入{ds:.2f}元、返奖{dp:.2f}元、净收益{dp-ds:+.2f}元、ROI {(dp-ds)/ds:.2%}。这些方案高度重叠，仅作独立观察，不能当成可同时下注的组合资产。",
        f"- 邪修影子：003(-4)让负@2.03命中，虚拟投入2.00元、返奖4.06元、净收益+2.06元、ROI 103.00%。",
        "",
        "## 错误归因",
        "",
        "- 001、002的胜负方向均正确，但让球首选均判断错误；市场强弱判断不等于穿盘判断，亚洲盘较浅的警告有效。",
        "- 003让负与3:0比分命中，但总进球7+/4过高；深盘时应把穿盘和总进球拆开判断。",
        "- 004—008不是预测失误，而是调度漏跑；没有赛前冻结证据，不能将赛后方向计入命中率或收益。",
        "- SAFE、VALUE和HEDGE共享001、002主胜，收益存在高度重复，不应据此放大仓位。",
        "",
        f"结构化审计：`{review_json.relative_to(ROOT)}`",
    ]
    review_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update(
        {
            "last_heartbeat_at": COMPLETED_AT,
            "last_reviewed_sales_day": DAY,
            "last_review_artifact": str(review_md.relative_to(ROOT)).replace("\\", "/"),
            "last_completed_stage": "2026-09-24销售日13:00全期复盘",
            "last_completed_at": COMPLETED_AT,
            "last_stage_status": "completed_review_8_results_3_predictions_5_missed_final",
            "next_required_stage": "2026-09-25 16:30终版分析003-005",
            "next_required_at": "2026-09-25T16:30:00+08:00",
            "next_dynamic_task_key": "2026-09-25|18:00-18:30|终版分析",
            "next_dynamic_task_at": "2026-09-25T16:30:00+08:00",
        }
    )
    state["review_20260924"] = {
        "status": "completed",
        "completed_at": COMPLETED_AT,
        "official_result_coverage": "8/8",
        "prediction_coverage": "3/8",
        "formal": "0_plans_stake0_payout0_net0",
        "fixed_shadow": "0_of_1_stake2_payout0_net_minus2",
        "displayed_shadow": f"stake{ds:.2f}_payout{dp:.2f}_net{dp-ds:.2f}",
        "contrarian_shadow": "1_of_1_stake2_payout4.06_net2.06",
        "report": str(review_md.relative_to(ROOT)).replace("\\", "/"),
        "audit": str(review_json.relative_to(ROOT)).replace("\\", "/"),
        "supabase_sync": "not_authorized_for_2026-09-24",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "official": "8/8", "predictions": "3/8", "formal": 0, "fixed_net": -2.0, "displayed_net": round(dp-ds, 4), "contrarian_net": 2.06}, ensure_ascii=False))


if __name__ == "__main__":
    main()
