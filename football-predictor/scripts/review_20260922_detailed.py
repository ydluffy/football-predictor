from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-09-22"
COMPLETED_AT = "2026-09-23T15:07:05+08:00"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    results = read_csv(ROOT / "artifacts/data/sporttery_results_2026-09-22.csv")
    by_number = {row["match_number"][-3:]: row for row in results}
    assert set(by_number) == {"001", "002", "003", "004"}
    assert all(row["status"] == "已完成" for row in results)

    formal = [row for row in read_csv(ROOT / "data/manual/betting_plan_ledger.csv") if row.get("date") == DAY]
    fixed = [row for row in read_csv(ROOT / "data/manual/fixed_odds_shadow_ledger.csv") if row.get("date") == DAY]
    assert not formal
    assert len(fixed) == 1 and fixed[0]["result"] == "未中"

    match_reviews = [
        {"number": "001", "result": "韩国亚2:0沙特亚", "spf": "胜", "rq": "让胜", "spf_primary": True, "spf_cover": True, "rq_primary": True, "rq_cover": True, "goals_primary": False, "goals_cover": True, "score_primary": True, "score_cover": True, "hf_primary": False, "hf_cover": True},
        {"number": "002", "result": "米尔顿4:1克劳利", "spf": "胜", "rq": "让胜", "spf_primary": True, "spf_cover": True, "rq_primary": True, "rq_cover": True, "goals_primary": False, "goals_cover": False, "score_primary": False, "score_cover": False, "hf_primary": True, "hf_cover": True},
        {"number": "003", "result": "诺茨郡2:1格里姆", "spf": "胜", "rq": "让平", "spf_primary": True, "spf_cover": True, "rq_primary": False, "rq_cover": True, "goals_primary": True, "goals_cover": True, "score_primary": False, "score_cover": True, "hf_primary": True, "hf_cover": True},
        {"number": "004", "result": "维冈3:2布莱克浦", "spf": "胜", "rq": "让平", "spf_primary": False, "spf_cover": True, "rq_primary": False, "rq_cover": True, "goals_primary": False, "goals_cover": False, "score_primary": False, "score_cover": False, "hf_primary": False, "hf_cover": True},
    ]

    strategy_shadow = [
        {"name": "001防冷", "selection": "001主胜/平", "stake": 4.0, "payout": 2.58, "net": -1.42, "hit": True},
        {"name": "001博高", "selection": "001(-1)让平", "stake": 2.0, "payout": 0.0, "net": -2.0, "hit": False},
        {"name": "002-003防冷", "selection": "002主胜/平×003主胜/客胜", "stake": 8.0, "payout": 5.734, "net": -2.266, "hit": True},
        {"name": "002-004博高", "selection": "002/003/004均让平", "stake": 2.0, "payout": 0.0, "net": -2.0, "hit": False},
    ]
    strategy_stake = sum(x["stake"] for x in strategy_shadow)
    strategy_payout = sum(x["payout"] for x in strategy_shadow)
    strategy_net = sum(x["net"] for x in strategy_shadow)

    displayed = [
        {"name": "顺势观察", "selection": "002主胜×003主胜", "stake": 50.0, "payout": 143.35, "net": 93.35, "hit": True},
        {"name": "价值观察", "selection": "003主胜×004客胜", "stake": 20.0, "payout": 0.0, "net": -20.0, "hit": False},
        {"name": "让球结构", "selection": "004让负×003让负", "stake": 20.0, "payout": 0.0, "net": -20.0, "hit": False},
        {"name": "防冷复式", "selection": "003主/客×004客/主", "stake": 8.0, "payout": 12.032, "net": 4.032, "hit": True},
        {"name": "总进球复式", "selection": "002(3/4)×003(3/2)", "stake": 8.0, "payout": 0.0, "net": -8.0, "hit": False},
        {"name": "比分观察", "selection": "002(2:1/2:0)×003(1:1/2:1)", "stake": 8.0, "payout": 0.0, "net": -8.0, "hit": False},
        {"name": "半全场观察", "selection": "002胜胜×003胜胜", "stake": 2.0, "payout": 14.104, "net": 12.104, "hit": True},
    ]
    displayed_stake = sum(x["stake"] for x in displayed)
    displayed_payout = sum(x["payout"] for x in displayed)
    displayed_net = sum(x["net"] for x in displayed)

    contrarian = [
        {"name": "001邪修", "selection": "001(-1)让胜@1.95", "stake": 2.0, "payout": 3.90, "net": 1.90, "hit": True},
        {"name": "003邪修", "selection": "003(-1)让负@1.43", "stake": 2.0, "payout": 0.0, "net": -2.0, "hit": False},
    ]
    contra_stake = sum(x["stake"] for x in contrarian)
    contra_payout = sum(x["payout"] for x in contrarian)
    contra_net = sum(x["net"] for x in contrarian)

    audit = {
        "sales_day": DAY,
        "reviewed_at": COMPLETED_AT,
        "status": "completed_official_4_of_4",
        "official_match_count": 4,
        "prediction_coverage": "4/4",
        "match_reviews": match_reviews,
        "prediction_metrics": {
            "spf_primary": "3/4", "spf_covered": "4/4",
            "rqspf_primary": "2/4", "rqspf_covered": "4/4",
            "total_goals_primary": "1/4", "total_goals_covered": "2/4",
            "correct_score_primary": "1/4", "correct_score_covered": "2/4",
            "half_full_primary": "2/4", "half_full_covered": "4/4",
        },
        "formal_summary": {"plans": 0, "stake": 0.0, "payout": 0.0, "net": 0.0, "roi": None, "reason": "both final batches executed formal strategy with zero eligible rows"},
        "fixed_odds_shadow_summary": {"plans": 1, "hits": 0, "stake": 2.0, "payout": 0.0, "net": -2.0, "roi": -1.0},
        "strategy_shadow_summary": {"schemes": 4, "hits": 2, "stake": strategy_stake, "payout": strategy_payout, "net": strategy_net, "roi": strategy_net / strategy_stake},
        "displayed_shadow_summary": {"schemes": 7, "hits": 3, "stake": displayed_stake, "payout": displayed_payout, "net": displayed_net, "roi": displayed_net / displayed_stake},
        "contrarian_shadow_summary": {"schemes": 2, "hits": 1, "stake": contra_stake, "payout": contra_payout, "net": contra_net, "roi": contra_net / contra_stake},
        "duplication_note": "fixed-odds shadow is excluded from strategy/displayed aggregates to prevent double counting; all shadow categories remain separate from formal ledger",
        "sources": [
            "artifacts/data/sporttery_results_2026-09-22.csv",
            "artifacts/data/sporttery_final_analysis_2026-09-22_1613_001.json",
            "artifacts/data/sporttery_final_analysis_2026-09-22_2112_002-004.json",
            "data/manual/betting_plan_ledger.csv",
            "data/manual/fixed_odds_shadow_ledger.csv",
        ],
        "supabase_sync": "not_authorized_for_2026-09-22",
    }
    audit_path = ROOT / "artifacts/data/sporttery_full_review_2026-09-22_1300_detailed.json"
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    match_lines = []
    for m in match_reviews:
        match_lines.append(
            f"|{m['number']}|{m['result']}|{m['spf']}|{m['rq']}|"
            f"{'中' if m['spf_primary'] else '失'} / {'中' if m['spf_cover'] else '失'}|"
            f"{'中' if m['rq_primary'] else '失'} / {'中' if m['rq_cover'] else '失'}|"
            f"{'中' if m['goals_cover'] else '失'}|{'中' if m['score_cover'] else '失'}|{'中' if m['hf_cover'] else '失'}|"
        )
    strategy_lines = "\n".join(f"|{x['name']}|{x['selection']}|{x['stake']:.2f}|{x['payout']:.2f}|{x['net']:.2f}|{'中' if x['hit'] else '失'}|" for x in strategy_shadow)
    displayed_lines = "\n".join(f"|{x['name']}|{x['selection']}|{x['stake']:.2f}|{x['payout']:.2f}|{x['net']:.2f}|{'中' if x['hit'] else '失'}|" for x in displayed)
    contra_lines = "\n".join(f"|{x['name']}|{x['selection']}|{x['stake']:.2f}|{x['payout']:.2f}|{x['net']:.2f}|{'中' if x['hit'] else '失'}|" for x in contrarian)

    markdown = f"""# 2026-09-22销售日详细复盘

官方赛果4/4、终版预测4/4。正式策略两个批次均实际执行，但生产候选均为0行，所以正式投入0元、返奖0元、净收益0元，ROI不适用；不是授权拦截。

## 逐场核验

|编号|赛果|SPF|让球赛果|SPF主选/覆盖|让球主选/覆盖|进球覆盖|比分覆盖|半全场覆盖|
|---|---|---|---|---|---|---|---|---|
{chr(10).join(match_lines)}

综合：SPF主选3/4、覆盖4/4；让球主选2/4、覆盖4/4；总进球主选1/4、覆盖2/4；比分主选1/4、覆盖2/4；半全场主选2/4、覆盖4/4。

## 正式与固定赔率台账

|类别|方案|命中|投入|返奖|净收益|ROI|
|---|---:|---:|---:|---:|---:|---:|
|正式模拟|0|0|0.00|0.00|0.00|不适用|
|固定赔率影子|1|0|2.00|0.00|-2.00|-100.00%|

固定赔率票为002主胜×003主胜×004客胜，前两腿命中，004实际主胜导致整票未中。

## 正式策略附带影子（独立统计）

|方案|选择|投入|返奖|净收益|结果|
|---|---|---:|---:|---:|---|
{strategy_lines}

合计投入{strategy_stake:.2f}元、返奖{strategy_payout:.2f}元、净收益{strategy_net:.2f}元、ROI {strategy_net / strategy_stake:.2%}。

## 报告展示的其他影子方案（独立统计）

|方案|选择|投入|返奖|净收益|结果|
|---|---|---:|---:|---:|---|
{displayed_lines}

合计投入{displayed_stake:.2f}元、返奖{displayed_payout:.2f}元、净收益{displayed_net:.2f}元、ROI {displayed_net / displayed_stake:.2%}。固定赔率票未重复计入。

## 邪修影子（独立统计）

|方案|选择|投入|返奖|净收益|结果|
|---|---|---:|---:|---:|---|
{contra_lines}

合计投入{contra_stake:.2f}元、返奖{contra_payout:.2f}元、净收益{contra_net:.2f}元、ROI {contra_net / contra_stake:.2%}。001的“强队赢且穿盘”打出，003的一球小胜对应让平，反大众让负未中，说明邪修信号不能机械反买。

## 结论

- 主胜方向整体较好，但004客胜主选错误；将主客双向列入覆盖后SPF达到4/4，代价是组合成本上升。
- 让球主选只有2/4；003和004均恰好一球胜，说明让平在均势盘中比机械让负更值得进入防守层。
- 比分与总进球仍是高方差玩法，不应因偶发命中扩大本金。
- 所有影子仅为研究记账，与正式台账隔离；未获本销售日Supabase同步授权。

结构化审计：`artifacts/data/sporttery_full_review_2026-09-22_1300_detailed.json`
"""
    report_path = ROOT / "artifacts/reviews/sporttery_full_review_2026-09-22_1300_detailed.md"
    report_path.write_text(markdown, encoding="utf-8")

    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update(
        {
            "last_heartbeat_at": COMPLETED_AT,
            "last_completed_stage": "2026-09-23 13:00前一销售日复盘",
            "last_completed_at": COMPLETED_AT,
            "last_stage_status": "completed_review_20260922_official_4_of_4_formal_zero_fixed_shadow_loss",
            "last_stage_artifact": "artifacts/reviews/sporttery_full_review_2026-09-22_1300_detailed.md",
            "last_reviewed_sales_day": DAY,
            "last_review_artifact": "artifacts/reviews/sporttery_full_review_2026-09-22_1300_detailed.md",
            "next_dynamic_task_key": "2026-09-23|18:30|终版分析",
            "next_dynamic_task_at": "2026-09-23T17:00:00+08:00",
            "next_required_stage": "2026-09-23 17:00终版分析002 日本亚 vs 泰国亚",
            "next_required_at": "2026-09-23T17:00:00+08:00",
        }
    )
    state["review_20260922"] = {
        "status": "completed",
        "completed_at": COMPLETED_AT,
        "official_matches": 4,
        "official_result_coverage": "4/4",
        "prediction_coverage": "4/4",
        "formal": "0_plans_stake0_payout0_net0_roi_not_applicable",
        "fixed_shadow": "0_of_1_stake2_payout0_net_minus2_roi_minus100pct",
        "strategy_shadow": f"2_of_4_stake{strategy_stake:.2f}_payout{strategy_payout:.2f}_net{strategy_net:.2f}",
        "displayed_shadow": f"3_of_7_stake{displayed_stake:.2f}_payout{displayed_payout:.2f}_net{displayed_net:.2f}",
        "contrarian_shadow": f"1_of_2_stake{contra_stake:.2f}_payout{contra_payout:.2f}_net{contra_net:.2f}",
        "report": "artifacts/reviews/sporttery_full_review_2026-09-22_1300_detailed.md",
        "audit": "artifacts/data/sporttery_full_review_2026-09-22_1300_detailed.json",
        "supabase_sync": "not_authorized_for_2026-09-22",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "official": "4/4", "formal": 0, "fixed_shadow_net": -2.0}, ensure_ascii=True))


if __name__ == "__main__":
    main()
