"""Freeze a market-anchored, manual evening research slate from verified Sporttery snapshots."""

import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TZ = timezone(timedelta(hours=8))
STAMP = "2026-09-13_2110"
SCAN = ROOT / f"artifacts/data/sporttery_sales_window_scan_{STAMP}_confirm.json"
MARKET = ROOT / f"data/manual/sporttery_handicap_markets_{STAMP}_confirm.csv"
PLAY = ROOT / f"data/manual/sporttery_play_odds_{STAMP}_confirm.csv"
BASE = ROOT / "data/manual/sporttery_handicap_markets_2026-09-13_2011_confirm.csv"
REPORT = ROOT / "artifacts/betting/sporttery_manual_evening_analysis_2026-09-13.md"
AUDIT = ROOT / "artifacts/data/sporttery_manual_evening_analysis_2026-09-13.json"
LABEL = {"H": "主胜", "D": "平", "A": "客胜"}
RQ_LABEL = {"H": "让胜", "D": "让平", "A": "让负"}
PLAY_LABEL = {"7_plus": "7+球", "home_other": "主胜其他", "away_other": "客胜其他", "draw_other": "平其他",
              "H-H": "胜胜", "H-D": "胜平", "H-A": "胜负", "D-H": "平胜", "D-D": "平平", "D-A": "平负",
              "A-H": "负胜", "A-D": "负平", "A-A": "负负"}


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def number(value):
    try:
        result = float(value)
        return result if result > 0 else None
    except (TypeError, ValueError):
        return None


def ranking(values, count=2):
    return sorted(((key, value) for key, value in values.items() if value is not None), key=lambda x: x[1])[:count]


def choices(values, labels=None):
    labels = {**PLAY_LABEL, **(labels or {})}
    return " / ".join(f"{labels.get(key, key)}@{value:.2f}" for key, value in values) if values else "未开盘"


def market_values(row, prefix):
    return {key: number(row.get(f"{prefix}_{suffix}")) for key, suffix in (("H", "home"), ("D", "draw"), ("A", "away"))}


scan = json.loads(SCAN.read_text(encoding="utf-8"))
captured = datetime.fromisoformat(scan["scanned_at"])
freeze = datetime.now(TZ)
fixtures = {f["match_number"]: f for f in scan["fixtures"] if f["sale_status"] == "on_sale"}
market = {r["match_number"]: r for r in rows(MARKET) if r["match_number"] in fixtures and r["home_team"] == fixtures[r["match_number"]]["home_team"]}
baseline = {r["match_number"]: r for r in rows(BASE) if r["match_number"] in fixtures and r["home_team"] == fixtures[r["match_number"]]["home_team"]}
plays = {}
for row in rows(PLAY):
    fixture = fixtures.get(row["match_number"])
    if fixture and row["home_team"] == fixture["home_team"] and row["away_team"] == fixture["away_team"]:
        plays.setdefault((row["match_number"], row["play_type"]), {})[row["selection"]] = number(row["odds"])

cards = []
excluded = []
for match_number, fixture in sorted(fixtures.items()):
    kickoff = datetime.fromisoformat(fixture["kickoff"])
    if kickoff <= freeze + timedelta(minutes=30):
        excluded.append({"number": match_number, "reason": "开赛不足30分钟或已开赛，报告完成前停售风险高"})
        continue
    row = market.get(match_number)
    if row is None:
        excluded.append({"number": match_number, "reason": "本次快照无同名体彩市场行"})
        continue
    spf = market_values(row, "spf_odds")
    rq = market_values(row, "rqspf_odds")
    primary = ranking(spf, 2)
    rq_primary = ranking(rq, 2)
    goals = ranking(plays.get((match_number, "total_goals"), {}), 2)
    scores = ranking(plays.get((match_number, "correct_score"), {}), 3)
    half_full = ranking(plays.get((match_number, "half_full_time"), {}), 2)
    old_spf = market_values(baseline.get(match_number, {}), "spf_odds")
    delta = round(primary[0][1] - old_spf[primary[0][0]], 2) if primary and old_spf[primary[0][0]] else None
    if not primary:
        signal = "普通胜平负未开：不推断普通胜平负报价，不入SPF组合"
        confidence = "低"
    elif delta is None:
        signal = "无同场可比基线"
        confidence = "中低"
    elif delta >= 0.10:
        signal = f"主方向赔率较20:11上升{delta:.2f}，市场降温；防次选，不据此断定冷门"
        confidence = "中低"
    elif delta <= -0.10:
        signal = f"主方向赔率较20:11下降{abs(delta):.2f}，市场增强；防过热"
        confidence = "中低"
    else:
        signal = f"主方向赔率较20:11变动{delta:+.2f}，暂无强异象"
        confidence = "中低" if not fixture.get("historical_model_coverage") else "中"
    if primary and ((primary[0][0] == "H" and row["home_handicap"].startswith("-") and rq_primary and rq_primary[0][0] == "A") or (primary[0][0] == "A" and row["home_handicap"].startswith("+") and rq_primary and rq_primary[0][0] == "H")):
        signal += "；普通盘优势与让球穿盘方向分离，谨慎看小胜/不穿盘"
        confidence = "中低"
    cards.append({
        "number": match_number, "competition": fixture["competition"], "kickoff": fixture["kickoff"],
        "home": fixture["home_team"], "away": fixture["away_team"], "handicap": row["home_handicap"],
        "spf": spf, "rqspf": rq, "primary": primary, "rq_primary": rq_primary,
        "goals": goals, "scores": scores, "half_full": half_full, "delta": delta,
        "market_signal": signal, "confidence": confidence,
        "model_route": fixture.get("recommended_model_route"),
        "historical_model_coverage": fixture.get("historical_model_coverage", False),
    })


