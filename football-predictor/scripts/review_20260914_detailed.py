"""Build the detailed 2026-09-14 review from frozen official data and results."""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-09-14"
SCAN = ROOT / "artifacts/data/sporttery_sales_window_scan_2026-09-14_1834_confirm.json"
RESULTS = ROOT / "data/manual/sporttery_results_2026-09-14_sales_window.csv"
REGISTRY = ROOT / "artifacts/data/sporttery_task_registry_2026-09-14.json"
REPORT = ROOT / "artifacts/reviews/sporttery_full_review_2026-09-14_1300_detailed.md"
AUDIT = ROOT / "artifacts/data/sporttery_full_review_2026-09-14_1300_detailed.json"


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def spf(score: str) -> str:
    home, away = (int(value) for value in score.split(":"))
    return "主胜" if home > away else "客胜" if home < away else "平"


def main() -> None:
    scan = json.loads(SCAN.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    fixtures = {item["match_number"]: item for item in scan["fixtures"]}
    official = {
        row["match_number"][-3:]: row
        for row in csv_rows(RESULTS)
        if row["match_number"].startswith("周一")
        and row["match_number"][-3:] in fixtures
    }
    expected = set(fixtures)
    if set(official) != expected:
        raise ValueError(f"official result coverage mismatch: missing={sorted(expected-set(official))}")
    if any(row["status"] != "已完成" or ":" not in row["full_time_score"] for row in official.values()):
        raise ValueError("not all in-scope matches have completed 90-minute scores")

    formal = [row for row in csv_rows(ROOT / "data/manual/betting_plan_ledger.csv") if row.get("date") == DAY]
    fixed = [row for row in csv_rows(ROOT / "data/manual/fixed_odds_shadow_ledger.csv") if row.get("date") == DAY]
    shadow = [row for row in csv_rows(ROOT / "data/manual/shadow_portfolio_ledger_v2.csv") if row.get("sales_day") == DAY or row.get("date") == DAY]
    final_task = next(item for item in registry["tasks"] if item["purpose"] == "终版分析")

    per_match = []
    for number in sorted(expected):
        row = official[number]
        result = {
            "number": number,
            "competition": row["competition"],
            "home": row["home_team"],
            "away": row["away_team"],
            "kickoff": fixtures[number]["kickoff"],
            "half_time": row["half_time_score"],
            "full_time": row["full_time_score"],
            "spf": spf(row["full_time_score"]),
            "handicap": int(row["handicap"]),
            "rqspf": row["rqspf_result"],
            "prediction_status": "无冻结终版预测，不计命中率",
        }
        per_match.append(result)

    reviewed_at = datetime.now().astimezone().replace(microsecond=0).isoformat()
    audit = {
        "schema_version": 1,
        "sales_day": DAY,
        "status": "completed_with_missing_final_prediction",
        "reviewed_at": reviewed_at,
        "official_result_count": len(per_match),
        "official_result_coverage": "11/11",
        "prediction_count": 0,
        "prediction_metrics": None,
        "formal_plan_count": len(formal),
        "fixed_odds_shadow_plan_count": len(fixed),
        "contrarian_or_other_shadow_plan_count": len(shadow),
        "formal_financials": {"stake": 0.0, "payout": 0.0, "net": 0.0, "roi": None},
        "shadow_financials": {"stake": 0.0, "payout": 0.0, "net": 0.0, "roi": None},
        "per_match": per_match,
        "missing_stage": {
            "task_key": final_task["key"],
            "scheduled_for": final_task["run_at"],
            "hard_lock": final_task["hard_lock"],
            "status_before_review": final_task["status"],
            "cause": "desktop heartbeat did not wake for the registered final task; no legal post-lock backfill",
        },
        "source_scan": str(SCAN.relative_to(ROOT)),
        "source_results": str(RESULTS.relative_to(ROOT)),
        "production_ledger_write_performed": False,
        "supabase_sync": "not_authorized_for_2026-09-14",
    }
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# 2026-09-14 销售日详细复盘",
        "",
        f"- 复盘时间：{reviewed_at}。",
        "- 体彩官方赛果覆盖：11/11，全部取得半场与90分钟比分。",
        "- 昨日21:30终版任务未被桌面心跳唤醒，且已过21:45硬锁，因此没有合法冻结预测、正式模拟方案或影子方案；本次严禁事后补写。",
        "- 本复盘完成的是赛果核实、台账核对及调度故障归因；预测命中率与方案ROI记为不适用，而不是0%。",
        "",
        "## 官方赛果逐场核实",
        "",
        "|编号|赛事|比赛|开赛时间（北京）|半场/全场|SPF|让球结果|预测核验|",
        "|---|---|---|---|---|---|---|---|",
    ]
    for item in per_match:
        kickoff = item["kickoff"][11:16]
        lines.append(
            f"|{item['number']}|{item['competition']}|{item['home']} vs {item['away']}|{kickoff}|"
            f"{item['half_time']} / {item['full_time']}|{item['spf']}|{item['handicap']:+d} {item['rqspf']}|"
            f"{item['prediction_status']}|"
        )
    lines += [
        "",
        "## 方案与资金复盘",
        "",
        "- 正式模拟方案：0组；投入0元、返奖0元、净收益0元；因无方案，ROI不适用。",
        "- 固定赔率影子：0组；投入0元、返奖0元、净收益0元；ROI不适用。",
        "- 邪修及其他组合影子：0组；投入0元、返奖0元、净收益0元；ROI不适用。",
        "- 以上均以销售日字段严格过滤；不得把其他日期的累计台账数字算入9月14日。",
        "",
        "## 故障归因与改进",
        "",
        "- 数据采集并非完全缺失：18:34已补采11场体彩四玩法并形成冻结赔率扫描。",
        "- 生产断点发生在21:30终版：注册表仍为 pending_schedule，桌面任务没有在硬锁前唤醒，因而没有赛前预测和方案可复盘。",
        "- 当前30分钟固定心跳已上线，可覆盖后续到期任务；到期前35分钟且数据齐备时允许提前执行，避免再次错过硬锁。",
        "- 外盘在昨日扫描时因额度仅余1 credit而未付费批量调用，不能用旧外盘快照补造昨日终版依据。",
        "- 未取得2026-09-14销售日Supabase同步授权，本次只保存本地产物。",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": audit["status"], "matches": len(per_match), "formal": len(formal), "fixed": len(fixed), "shadow": len(shadow), "report": str(REPORT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
