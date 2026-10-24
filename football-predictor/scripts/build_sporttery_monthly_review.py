from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SETTLED_RESULTS = {"命中", "未中"}


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig", keep_default_na=False) if path.exists() else pd.DataFrame()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _number(value: object) -> float:
    return float(pd.to_numeric(pd.Series([value]), errors="coerce").fillna(0.0).iloc[0])


def parse_plan_odds(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = float(text)
        return parsed if parsed > 1 else None
    except ValueError:
        pass
    if "=" in text:
        try:
            parsed = float(text.rsplit("=", 1)[1].strip())
            return parsed if parsed > 1 else None
        except ValueError:
            pass
    factors = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", text)]
    if "*" in text and factors:
        parsed = math.prod(factors)
        return parsed if parsed > 1 else None
    return factors[-1] if factors and factors[-1] > 1 else None


def maximum_drawdown(frame: pd.DataFrame) -> tuple[float, float]:
    if frame.empty:
        return 0.0, 0.0
    ordered = frame.copy()
    raw_time = ordered.get("time_window", pd.Series("", index=ordered.index)).astype(str)
    first_clock = raw_time.str.extract(r"(\d{1,2}:\d{2})", expand=False).fillna("00:00")
    ordered["_order"] = pd.to_datetime(
        ordered["date"].astype(str) + " " + first_clock,
        errors="coerce",
    )
    ordered = ordered.sort_values(["_order", "plan_id"], kind="mergesort")
    stake = pd.to_numeric(ordered["stake"], errors="coerce").fillna(0.0)
    payout = pd.to_numeric(ordered["payout"], errors="coerce").fillna(0.0)
    equity = (payout - stake).cumsum()
    peaks = pd.concat([pd.Series([0.0]), equity], ignore_index=True).cummax().iloc[1:].reset_index(drop=True)
    drawdowns = equity.reset_index(drop=True) - peaks
    amount = abs(float(drawdowns.min())) if not drawdowns.empty else 0.0
    total_stake = float(stake.sum())
    return round(amount, 2), round(amount / total_stake, 4) if total_stake else 0.0


def summarize(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {"plans": 0, "hits": 0, "stake": 0.0, "payout": 0.0, "net_profit": 0.0, "roi": 0.0, "hit_rate": 0.0, "max_drawdown": 0.0, "max_drawdown_stake_ratio": 0.0}
    stake = float(pd.to_numeric(frame["stake"], errors="coerce").fillna(0.0).sum())
    payout = float(pd.to_numeric(frame["payout"], errors="coerce").fillna(0.0).sum())
    hits = int(frame["result"].astype(str).eq("命中").sum())
    drawdown, drawdown_ratio = maximum_drawdown(frame)
    return {
        "plans": int(len(frame)), "hits": hits, "stake": round(stake, 2),
        "payout": round(payout, 2), "net_profit": round(payout - stake, 2),
        "roi": round((payout - stake) / stake, 4) if stake else 0.0,
        "hit_rate": round(hits / len(frame), 4), "max_drawdown": drawdown,
        "max_drawdown_stake_ratio": drawdown_ratio,
    }


def grouped(frame: pd.DataFrame, column: str) -> dict[str, dict[str, Any]]:
    if frame.empty or column not in frame.columns:
        return {}
    return {str(key): summarize(group) for key, group in frame.groupby(column, dropna=False)}


def _odds_band(value: object) -> str:
    odds = parse_plan_odds(value)
    if odds is None:
        return "missing"
    if odds < 1.50:
        return "1.01-1.49"
    if odds < 2.00:
        return "1.50-1.99"
    if odds < 3.00:
        return "2.00-2.99"
    if odds < 6.00:
        return "3.00-5.99"
    if odds <= 10.00:
        return "6.00-10.00"
    return "10.01+"


def _play_group(value: object) -> str:
    text = str(value)
    has_handicap = "让球胜平负" in text or re.search(r"[+-]\d+", text) is not None
    has_spf = "胜平负" in text or any(token in text for token in ("主胜", "客胜"))
    if has_handicap and has_spf and "让球胜平负" not in text:
        return "mixed_or_legacy"
    if has_handicap:
        return "rqspf"
    if has_spf:
        return "spf"
    return "unclassified"


def ledger_metrics(path: Path, month: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    ledger = _read_csv(path)
    if ledger.empty:
        return ledger, summarize(ledger)
    frame = ledger[ledger["date"].astype(str).str.startswith(month + "-")].copy()
    frame = frame[frame["result"].astype(str).isin(SETTLED_RESULTS)].copy()
    odds_source = frame.get("actual_odds", pd.Series("", index=frame.index)).astype(str)
    odds_source = odds_source.where(odds_source.str.strip().ne(""), frame.get("estimated_odds", pd.Series("", index=frame.index)).astype(str))
    frame["odds_band"] = odds_source.map(_odds_band)
    frame["play_group"] = frame["selections"].map(_play_group)
    result = summarize(frame)
    result["by_type"] = grouped(frame, "plan_type")
    result["by_odds_band"] = grouped(frame, "odds_band")
    result["by_play_group"] = grouped(frame, "play_group")
    result["by_time_window"] = grouped(frame, "time_window")
    result["league_breakdown"] = {"status": "unavailable", "reason": "production ledger does not persist a normalized competition field"}
    return frame, result


def registry_metrics(month: str) -> dict[str, Any]:
    paths = sorted((ROOT / "artifacts/data").glob(f"sporttery_task_registry_{month}-*.json"))
    tasks: list[dict[str, Any]] = []
    for path in paths:
        tasks.extend(_read_json(path).get("tasks", []))
    counts: dict[str, int] = {}
    for task in tasks:
        status = str(task.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    measurable = 0
    before_lock = 0
    production_measurable = 0
    abstained = 0
    for task in tasks:
        completed_at = pd.to_datetime(task.get("completed_at"), errors="coerce", utc=True)
        hard_lock = pd.to_datetime(task.get("hard_lock"), errors="coerce", utc=True)
        if pd.notna(completed_at) and pd.notna(hard_lock):
            measurable += 1
            before_lock += int(completed_at <= hard_lock)
        if task.get("production_plan_rows") is not None:
            production_measurable += 1
            abstained += int(_number(task.get("production_plan_rows")) == 0)
    return {
        "registries": len(paths), "tasks": len(tasks), "status_counts": counts,
        "hard_lock_measurable_tasks": measurable,
        "completed_before_hard_lock": before_lock,
        "hard_lock_punctuality": round(before_lock / measurable, 4) if measurable else None,
        "abstention_measurable_tasks": production_measurable,
        "abstained_tasks": abstained,
        "abstention_rate": round(abstained / production_measurable, 4) if production_measurable else None,
    }


def source_metrics(month: str) -> dict[str, Any]:
    paths = sorted((ROOT / "artifacts/data").glob(f"sporttery_official_fetch_audit_{month}-*.json"))
    play_counts: dict[str, dict[str, int]] = {}
    complete = 0
    for path in paths:
        fetches = _read_json(path).get("fetches", {})
        ok_all = bool(fetches)
        for play, payload in fetches.items():
            bucket = play_counts.setdefault(play, {"attempts": 0, "successes": 0})
            bucket["attempts"] += 1
            success = bool(payload.get("ok"))
            bucket["successes"] += int(success)
            ok_all = ok_all and success
        complete += int(ok_all)
    for bucket in play_counts.values():
        bucket["success_rate"] = round(bucket["successes"] / bucket["attempts"], 4) if bucket["attempts"] else 0.0
    return {
        "snapshots": len(paths), "four_play_complete_snapshots": complete,
        "four_play_complete_rate": round(complete / len(paths), 4) if paths else None,
        "by_play": play_counts,
    }


def calibration_metrics(path: Path, month: str) -> dict[str, Any]:
    frame = _read_csv(path)
    if frame.empty or "sales_day" not in frame.columns:
        return {"samples": 0, "status": "unavailable"}
    frame = frame[frame["sales_day"].astype(str).str.startswith(month + "-") & frame["result_status"].astype(str).eq("settled")].copy()
    rows: list[tuple[list[float], int]] = []
    outcomes = {"home": 0, "draw": 1, "away": 2, "让胜": 0, "让平": 1, "让负": 2}
    for _, row in frame.iterrows():
        probs = [_number(row.get("prob_home")), _number(row.get("prob_draw")), _number(row.get("prob_away"))]
        total = sum(probs)
        actual = outcomes.get(str(row.get("actual_rqspf", "")).strip())
        if actual is None or total <= 0:
            continue
        rows.append(([p / total for p in probs], actual))
    if not rows:
        return {"samples": 0, "status": "unavailable_no_settled_probability_rows"}
    briers, losses, correct = [], [], 0
    for probs, actual in rows:
        target = [1.0 if index == actual else 0.0 for index in range(3)]
        briers.append(sum((prob - truth) ** 2 for prob, truth in zip(probs, target)))
        losses.append(-math.log(max(probs[actual], 1e-15)))
        correct += int(max(range(3), key=probs.__getitem__) == actual)
    return {"samples": len(rows), "accuracy": round(correct / len(rows), 4), "brier_score": round(sum(briers) / len(rows), 6), "log_loss": round(sum(losses) / len(rows), 6), "status": "sample_too_small" if len(rows) < 50 else "measured"}


def _fmt_rate(value: object) -> str:
    return "不可用" if value is None else f"{float(value):.2%}"


def _summary_line(label: str, item: dict[str, Any]) -> str:
    return f"- {label}：{item['plans']}张，命中{item['hits']}张，投入{item['stake']:.2f}元，返奖{item['payout']:.2f}元，净收益{item['net_profit']:+.2f}元，ROI {_fmt_rate(item['roi'])}，最大回撤{item['max_drawdown']:.2f}元。"


def render_markdown(report: dict[str, Any]) -> str:
    ledger = report["production_ledger"]
    candidate = report["candidate_decision"]
    lines = [
        f"# 体彩月度预测与投注复盘（{report['month']}）", "",
        f"生成时间：{report['generated_at']}。仅使用赛前已冻结记录和已结算台账；未事后补造方案。", "",
        "## 核心结论", "", _summary_line("正式方案", ledger),
    ]
    for name, item in ledger.get("by_type", {}).items():
        lines.append(_summary_line(name, item))
    lines += [
        "", "- 本月主要亏损来自‘稳健’低赔串关；低赔率没有抵消任一腿失误导致整票归零的结构风险。",
        "- 稳健与价值票共享核心场次会放大同一判断错误，下一月新增零共享研究开关，但保持生产默认不变。",
        "- 联赛分组无法可靠统计，因为正式台账没有保存规范化赛事字段；这是10月必须补齐的数据契约。",
        "", "## 执行与数据质量", "",
        f"- 体彩四玩法完整抓取率：{_fmt_rate(report['data_sources']['four_play_complete_rate'])}（{report['data_sources']['four_play_complete_snapshots']}/{report['data_sources']['snapshots']}个快照）。",
        f"- 可测任务硬锁前完成率：{_fmt_rate(report['task_registry']['hard_lock_punctuality'])}（{report['task_registry']['completed_before_hard_lock']}/{report['task_registry']['hard_lock_measurable_tasks']}）。",
        f"- 可测批次弃投率：{_fmt_rate(report['task_registry']['abstention_rate'])}；弃投保留为风控结果，不按0收益伪装。",
        f"- 概率校准：{report['calibration']['samples']}个可结算概率样本，状态 `{report['calibration']['status']}`；样本不足时不据此晋级。",
        "- CLV：缺少逐方案早盘—终盘唯一关联，暂不输出伪精确数值。",
        "", "## 模型与组合改进决定", "",
        f"- 候选：`max_shared_production_matches=0`（稳健/价值两票不共享比赛），决定：`{candidate['decision']}`。",
        f"- 自动晋级闸门：正式已结算{candidate['settled_plans']}/50；最小受影响分组{candidate['minimum_affected_group']}/20。",
        "- v3净胜球/盘口移动模型继续保持影子；赛前阵容、伤停、xG、旅行和时区覆盖不足，不能启用新增信息模型。",
        "- 不提高预算、不改历史预测、不把ROI单项改善当作晋级依据。",
        "", "## 10月行动项", "",
        "1. 所有正式台账新增规范化赛事、开赛时间、每腿模型概率、早盘与终盘快照ID。",
        "2. 影子对照生产默认（最多共享1场）与零共享候选，至少累计50张且受影响组不少于20张后再评估。",
        "3. 对稳健票单独监控最大回撤和低于2.00总赔率区间；禁止把‘低赔’直接命名为低风险证据。",
        "4. 外盘缺失时继续降级体彩基线；数据失败和模型失败分开归因。",
        "", f"结构化审计：`{report['artifacts']['monthly_json']}`。", "",
    ]
    return "\n".join(lines)


def build(month: str, generated_at: str, source_thread_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    ledger_path = ROOT / "data/manual/betting_plan_ledger.csv"
    fixed_path = ROOT / "data/manual/fixed_odds_shadow_ledger.csv"
    shadow_path = ROOT / "data/manual/shadow_prediction_ledger_v2.csv"
    frame, production = ledger_metrics(ledger_path, month)
    _, fixed = ledger_metrics(fixed_path, month)
    registry = registry_metrics(month)
    sources = source_metrics(month)
    calibration = calibration_metrics(shadow_path, month)
    controller_state = _read_json(ROOT / "artifacts/data/football_automation_controller_state.json")
    month_end = str(pd.Period(month, freq="M").end_time.date())
    last_reviewed_sales_day = str(controller_state.get("last_reviewed_sales_day", ""))
    migration_ready = last_reviewed_sales_day >= month_end
    group_sizes = [item["plans"] for item in production.get("by_type", {}).values()]
    minimum_group = min(group_sizes) if group_sizes else 0
    gate_passed = production["plans"] >= 50 and minimum_group >= 20
    target_month = str((pd.Period(month, freq="M") + 1))
    report = {
        "schema_version": 2, "month": month, "generated_at": generated_at,
        "production_ledger": production, "fixed_odds_forward_shadow": fixed,
        "task_registry": registry, "data_sources": sources, "calibration": calibration,
        "clv": {"status": "unavailable", "reason": "no unique plan-to-early-and-closing-snapshot linkage"},
        "failure_separation": {
            "model_or_expression": "negative settled-plan ROI and correlated ticket exposure",
            "data_or_execution": "registry failures/pending tasks and missing normalized competition/probability/CLV fields are reported separately",
        },
        "candidate_decision": {
            "candidate": {"max_shared_production_matches": 0},
            "settled_plans": production["plans"], "required_settled_plans": 50,
            "minimum_affected_group": minimum_group, "required_affected_group": 20,
            "decision": "eligible_for_further_risk_checks" if gate_passed else "research_only_sample_gate_failed",
            "production_promotion_allowed": False,
            "production_change_performed": False,
        },
        "artifacts": {
            "monthly_json": f"artifacts/data/sporttery_monthly_review_{month}.json",
            "monthly_markdown": f"artifacts/reviews/sporttery_monthly_review_{month}.md",
            "asian_handicap": "artifacts/data/asian_handicap_research_2026-10-01.json",
            "v3": "artifacts/data/handicap_margin_movement_v3_2026-10-01.json",
            "prematch_coverage": "artifacts/data/prematch_intelligence_coverage_2026-10-01_monthly.json",
        },
    }
    handoff = {
        "schema_version": 1, "handoff_month": month, "target_month": target_month,
        "generated_at": generated_at, "project_directory": str(ROOT),
        "execution_environment": "local", "worktree": False,
        "controller_automation_id": "2026-09", "source_thread_id": source_thread_id,
        "must_use_single_heartbeat": True,
        "monthly_review": report["artifacts"]["monthly_json"],
        "ledger_hashes": {
            "betting_plan_ledger_sha256": _sha256(ledger_path),
            "fixed_odds_shadow_ledger_sha256": _sha256(fixed_path),
            "shadow_prediction_ledger_v2_sha256": _sha256(shadow_path),
        },
        "candidate_decision": report["candidate_decision"],
        "migration_ready": migration_ready,
        "migration_blocker": None if migration_ready else f"complete daily review through {month_end}; current last reviewed sales day is {last_reviewed_sales_day or 'unknown'}",
        "migration_rules": [
            "create one dedicated local controller chat titled 足球预测生产总控（2026-10）",
            "retarget the existing single heartbeat only after the new chat reads this handoff",
            "verify the automation target and next wake before archiving the old controller",
            "never keep two active controller heartbeats",
        ],
    }
    return report, handoff


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an auditable monthly Sporttery review and controller handoff.")
    parser.add_argument("--month", required=True)
    parser.add_argument("--generated-at", default=datetime.now().astimezone().isoformat(timespec="seconds"))
    parser.add_argument("--source-thread-id", default="")
    parser.add_argument("--skip-markdown-write", action="store_true", help="Keep an already materialized Markdown report while refreshing JSON and handoff outputs.")
    args = parser.parse_args()
    report, handoff = build(args.month, args.generated_at, args.source_thread_id)
    report_json = ROOT / f"artifacts/data/sporttery_monthly_review_{args.month}.json"
    report_md = ROOT / f"artifacts/reviews/sporttery_monthly_review_{args.month}.md"
    handoff_json = ROOT / f"artifacts/data/football_automation_handoff_{args.month}.json"
    for path in (report_json, report_md, handoff_json):
        path.parent.mkdir(parents=True, exist_ok=True)
    handoff_json.write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.skip_markdown_write:
        report_md.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"ok": True, "review": str(report_json), "handoff": str(handoff_json)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