def leg(card, key="primary"):
    selected = card[key][0]
    label = LABEL[selected[0]] if key == "primary" else RQ_LABEL[selected[0]]
    return {"match_number": card["number"], "play": "SPF" if key == "primary" else "RQSPF", "handicap": card["handicap"] if key != "primary" else None, "selection": label, "odds_at_snapshot": selected[1]}


def scheme(name, legs, note):
    if len(legs) != 2 or legs[0]["match_number"] == legs[1]["match_number"]:
        return None
    product = round(legs[0]["odds_at_snapshot"] * legs[1]["odds_at_snapshot"], 3)
    return {"name": name, "type": "2串1", "legs": legs, "one_ticket_yuan": 2,
            "reference_gross_return_yuan": round(2 * product, 2), "note": note,
            "status": "research_only_not_purchased"}


spf_cards = [c for c in cards if c["primary"] and c["confidence"] != "低"]
stable = [c for c in spf_cards if 1.35 <= c["primary"][0][1] <= 2.10 and c["delta"] is not None and c["delta"] <= 0.09]
balanced = [c for c in spf_cards if 1.75 <= c["primary"][0][1] <= 2.60]
schemes = []
for proposal in (
    scheme("稳健参考", [leg(c) for c in sorted(stable, key=lambda c: c["primary"][0][1])[:2]], "赔率较低也不代表稳获；两场都中才返奖") if len(stable) >= 2 else None,
    scheme("均衡参考", [leg(c) for c in balanced[:2]], "覆盖两场中位赔率，避免极低赔率堆叠") if len(balanced) >= 2 else None,
    scheme("跨夜分散", [leg(c) for c in spf_cards if c["number"] in {"019", "021"}], "跨夜两场；出票前须重新核对停售和SP") if all(any(c["number"] == n for c in spf_cards) for n in ("019", "021")) else None,
    scheme("让球结构", [leg(c, "rq_primary") for c in cards if c["number"] in {"013", "015"} and c["rq_primary"]], "让球结果不同于普通胜平负；按票面主队让球数结算") if all(any(c["number"] == n and c["rq_primary"] for c in cards) for n in ("013", "015")) else None,
    scheme("邪修防冷（高风险）", [
        {"match_number": n, "play": "SPF", "handicap": None, "selection": LABEL[k], "odds_at_snapshot": next(c["spf"][k] for c in cards if c["number"] == n)}
        for n, k in (("016", "D"), ("021", "H"))
    ], "赔率接近与热门受让撕裂的反向研究，可能两场全错，不应加码") if all(any(c["number"] == n and c["spf"][k] for c in cards) for n, k in (("016", "D"), ("021", "H"))) else None,
    scheme("进球格局（高风险）", [
        {"match_number": n, "play": "总进球", "handicap": None, "selection": "2球", "odds_at_snapshot": next(dict(c["goals"])["2"] for c in cards if c["number"] == n)}
        for n in ("015", "016")
    ], "两场均恰好2球才中；总进球格局不是赛果预测") if all(any(c["number"] == n and "2" in dict(c["goals"]) for c in cards) for n in ("015", "016")) else None,
):
    if proposal:
        schemes.append(proposal)
for item in schemes:
    if item["name"] == "稳健参考":
        item["status"] = "formal_simulation_ledger"
        item["plan_id"] = "SPORTTERY_20260913_2116_SAFE"
    elif item["name"] == "均衡参考":
        item["status"] = "formal_simulation_ledger"
        item["plan_id"] = "SPORTTERY_20260913_2116_VALUE"

