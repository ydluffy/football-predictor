from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-09-23"
COMPLETED_AT = "2026-09-24T13:06:43+08:00"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def summarize(rows: list[dict]) -> dict:
    stake = round(sum(float(row["stake"]) for row in rows), 2)
    payout = round(sum(float(row["payout"]) for row in rows), 2)
    net = round(payout - stake, 2)
    return {
        "schemes": len(rows),
        "hits": sum(bool(row["hit"]) for row in rows),
        "stake": stake,
        "payout": payout,
        "net": net,
        "roi": round(net / stake, 6) if stake else None,
    }


def main() -> None:
    results = read_csv(ROOT / "artifacts/data/sporttery_results_2026-09-23.csv")
    wanted = {
        "001": ("中国亚", "阿联酋亚"),
        "002": ("日本亚", "泰国亚"),
        "003": ("西雅图", "盐湖城"),
    }
    official: dict[str, dict[str, str]] = {}
    for row in results:
        number = row["match_number"][-3:]
        if number in wanted and row["home_team"] == wanted[number][0] and row["away_team"] == wanted[number][1]:
            official[number] = row
    assert set(official) == set(wanted)
    assert all(row["status"] == "已完成" for row in official.values())

    formal = [row for row in read_csv(ROOT / "data/manual/betting_plan_ledger.csv") if row.get("date") == DAY]
    fixed = [row for row in read_csv(ROOT / "data/manual/fixed_odds_shadow_ledger.csv") if row.get("date") == DAY]
    shadow_predictions = [row for row in read_csv(ROOT / "data/manual/shadow_prediction_ledger_v2.csv") if row.get("sales_day") == DAY]
    shadow_portfolios = [row for row in read_csv(ROOT / "data/manual/shadow_portfolio_ledger_v2.csv") if row.get("sales_day") == DAY]
    assert not formal and not fixed and not shadow_predictions and not shadow_portfolios

    match_reviews = [
        {
            "number": "001", "match": "中国亚 vs 阿联酋亚", "half": "0:0", "full": "0:0",
            "spf": "平", "rq": "让负", "spf_primary": False, "spf_cover": True,
            "rq_primary": True, "rq_cover": True, "goals_primary": False, "goals_cover": False,
            "score_primary": False, "score_cover": False, "hf_primary": False, "hf_cover": True,
            "diagnosis": "主胜未出；防平、让负和半全场次选平平命中，外盘浅于体彩-1的防不穿判断有效。",
        },
        {
            "number": "002", "match": "日本亚 vs 泰国亚", "half": "1:0", "full": "3:0",
            "spf": "胜（未开售）", "rq": "让胜", "spf_primary": True, "spf_cover": True,
            "rq_primary": True, "rq_cover": True, "goals_primary": True, "goals_cover": True,
            "score_primary": True, "score_cover": True, "hf_primary": None, "hf_cover": None,
            "diagnosis": "-2让胜、总进球3和比分3:0全部命中；捷报-3仅走盘，深盘风险提示仍成立。",
        },
        {
            "number": "003", "match": "西雅图 vs 盐湖城", "half": "0:0", "full": "2:0",
            "spf": "胜", "rq": "让胜", "spf_primary": True, "spf_cover": True,
            "rq_primary": False, "rq_cover": True, "goals_primary": False, "goals_cover": False,
            "score_primary": False, "score_cover": False, "hf_primary": False, "hf_cover": True,
            "diagnosis": "主胜命中且最终穿-1；让负主选失误，让胜防守命中；进球、比分均低于候选，平胜次选命中。",
        },
    ]

    contrarian = [
        {"name": "001邪修", "selection": "001(-1)让负@1.75", "stake": 2.0, "payout": 3.50, "hit": True},
        {"name": "002邪修", "selection": "002(-2)让胜@1.58", "stake": 2.0, "payout": 3.16, "hit": True},
        {"name": "003邪修", "selection": "003(-1)让负@1.93", "stake": 2.0, "payout": 0.00, "hit": False},
    ]
    additional = [
        {"name": "002让球双选", "selection": "让胜@1.58/让平@4.35，各2元", "stake": 4.0, "payout": 3.16, "hit": True},
        {"name": "002进球双选", "selection": "3@4.25/4@4.30，各2元", "stake": 4.0, "payout": 8.50, "hit": True},
        {"name": "002比分双选", "selection": "3:0@6.00/2:0@7.00，各2元", "stake": 4.0, "payout": 12.00, "hit": True},
        {"name": "003胜平双选", "selection": "主胜@1.65/平@3.70，各2元", "stake": 4.0, "payout": 3.30, "hit": True},
        {"name": "003让平", "selection": "(-1)让平@3.40", "stake": 2.0, "payout": 0.00, "hit": False},
        {"name": "003进球双选", "selection": "3@3.15/4@4.25，各2元", "stake": 4.0, "payout": 0.00, "hit": False},
        {"name": "003比分双选", "selection": "2:1@6.25/1:1@7.30，各2元", "stake": 4.0, "payout": 0.00, "hit": False},
    ]
    contrarian_summary = summarize(contrarian)
    additional_summary = summarize(additional)

    def metric(field: str) -> tuple[int, int]:
        eligible = [row[field] for row in match_reviews if row[field] is not None]
        return sum(bool(value) for value in eligible), len(eligible)

    metrics = {
        "spf_primary": metric("spf_primary"), "spf_covered": metric("spf_cover"),
        "rqspf_primary": metric("rq_primary"), "rqspf_covered": metric("rq_cover"),
        "total_goals_primary": metric("goals_primary"), "total_goals_covered": metric("goals_cover"),
        "correct_score_primary": metric("score_primary"), "correct_score_covered": metric("score_cover"),
        "half_full_primary": metric("hf_primary"), "half_full_covered": metric("hf_cover"),
    }

    audit = {
        "sales_day": DAY,
        "reviewed_at": COMPLETED_AT,
        "status": "completed_official_3_of_3",
        "official_match_count": 3,
        "prediction_coverage": "3/3",
        "match_reviews": match_reviews,
        "prediction_metrics": {key: f"{value[0]}/{value[1]}" for key, value in metrics.items()},
        "formal_summary": {"plans": 0, "stake": 0.0, "payout": 0.0, "net": 0.0, "roi": None,
                           "reason": "three one-match batches produced zero formal eligible rows; not authorization-blocked"},
        "fixed_odds_shadow_summary": {"plans": 0, "stake": 0.0, "payout": 0.0, "net": 0.0, "roi": None},
        "ledger_shadow_summary": {"predictions": 0, "portfolios": 0, "stake": 0.0, "payout": 0.0, "net": 0.0, "roi": None},
        "contrarian_display_summary": contrarian_summary,
        "additional_display_summary": additional_summary,
        "display_note": "displayed theoretical schemes were not written to shadow ledgers; settled separately and never counted as formal returns",
        "sources": [
            "artifacts/data/sporttery_results_2026-09-23.csv",
            "artifacts/data/sporttery_final_analysis_2026-09-23_1306_001.json",
            "artifacts/data/sporttery_final_analysis_2026-09-23_1705_002.json",
            "artifacts/data/sporttery_final_analysis_2026-09-23_2107_003.json",
            "data/manual/betting_plan_ledger.csv",
            "data/manual/fixed_odds_shadow_ledger.csv",
            "data/manual/shadow_prediction_ledger_v2.csv",
            "data/manual/shadow_portfolio_ledger_v2.csv",
        ],
        "supabase_sync": "not_authorized_for_2026-09-23",
    }
    audit_path = ROOT / "artifacts/data/sporttery_full_review_2026-09-23_1300_detailed.json"
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    match_lines = "\n".join(
        f"|{row['number']}|{row['match']}|{row['half']} / {row['full']}|{row['spf']}|{row['rq']}|"
        f"{'中' if row['spf_primary'] else '失'} / {'中' if row['spf_cover'] else '失'}|"
        f"{'中' if row['rq_primary'] else '失'} / {'中' if row['rq_cover'] else '失'}|"
        f"{'中' if row['goals_cover'] else '失'}|{'中' if row['score_cover'] else '失'}|"
        f"{'不适用' if row['hf_cover'] is None else ('中' if row['hf_cover'] else '失')}|"
        for row in match_reviews
    )
    diagnosis_lines = "\n".join(f"- {row['number']}：{row['diagnosis']}" for row in match_reviews)
    contra_lines = "\n".join(
        f"|{row['name']}|{row['selection']}|{row['stake']:.2f}|{row['payout']:.2f}|{row['payout']-row['stake']:+.2f}|{'中' if row['hit'] else '失'}|"
        for row in contrarian
    )
    additional_lines = "\n".join(
        f"|{row['name']}|{row['selection']}|{row['stake']:.2f}|{row['payout']:.2f}|{row['payout']-row['stake']:+.2f}|{'中' if row['hit'] else '失'}|"
        for row in additional
    )
    markdown = f"""# 2026-09-23销售日详细复盘

官方赛果3/3、终版预测3/3。正式策略三个单场批次均实际执行，但正式候选均为0行，因此正式投入、返奖和净收益均为0元，ROI不适用；不是授权闸门拦截。固定赔率影子和组合影子台账也均为0条。

## 逐场核验

|编号|比赛|半场/全场|SPF赛果|让球赛果|SPF主选/覆盖|让球主选/覆盖|进球覆盖|比分覆盖|半全场覆盖|
|---|---|---|---|---|---|---|---|---|---|
{match_lines}

{diagnosis_lines}

预测汇总：SPF主选2/3、覆盖3/3；让球主选2/3、覆盖3/3；总进球主选及覆盖1/3；比分主选及覆盖1/3；半全场主选0/2、覆盖2/2（002未提供半全场候选）。

## 正式及已冻结台账

|类别|方案|命中|投入|返奖|净收益|ROI|
|---|---:|---:|---:|---:|---:|---:|
|正式模拟|0|0|0.00|0.00|0.00|不适用|
|固定赔率影子|0|0|0.00|0.00|0.00|不适用|
|v2组合影子|0|0|0.00|0.00|0.00|不适用|

## 邪修展示方案（未入台账，独立理论结算）

|方案|选择|理论投入|理论返奖|理论净收益|结果|
|---|---|---:|---:|---:|---|
{contra_lines}

合计：3组，命中2组，理论投入{contrarian_summary['stake']:.2f}元、返奖{contrarian_summary['payout']:.2f}元、净收益{contrarian_summary['net']:+.2f}元、ROI {contrarian_summary['roi']:.2%}。

## 附加展示影子（未入台账，独立理论结算）

|方案|选择|理论投入|理论返奖|理论净收益|结果|
|---|---|---:|---:|---:|---|
{additional_lines}

合计：7组，命中4组，理论投入{additional_summary['stake']:.2f}元、返奖{additional_summary['payout']:.2f}元、净收益{additional_summary['net']:+.2f}元、ROI {additional_summary['roi']:.2%}。该组与邪修存在选项重叠，不合并成一个总收益口径。

## 结论

- 三场SPF方向通过防守选项实现3/3覆盖，但主选仅2/3；001主胜判断是主要错误。
- 让球主选2/3，003把浅外盘解释成不穿盘最终失效；盘口信号只能降级置信度，不能机械反买。
- 002的进球数3与比分3:0同时命中，但001和003均低于进球候选，比分玩法仍高方差。
- 正式方案为0的原因是三个批次均为单场且分别存在概率、玩法覆盖或单关资格门禁，不是写入授权失败。
- 所有展示影子仅作赛前研究回测，不补写任何台账；本销售日未授权Supabase同步。

结构化审计：`artifacts/data/sporttery_full_review_2026-09-23_1300_detailed.json`
"""
    report_path = ROOT / "artifacts/reviews/sporttery_full_review_2026-09-23_1300_detailed.md"
    report_path.write_text(markdown, encoding="utf-8")

    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update({
        "last_heartbeat_at": COMPLETED_AT,
        "last_completed_stage": "2026-09-24 13:00前一销售日复盘",
        "last_completed_at": COMPLETED_AT,
        "last_stage_status": "completed_review_20260923_official_3_of_3_formal0_fixed0_displayed_shadow_separate",
        "last_stage_artifact": "artifacts/reviews/sporttery_full_review_2026-09-23_1300_detailed.md",
        "last_reviewed_sales_day": DAY,
        "last_review_artifact": "artifacts/reviews/sporttery_full_review_2026-09-23_1300_detailed.md",
        "next_dynamic_task_key": "2026-09-24|18:05-19:35|终版分析",
        "next_dynamic_task_at": "2026-09-24T16:35:00+08:00",
        "next_required_stage": "2026-09-24 16:35终版分析001-003",
        "next_required_at": "2026-09-24T16:35:00+08:00",
    })
    state["review_20260923"] = {
        "status": "completed", "completed_at": COMPLETED_AT,
        "official_matches": 3, "official_result_coverage": "3/3", "prediction_coverage": "3/3",
        "formal": "0_plans_stake0_payout0_net0_roi_not_applicable",
        "fixed_shadow": "0_plans_stake0_payout0_net0_roi_not_applicable",
        "ledger_shadow": "0_predictions_0_portfolios",
        "contrarian_display": f"2_of_3_stake{contrarian_summary['stake']:.2f}_payout{contrarian_summary['payout']:.2f}_net{contrarian_summary['net']:.2f}",
        "additional_display": f"4_of_7_stake{additional_summary['stake']:.2f}_payout{additional_summary['payout']:.2f}_net{additional_summary['net']:.2f}",
        "report": "artifacts/reviews/sporttery_full_review_2026-09-23_1300_detailed.md",
        "audit": "artifacts/data/sporttery_full_review_2026-09-23_1300_detailed.json",
        "supabase_sync": "not_authorized_for_2026-09-23",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "official": "3/3", "formal": 0,
                      "contrarian_net": contrarian_summary["net"], "additional_net": additional_summary["net"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
