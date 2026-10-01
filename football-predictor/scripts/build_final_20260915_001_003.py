import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-09-15"
NUMBERS = ["001", "002", "003"]
FINAL = ROOT / "data/manual/sporttery_handicap_markets_2026-09-15_1636_final_001-003.csv"
BASE = ROOT / "data/manual/sporttery_handicap_markets_2026-09-15_1430_confirm.csv"
PLAYS = ROOT / "data/manual/sporttery_play_odds_2026-09-15_1636_confirm.csv"
SCAN = ROOT / "artifacts/data/sporttery_sales_window_scan_2026-09-15_1636_confirm.json"
REPORT = ROOT / "artifacts/betting/sporttery_final_analysis_2026-09-15_1637_001-003.md"
AUDIT = ROOT / "artifacts/data/sporttery_final_analysis_2026-09-15_1637_001-003.json"
PLANS = ROOT / "artifacts/data/sporttery_plans_2026-09-15_1637_001-003.csv"


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def flt(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


fixtures = {r["match_number"].zfill(3): r for r in rows(FINAL)}
base = {
    r["match_number"].zfill(3): r
    for r in rows(BASE)
    if r["match_number"].zfill(3) in NUMBERS
    and r["home_team"] == fixtures[r["match_number"].zfill(3)]["home_team"]
    and r["away_team"] == fixtures[r["match_number"].zfill(3)]["away_team"]
}
play_map = {}
for r in rows(PLAYS):
    n = r["match_number"].zfill(3)
    if n not in NUMBERS or r.get("home_team") != fixtures[n]["home_team"] or r.get("away_team") != fixtures[n]["away_team"]:
        continue
    key = (n, r["play_type"])
    odds = flt(r["odds"])
    if odds is not None:
        play_map.setdefault(key, {})[r["selection"]] = min(odds, play_map.get(key, {}).get(r["selection"], odds))


def low(n, play, count):
    return sorted(play_map.get((n, play), {}).items(), key=lambda item: item[1])[:count]


def fmt(items, label=lambda value: value):
    return "/".join(f"{label(k)}@{v:.2f}" for k, v in items) if items else "未开"


spf_label = {"H": "主胜", "D": "平", "A": "客胜"}
rq_label = {"H": "让胜", "D": "让平", "A": "让负"}
hf_label = {"H-H": "胜胜", "D-H": "平胜", "A-H": "负胜", "H-D": "胜平", "D-D": "平平", "A-D": "负平", "H-A": "胜负", "D-A": "平负", "A-A": "负负"}

cards = []
for n in NUMBERS:
    r, old = fixtures[n], base[n]
    spf = {"H": flt(r["spf_odds_home"]), "D": flt(r["spf_odds_draw"]), "A": flt(r["spf_odds_away"])}
    rq = {"H": flt(r["rqspf_odds_home"]), "D": flt(r["rqspf_odds_draw"]), "A": flt(r["rqspf_odds_away"])}
    old_spf = {"H": flt(old["spf_odds_home"]), "D": flt(old["spf_odds_draw"]), "A": flt(old["spf_odds_away"])}
    order = sorted(spf.items(), key=lambda item: item[1])
    rq_order = sorted(rq.items(), key=lambda item: item[1])
    direction, defense = order[0], order[1]
    delta = direction[1] - old_spf[direction[0]]
    all_delta = {k: round(spf[k] - old_spf[k], 2) for k in spf}
    movement = f"胜{all_delta['H']:+.2f}/平{all_delta['D']:+.2f}/负{all_delta['A']:+.2f}"
    if n == "001":
        orthodox = "海港客胜为主；客胜由2.28降至2.15，获得真实市场支持，但+1让胜仅1.52，提示主队不败/一球差风险。"
        contrarian = "热门方向增强但让球端明显不支持穿盘，邪修只防平局，不反买主胜。"
        confidence = "中等"
    elif n == "002":
        orthodox = "大田主胜为主；主胜1.86降至1.80，但-1让负1.78最热，判断主队更像小胜或被逼平。"
        contrarian = "SPF主胜与-1让负同热，属于胜而不穿结构；防平优先于防客胜。"
        confidence = "中等"
    else:
        orthodox = "韩国亚客胜为主；1.12超低赔确认实力差，但+2让胜2.20低于让负2.38，三球大胜没有形成一致支持。"
        contrarian = "大热拥挤且深盘撕裂，胜负仍顺客胜，盘口层防韩国只赢一至两球。"
        confidence = "中低"
    cards.append({
        "number": n, "competition": r["competition"], "kickoff": r["kickoff_time"], "home": r["home_team"], "away": r["away_team"],
        "handicap": r["home_handicap"], "spf": spf, "rq": rq, "primary": spf_label[direction[0]], "primary_odds": direction[1],
        "defense": spf_label[defense[0]], "defense_odds": defense[1], "rq_primary": rq_label[rq_order[0][0]], "rq_odds": rq_order[0][1],
        "movement": movement, "orthodox": orthodox, "contrarian": contrarian, "confidence": confidence,
        "goals": low(n, "total_goals", 2), "scores": low(n, "correct_score", 3), "half_full": low(n, "half_full_time", 2),
    })

schemes = [
    {"plan_id": "SHADOW_20260915_1637_SAFE", "plan_type": "稳健观察", "title": "002主胜 × 003客胜", "stake": 50.0, "bets": 1, "odds_min": 2.016, "odds_max": 2.016, "selections": "002 大田市民vs京都 胜平负:主胜@1.80 + 003 卡塔尔亚vs韩国亚 胜平负:客胜@1.12", "risk": "两腿均为热门；003超低赔贡献有限且杯赛阵容不确定。", "shadow": True},
    {"plan_id": "SHADOW_20260915_1637_VALUE", "plan_type": "价值观察", "title": "001客胜 × 002主胜", "stake": 20.0, "bets": 1, "odds_min": 3.870, "odds_max": 3.870, "selections": "001 叻武里vs上海海港 胜平负:客胜@2.15 + 002 大田市民vs京都 胜平负:主胜@1.80", "risk": "001让球端不支持客队穿盘；两场均属未覆盖赛事域。", "shadow": True},
    {"plan_id": "SHADOW_20260915_1637_HANDICAP", "plan_type": "让球结构观察", "title": "001让胜 × 002让负", "stake": 20.0, "bets": 1, "odds_min": 2.7056, "odds_max": 2.7056, "selections": "001 叻武里(+1) 让球胜平负:让胜@1.52 + 002 大田市民(-1) 让球胜平负:让负@1.78", "risk": "同时押注两场强方不穿盘，依赖一球差/不胜结构。", "shadow": True},
    {"plan_id": "SHADOW_20260915_1637_HEDGE", "plan_type": "防冷复式", "title": "001客胜/平 × 002主胜/平", "stake": 8.0, "bets": 4, "odds_min": 3.87, "odds_max": 12.07, "selections": "001 客胜@2.15/平@3.40 + 002 主胜@1.80/平@3.55", "risk": "4注复式仍不覆盖两场任一主负方向；最高返奖取决于具体命中组合。", "shadow": True},
    {"plan_id": "SHADOW_20260915_1637_GOALS", "plan_type": "总进球复式", "title": "001进球2/3 × 002进球2/3", "stake": 8.0, "bets": 4, "odds_min": 12.59, "odds_max": 13.69, "selections": "001 总进球2@3.65/3@3.75 + 002 总进球2@3.45/3@3.65", "risk": "进球玩法赔率高、方差大，只作小额结构样本。", "shadow": True},
    {"plan_id": "SHADOW_20260915_1637_SCORE", "plan_type": "比分观察", "title": "001 1:1/1:2 × 003 0:2/0:3", "stake": 8.0, "bets": 4, "odds_min": 35.94, "odds_max": 56.00, "selections": "001 比分1:1@6.25/1:2@8.00 + 003 比分0:2@5.75/0:3@7.00", "risk": "高方差窄覆盖，任何额外进球都会断票。", "shadow": True},
    {"plan_id": "SHADOW_20260915_1637_HALF_FULL", "plan_type": "半全场观察", "title": "002胜胜 × 003负负", "stake": 2.0, "bets": 1, "odds_min": 4.4835, "odds_max": 4.4835, "selections": "002 半全场:胜胜@3.05 + 003 半全场:负负@1.47", "risk": "要求两支热门从半场领先到终场，容错很低。", "shadow": True},
    {"plan_id": "MULTI_PLAY_FIXED_ODDS_SHADOW", "plan_type": "固定赔率观察", "title": "目标8.00固定赔率影子", "stake": 2.0, "bets": 1, "odds_min": 8.4198, "odds_max": 8.4198, "selections": "001 叻武里vs上海海港 胜平负:客胜@2.15 + 002 大田市民(-1)vs京都 让球胜平负:让负@1.78 + 003 卡塔尔亚(+2)vs韩国亚 让球胜平负:让胜@2.20", "risk": "三腿且两腿押不穿盘，只用于固定赔率长期统计。", "shadow": True},
    {"plan_id": "CONTRARIAN_20260915_1637", "plan_type": "邪修方案", "title": "003深盘撕裂单场理论观察", "stake": 2.0, "bets": 1, "odds_min": 2.20, "odds_max": 2.20, "selections": "003 卡塔尔亚(+2) 让球胜平负:让胜@2.20", "risk": "单关资格未核实，只作理论影子；赔率异象不是赛果保证，禁止追损或加倍。", "shadow": True},
]

fields = ["plan_id", "plan_type", "title", "stake", "bet_count", "base_bet_unit", "multiplier", "amount_per_bet", "total_stake", "unused_budget", "estimated_odds_min", "estimated_odds_max", "estimated_payout_min", "estimated_payout_max", "estimated_net_min", "estimated_net_max", "selections", "rationale", "risk_notes", "is_shadow", "eligibility_note"]
with PLANS.open("w", encoding="utf-8-sig", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    for s in schemes:
        payout_min, payout_max = s["stake"] * s["odds_min"], s["stake"] * s["odds_max"]
        writer.writerow({"plan_id": s["plan_id"], "plan_type": s["plan_type"], "title": s["title"], "stake": s["stake"], "bet_count": s["bets"], "base_bet_unit": 2, "multiplier": 1, "amount_per_bet": s["stake"] / s["bets"], "total_stake": s["stake"], "unused_budget": 0, "estimated_odds_min": s["odds_min"], "estimated_odds_max": s["odds_max"], "estimated_payout_min": round(payout_min, 2), "estimated_payout_max": round(payout_max, 2), "estimated_net_min": round(payout_min-s["stake"], 2), "estimated_net_max": round(payout_max-s["stake"], 2), "selections": s["selections"], "rationale": "按16:36体彩官方赔率冻结的结构化观察方案。", "risk_notes": s["risk"], "is_shadow": True, "eligibility_note": "影子研究，不进入正式模拟投注台账。"})

lines = [
    "# 2026-09-15 体彩001—003终版分析与方案", "",
    "执行时间：北京时间2026-09-15 16:37；16:36重新抓取体彩SPF/RQSPF、总进球、比分和半全场。001—003均在售且未开赛，终版门禁为`READY_FOR_FINAL_ANALYSIS`，17:45硬锁。", "",
    "数据边界：The Odds此前HTTP 401且仅余1 credit，本批未循环消耗，外盘映射0/3并排除；影子v2三场均因赛事不在训练域而`blocked`，没有独立模型概率。故本批提供完整市场预测和多组影子方案，但正式模拟台账0入账。", "",
    "## 完整赛程与逐场预测", "",
    "|编号|赛事/开赛|比赛|SPF与14:30变化|让球判断|总进球|比分|半全场|正道/邪修与信心|", "|---|---|---|---|---|---|---|---|---|",
]
for c in cards:
    spf_text = f"{c['primary']}@{c['primary_odds']:.2f}，防{c['defense']}@{c['defense_odds']:.2f}；{c['movement']}"
    rq_order = sorted(c["rq"].items(), key=lambda item: item[1])[:2]
    rq_text = f"{c['handicap']} {fmt(rq_order, lambda k: rq_label[k])}"
    lines.append(f"|{c['number']}|{c['competition']} {c['kickoff'][11:]}|{c['home']}—{c['away']}|{spf_text}|{rq_text}|{fmt(c['goals'])}|{fmt(c['scores'])}|{fmt(c['half_full'], lambda k: hf_label.get(k,k))}|{c['orthodox']} 邪修：{c['contrarian']} 信心{c['confidence']}|")

lines += ["", "## 逐场详细依据", ""]
for c in cards:
    lines += [f"### {c['number']} {c['home']} vs {c['away']}", f"- 正道：{c['orthodox']}", f"- 让球：主队{c['handicap']}，市场首选{c['rq_primary']}@{c['rq_odds']:.2f}；胜负与穿盘分开判断。", f"- 邪修：{c['contrarian']} 该信号只用于降级或防冷，不能解释为机构预告赛果。", f"- 多玩法：总进球{fmt(c['goals'])}；比分{fmt(c['scores'])}；半全场{fmt(c['half_full'], lambda k: hf_label.get(k,k))}。", "- 情报边界：无可核验统一伤停、确认首发、xG或旅行负荷映射，不写成‘阵容完整’，也不提高金额。", ""]

lines += ["## 真实入账方案", "", "本批0组、0元。官方终版门禁虽通过，但三场影子模型均被赛事训练域门禁拦截，只有市场隐含方向，没有可审计的独立模型概率；按规则不得把纯赔率方向写入正式模拟台账。", "", "## 多组观察方案（均不入账）", "", "|方案|完整选择|串关/注数|本金|组合赔率|预计返奖|主要风险|", "|---|---|---:|---:|---:|---:|---|"]
for s in schemes:
    payout_min, payout_max = s["stake"] * s["odds_min"], s["stake"] * s["odds_max"]
    odds_text = f"{s['odds_min']:.4f}" if s["odds_min"] == s["odds_max"] else f"{s['odds_min']:.4f}—{s['odds_max']:.4f}"
    payout_text = f"{payout_min:.2f}元" if payout_min == payout_max else f"{payout_min:.2f}—{payout_max:.2f}元"
    lines.append(f"|{s['plan_type']}：{s['title']}|{s['selections']}|{s['bets']}注，倍数1|{s['stake']:.0f}元|{odds_text}|{payout_text}|{s['risk']}|")

lines += ["", "## 固定赔率影子方案（不入账）", "", "已找到区间[6.00,10.00]内的三腿组合：001客胜@2.15 × 002(-1)让负@1.78 × 003(+2)让胜@2.20，总赔率8.4198，2元虚拟注，预计返奖16.84元。该方案单独写入固定赔率影子台账。", "", "## 邪修方案（独立影子研究）", "", "003卡塔尔亚(+2)让胜@2.20，2元虚拟计量；单关资格未核实，因此只作理论观察、不计可出票收益。依据是韩国亚客胜1.12极热，但+2盘口让胜2.20低于让负2.38，胜负与穿三球明显撕裂；只作为赔率异象样本，不倍投、不追损。", "", "## 后续与复盘", "", "- 18:45处理004—005；21:00处理006—014，届时必须各自重新抓取，不能复用本批赔率。", "- 2026-09-16 13:00逐场复盘；正式、固定赔率影子、邪修和其他观察方案分开计算投入、返奖、净收益和ROI。", "- 本销售日未获Supabase同步授权，仅本地保存。", ""]

REPORT.write_text("\n".join(lines), encoding="utf-8")
payload = {"schema_version": 1, "sales_day": DAY, "stage": "final", "scope": "001-003", "analysis_at": "2026-09-15T16:37:21+08:00", "official_captured_at": json.loads(SCAN.read_text(encoding="utf-8"))["scanned_at"], "gate": "READY_FOR_FINAL_ANALYSIS", "matches": cards, "formal_plans": [], "formal_plan_reason": "no independent model probability; all three shadow model rows blocked outside training domain", "shadow_schemes": schemes, "fixed_odds_shadow_plan_id": "MULTI_PLAY_FIXED_ODDS_SHADOW", "contrarian_market_shadow": {"status": "candidate", "is_shadow": True, "production_ledger_write": False, "rule_version": "docs/contrarian_market_shadow.md", "match_number": "003", "kickoff": "2026-09-15T18:30:00+08:00", "basic_direction": "韩国亚客胜", "signal": "SPF客胜1.12超低热度与主队+2让胜2.20低于让负2.38的深盘撕裂", "selection": "卡塔尔亚(+2)让胜", "odds": 2.20, "virtual_stake": 2.0, "single_bet_qualification": "unverified_theoretical_observation", "funding_sentiment": "unknown", "invalid_if": "停售、盘口变化或无法唯一映射", "data_gap": "无成交量、投注占比、统一伤停与首发"}, "production_ledger_write_performed": False, "report": str(REPORT.relative_to(ROOT)).replace("\\", "/"), "plans_csv": str(PLANS.relative_to(ROOT)).replace("\\", "/"), "review_due_at": "2026-09-16T13:00:00+08:00", "supabase_sync": "not_authorized_for_2026-09-15"}
AUDIT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"status": "completed", "matches": len(cards), "formal_plans": 0, "shadow_schemes": len(schemes), "report": payload["report"]}, ensure_ascii=False))
