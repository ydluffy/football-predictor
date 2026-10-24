"""Build a no-ledger early baseline from two frozen Sporttery snapshots."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTCOME_LABELS = {"H": "主胜", "D": "平", "A": "客胜"}
RQ_LABELS = {"H": "让胜", "D": "让平", "A": "让负"}
HF_LABELS = {
    "H-H": "胜胜", "H-D": "胜平", "H-A": "胜负",
    "D-H": "平胜", "D-D": "平平", "D-A": "平负",
    "A-H": "负胜", "A-D": "负平", "A-A": "负负",
}


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def f(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def exact_market(source: list[dict[str, str]], fixture: dict) -> dict[str, str]:
    found = [row for row in source if row["match_number"] == fixture["match_number"]
             and row["home_team"] == fixture["home_team"] and row["away_team"] == fixture["away_team"]]
    if len(found) != 1:
        raise ValueError(f"market mapping {fixture['match_number']}: {len(found)}")
    return found[0]


def lowest(values: dict[str, float | None], labels: dict[str, str], count: int = 2) -> list[dict]:
    ordered = sorted(((key, value) for key, value in values.items() if value is not None), key=lambda x: x[1])
    return [{"selection": labels[key], "odds": value} for key, value in ordered[:count]]


def play_lowest(source: list[dict[str, str]], fixture: dict, play: str, count: int) -> list[dict]:
    found = [row for row in source if row["match_number"] == fixture["match_number"]
             and row["home_team"] == fixture["home_team"] and row["away_team"] == fixture["away_team"]
             and row["play_type"] == play and f(row["odds"]) is not None]
    found.sort(key=lambda row: float(row["odds"]))
    result = []
    for row in found[:count]:
        selection = row["selection"]
        if play == "half_full_time":
            selection = HF_LABELS.get(selection, selection)
        elif play == "total_goals" and selection == "7_plus":
            selection = "7+"
        result.append({"selection": selection, "odds": float(row["odds"])})
    return result


def fmt(items: list[dict]) -> str:
    return "/".join(f"{item['selection']}@{item['odds']:.2f}" for item in items) or "未开"


def delta_text(current: dict[str, float | None], previous: dict[str, float | None]) -> str:
    parts = []
    labels = {"H": "胜", "D": "平", "A": "负"}
    for key in ("H", "D", "A"):
        if current[key] is not None and previous[key] is not None:
            diff = current[key] - previous[key]
            parts.append(f"{labels[key]}{diff:+.2f}")
    return "/".join(parts) or "不可比"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sales-day", required=True)
    parser.add_argument("--scan-json", required=True)
    parser.add_argument("--market-csv", required=True)
    parser.add_argument("--previous-market-csv", required=True)
    parser.add_argument("--play-odds-csv", required=True)
    parser.add_argument("--scheduled-at", required=True)
    parser.add_argument("--report-output", required=True)
    parser.add_argument("--audit-output", required=True)
    args = parser.parse_args()

    scan_path = ROOT / args.scan_json
    market_path = ROOT / args.market_csv
    old_path = ROOT / args.previous_market_csv
    play_path = ROOT / args.play_odds_csv
    scan = json.loads(scan_path.read_text(encoding="utf-8"))
    current_rows, old_rows, play_rows = rows(market_path), rows(old_path), rows(play_path)
    results = []
    on_sale_fixtures = [fixture for fixture in scan["fixtures"] if fixture.get("sale_status") == "on_sale"]
    stopped_fixtures = [fixture for fixture in scan["fixtures"] if fixture.get("sale_status") == "stopped"]
    for fixture in on_sale_fixtures:
        cur, old = exact_market(current_rows, fixture), exact_market(old_rows, fixture)
        spf = {key: f(cur[f"spf_odds_{name}"]) for key, name in (("H", "home"), ("D", "draw"), ("A", "away"))}
        old_spf = {key: f(old[f"spf_odds_{name}"]) for key, name in (("H", "home"), ("D", "draw"), ("A", "away"))}
        rq = {key: f(cur[f"rqspf_odds_{name}"]) for key, name in (("H", "home"), ("D", "draw"), ("A", "away"))}
        old_rq = {key: f(old[f"rqspf_odds_{name}"]) for key, name in (("H", "home"), ("D", "draw"), ("A", "away"))}
        spf_order = lowest(spf, OUTCOME_LABELS)
        rq_order = lowest(rq, RQ_LABELS)
        goals = play_lowest(play_rows, fixture, "total_goals", 2)
        scores = play_lowest(play_rows, fixture, "correct_score", 3)
        half_full = play_lowest(play_rows, fixture, "half_full_time", 2)
        risks = []
        if not spf_order:
            risks.append("SPF未开，仅让球基线")
        if abs(int(cur["home_handicap"])) >= 2:
            risks.append("深盘，胜负与穿盘分离")
        if "杯" in fixture["competition"] or "亚冠" in fixture["competition"] or "亚运" in fixture["competition"]:
            risks.append("杯赛/赛会制轮换风险")
        if spf_order and spf_order[0]["odds"] <= 1.30:
            risks.append("超低赔热门，禁作单一串关锚")
        if not fixture["competition_known"]:
            risks.append("赛事属性训练域未覆盖")
        if not risks:
            risks.append("仅市场基线，无首发伤停增益")
        all_diffs = [abs((spf[k] or 0) - (old_spf[k] or 0)) for k in spf if spf[k] is not None and old_spf[k] is not None]
        all_diffs += [abs((rq[k] or 0) - (old_rq[k] or 0)) for k in rq if rq[k] is not None and old_rq[k] is not None]
        movement = "显著" if all_diffs and max(all_diffs) >= 0.15 else "一般" if all_diffs and max(all_diffs) >= 0.05 else "稳定"
        results.append({
            "number": fixture["match_number"], "competition": fixture["competition"],
            "kickoff": fixture["kickoff"], "home": fixture["home_team"], "away": fixture["away_team"],
            "handicap": cur["home_handicap"], "spf": spf, "rqspf": rq,
            "spf_primary": spf_order[0] if spf_order else None,
            "spf_defense": spf_order[1] if len(spf_order) > 1 else None,
            "rqspf_primary": rq_order[0] if rq_order else None,
            "rqspf_defense": rq_order[1] if len(rq_order) > 1 else None,
            "goals": goals, "scores": scores, "half_full": half_full,
            "spf_delta": delta_text(spf, old_spf), "rqspf_delta": delta_text(rq, old_rq),
            "movement_level": movement, "risks": risks,
            "confidence": "低（纯市场）" if not spf_order or abs(int(cur["home_handicap"])) >= 2 else "中低（纯市场）",
        })

    completed_at = datetime.now().astimezone().replace(microsecond=0).isoformat()
    audit = {
        "schema_version": 1, "sales_day": args.sales_day, "stage": "early_baseline",
        "scheduled_at": args.scheduled_at, "captured_at": scan["scanned_at"], "completed_at": completed_at,
        "fixture_count": len(results), "predictions": results,
        "excluded_stopped_match_numbers": [fixture["match_number"] for fixture in stopped_fixtures],
        "external_odds": {
            "primary_status": "quota_insufficient",
            "primary_remaining_credits": 1,
            "effective_status": "available_via_nowscore",
            "nowscore_mapped_fixtures": 9,
            "nowscore_research_eligible_rows": 125,
            "production_model_feature_ready": False,
            "reason": "The Odds API quota is insufficient; Nowscore mapped all 9 on-sale fixtures and is retained as research evidence only.",
        },
        "production_ledger_write_performed": False, "fixed_shadow_write_performed": False,
        "contrarian_shadow_write_performed": False,
        "source_files": {args.scan_json: sha(scan_path), args.market_csv: sha(market_path), args.previous_market_csv: sha(old_path), args.play_odds_csv: sha(play_path)},
    }
    audit_path = ROOT / args.audit_output
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        f"# {args.sales_day} 全场早期基线分析",
        "",
        f"计划15:00；固定心跳于15:06执行，实际体彩四玩法冻结于 {scan['scanned_at']}，覆盖{len(results)}场。",
        "本阶段只冻结赔率变化和市场基线，不生成正式、固定赔率或邪修投注方案，不写任何投注台账。所有方向均为体彩隐含市场倾向，不是独立模型保证。",
        "",
        f"## {len(results)}场行程、赔率变化与基线方向",
        "",
        "|编号|赛事|比赛|开赛|SPF现价|让球现价|11:06→当前变化|市场基线预测|进球/比分/半全场|风险与置信|",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for item in results:
        spf_text = "/".join("-" if item["spf"][key] is None else f"{item['spf'][key]:.2f}" for key in ("H", "D", "A"))
        rq_text = "/".join("-" if item["rqspf"][key] is None else f"{item['rqspf'][key]:.2f}" for key in ("H", "D", "A"))
        spf_pick = item["spf_primary"]["selection"] if item["spf_primary"] else "SPF未开"
        rq_pick = item["rqspf_primary"]["selection"] if item["rqspf_primary"] else "让球未开"
        extra = f"进球{fmt(item['goals'])}；比分{fmt(item['scores'])}；半全场{fmt(item['half_full'])}"
        lines.append(
            f"|{item['number']}|{item['competition']}|{item['home']}—{item['away']}|{item['kickoff'][11:16]}|{spf_text}|"
            f"{item['handicap']}：{rq_text}|SPF {item['spf_delta']}；让球 {item['rqspf_delta']}（{item['movement_level']}）|"
            f"{spf_pick}；{rq_pick}|{extra}|{'；'.join(item['risks'])}；{item['confidence']}|"
        )
    lines += [
        "", "## 内外盘与让球解释", "",
        f"- 体彩内盘：{len(results)}场在售比赛重新抓取并完成四玩法归档；024、025已开赛/停止，不进入本次基线。",
        "- 外盘：The Odds API仅余1 credit，不足以完成多市场刷新；捷报后备本批9/9唯一映射，研究合格125行。捷报只作对照证据，不升级为生产模型特征。",
        "- 让球端按主队视角逐场保留整数盘口。+2/-2深盘不与普通胜平负合并；强队取胜与能否穿盘分别判断。",
        f"- 阵容、伤停、xG与旅行负荷没有形成{len(results)}场统一可核验覆盖，不能写成无伤停或阵容完整，也不能提高投注金额。",
        "", "## 真实入账方案", "",
        "本轮0组。早期基线禁止生成或入账投注方案，正式方案将在各批终版重新抓取后单独生成。",
        "", "## 固定赔率影子方案（不入账）", "",
        "本轮0组；固定赔率影子只允许终版阶段冻结。",
        "", "## 邪修方案（独立影子研究）", "",
        "本轮只记录赔率异动观察，不冻结组合、不计收益。重点关注显著变化、深盘和低赔热门，终版仍需正道基本面与最新赔率交叉校验。",
        "", "## 后续批次", "",
        "- 16:30：001—003终版分析与完整方案，17:45硬锁。",
        "- 22:00：004—009终版分析与完整方案，22:45硬锁。",
        "- 2026-09-28 13:00：001—009逐场详细复盘。",
        "", "## 审计", "",
        f"- 官方扫描：{args.scan_json}", f"- 体彩市场：{args.market_csv}", f"- 体彩四玩法：{args.play_odds_csv}",
        f"- JSON审计：{args.audit_output}", "- Supabase：本销售日未获明确同步授权，本轮仅本地保存。", "",
    ]
    report_path = ROOT / args.report_output
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "completed", "fixtures": len(results), "captured_at": scan["scanned_at"], "report": str(report_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