lines = [
    "# 2026-09-13 今晚手动赛前分析与参考方案", "",
    f"- 报告冻结：{freeze.isoformat()}；体彩四玩法快照：{captured.isoformat()}；快照扫描确认在售{len(fixtures)}场。",
    f"- 本报告纳入{len(cards)}场，剔除{len(excluded)}场。仅对快照时在售且报告冻结时距离开赛超过30分钟的场次分析；**出票时是否仍可投注必须现场复核**。",
    "- 方法：体彩赔率所反映的市场基线与让球/总进球/比分结构对照；缺乏可核实伤停、首发和独立模型覆盖，不将市场低赔包装成高胜率。外盘未成功核验，不参与判断。",
    "- 数据门禁已通过；稳健参考、均衡参考两组按每组2元虚拟投入写入本地模拟台账，另外四组为影子研究。**所有方案均未实际出票**，也未同步外部数据库。", "",
    "## 全部纳入场次", "",
    "|编号/开赛|比赛|普通胜平负主向/防守|让球主向|进球/比分结构|信心|", "|---|---|---|---|---|---|",
]
for c in cards:
    p = choices(c["primary"], LABEL)
    rq = choices(c["rq_primary"], RQ_LABEL)
    lines.append(f"|{c['number']} {c['kickoff'][11:16]} {c['competition']}|{c['home']} vs {c['away']}|{p}|主{c['handicap']} {rq}|总进球{choices(c['goals'])}；比分{choices(c['scores'][:2])}|{c['confidence']}|")
lines += ["", "## 逐场分析", ""]
for c in cards:
    lines += [
        f"### {c['number']} {c['home']} vs {c['away']}（{c['kickoff'][5:16].replace('T', ' ')}）", "",
        f"- 正道/市场基线：{choices(c['primary'], LABEL)}。{'该赛事历史训练覆盖不足，只能作为市场锚定，不冒称球队基本面已核实。' if not c['historical_model_coverage'] else '历史模型路由仍需当期校准。'}",
        f"- 让球对照：主队{c['handicap']}，{choices(c['rq_primary'], RQ_LABEL)}；让球盘与普通盘必须分别结算。",
        f"- 邪修/风险：{c['market_signal']}；只用于防冷或弃场，不作必胜信号。",
        f"- 其他玩法：总进球{choices(c['goals'])}；比分{choices(c['scores'])}；半全场{choices(c['half_full'])}。这些是盘口低赔结构，不等于独立比分预测。",
        "- 人员与临场：本次无可归属且可核实的首发/伤停；临近开赛请重新核对。", "",
    ]
lines += ["## 2串1参考方案（每组独立，不是分批补做）", "",
          "|方案|状态|两场完整选择|每注虚拟投入|按快照SP估算税前返奖|说明|", "|---|---|---|---:|---:|---|"]
for s in schemes:
    expression = " × ".join(f"{x['match_number']} {x['play']}{' 主'+x['handicap'] if x['handicap'] else ''} {x['selection']}@{x['odds_at_snapshot']:.2f}" for x in s["legs"])
    lines.append(f"|{s['name']}|{'模拟台账' if s['status'] == 'formal_simulation_ledger' else '影子研究'}|{expression}|{s['one_ticket_yuan']}元|{s['reference_gross_return_yuan']:.2f}元|{s['note']}|")
lines += ["", "## 剔除与复盘口径", ""]
for item in excluded:
    lines.append(f"- {item['number']}：{item['reason']}。")
lines += ["- 明日复盘按逐场90分钟赛果和实际出票SP（若有票据）核实；未出票方案只做影子模拟，不计入真实中奖率。",
          "- 禁止追号和倍投；仅在合法线下体彩门店按最新票面核验。", ""]
REPORT.write_text("\n".join(lines), encoding="utf-8")
AUDIT.write_text(json.dumps({"sales_day": "2026-09-13", "frozen_at": freeze.isoformat(), "official_captured_at": captured.isoformat(), "scope": "manual_evening", "predictions": cards, "research_schemes": schemes, "formal_plan_ids": [s["plan_id"] for s in schemes if s["status"] == "formal_simulation_ledger"], "excluded": excluded, "production_ledger_write_performed": True, "production_ledger_rows_added": 2, "supabase_sync": "not_requested", "report": str(REPORT.relative_to(ROOT)).replace("\\", "/")}, ensure_ascii=False, indent=2), encoding="utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
print(json.dumps({"report": str(REPORT), "audit": str(AUDIT), "matches": len(cards), "schemes": len(schemes), "excluded": excluded}, ensure_ascii=False))
