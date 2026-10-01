import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def rows(path):
    with (ROOT / path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


results_raw = rows("data/manual/sporttery_results_2026-09-07_sales_window.csv")
results = {}
for number in range(1, 10):
    key = f"{number:03}"
    matches = [r for r in results_raw if r["match_number"].endswith(key) and r["status"] == "已完成"]
    if len(matches) != 1:
        raise RuntimeError(f"official result mapping failed for {key}: {len(matches)}")
    results[key] = matches[0]

markets = {r["match_number"].zfill(3): r for r in rows("data/manual/sporttery_handicap_markets_2026-09-07_2102_confirm.csv")}
play_odds = {(r["match_number"].zfill(3), r["play_type"], r["selection"]): float(r["odds"]) for r in rows("data/manual/sporttery_play_odds_2026-09-07_2102_confirm.csv")}

cards = {
    "001": {"main": "主胜/平", "main_hit": True, "handicap": "主-1让负", "handicap_hit": False, "goals": ["1", "2"], "scores": ["1:1", "1:0", "0:1"], "hf": ["D-D", "D-H"], "cause": "主队1:0小胜；不败判断正确，但-1落让平，不能把赢球等同穿盘。"},
    "002": {"main": "主胜/平", "main_hit": True, "handicap": "主-1让负", "handicap_hit": True, "goals": ["1", "2"], "scores": ["1:1", "1:0", "0:1"], "hf": ["D-D", "D-H"], "cause": "1:1验证均衡低比分与防平；半场主领先使半全场脚本失效。"},
    "003": {"main": "主胜", "main_hit": False, "handicap": "主-1让负/让平", "handicap_hit": True, "goals": ["2", "3"], "scores": ["2:1", "1:0", "2:0", "1:1"], "hf": ["D-H", "H-H"], "cause": "0:0冷平；主胜降赔未兑现，让球保护正确但正式价值方案被主胜断腿。"},
    "004": {"main": "客胜", "main_hit": True, "handicap": "客队穿盘，防只赢1球", "handicap_hit": True, "goals": ["2", "3"], "scores": ["1:2", "0:1", "0:2", "1:1"], "hf": ["D-A", "A-A"], "cause": "客队0:1兑现，客胜与比分命中；只赢一球落主+1让平，深层防守分支必要。"},
    "005": {"main": "主胜", "main_hit": False, "handicap": "主-2禁作稳胆", "handicap_hit": True, "goals": ["2", "3"], "scores": ["2:1", "2:0"], "hf": ["H-H", "D-H"], "cause": "1.10超低赔主胜爆冷，0:2客胜；深盘分歧警报正确，但仍把主胜放入稳健组合，属核心错误。"},
    "006": {"main": "主胜/平", "main_hit": False, "handicap": "主+1让胜", "handicap_hit": False, "goals": ["1", "2"], "scores": ["1:1", "1:0", "0:1"], "hf": ["D-D", "D-H"], "cause": "拉齐奥1:2客胜；客胜升赔并未阻止正路，主队+1只落让平，反热门过度。"},
    "007": {"main": "主队不败观察", "main_hit": True, "handicap": "外盘主队0球轻保护", "handicap_hit": True, "goals": ["1", "2"], "scores": ["1:1", "1:0", "0:1"], "hf": ["D-D"], "cause": "0:0；常规主不败与外盘浅盘保护成立，邪修客胜失败，赔率同向移动不等于赛果。"},
    "008": {"main": "客胜", "main_hit": True, "handicap": "主+1让胜/让平", "handicap_hit": True, "goals": ["2", "3"], "scores": ["1:1", "1:2", "2:1"], "hf": ["D-D", "D-A"], "cause": "皇家社会2:3客胜且主+1落让平；胜负与受让保护同时成立，但进球数被明显低估。"},
    "009": {"main": "主胜/平", "main_hit": True, "handicap": "主-1让负", "handicap_hit": False, "goals": ["1", "2"], "scores": ["1:1", "1:0", "0:1"], "hf": ["D-D", "D-H"], "cause": "维多利亚1:0小胜；不败、1球、1:0与平胜命中，但-1实际让平。"},
}


def outcome(h, a):
    return "H" if h > a else "D" if h == a else "A"


theoretical = []
for number, card in cards.items():
    r = results[number]
    h, a = map(int, r["full_time_score"].split(":"))
    hh, ha = map(int, r["half_time_score"].split(":"))
    actual_goals = str(h + a) if h + a < 7 else "7+"
    actual_hf = f"{outcome(hh, ha)}-{outcome(h, a)}"
    goal_hit = actual_goals in card["goals"]
    score_hit = r["full_time_score"] in card["scores"]
    hf_hit = actual_hf in card["hf"]
    goal_stake = 2.0 * len(card["goals"])
    score_stake = 2.0 * len(card["scores"])
    goal_payout = 2.0 * play_odds.get((number, "total_goals", actual_goals), 0.0) if goal_hit else 0.0
    score_payout = 2.0 * play_odds.get((number, "correct_score", r["full_time_score"]), 0.0) if score_hit else 0.0
    theoretical.append({
        "number": number, "actual_goals": actual_goals, "actual_hf": actual_hf,
        "goal_hit": goal_hit, "score_hit": score_hit, "hf_hit": hf_hit,
        "goal_stake": goal_stake, "goal_payout": round(goal_payout, 2),
        "score_stake": score_stake, "score_payout": round(score_payout, 2),
    })

real = [r for r in rows("data/manual/betting_plan_ledger.csv") if r["date"] == "2026-09-07"]
fixed = [r for r in rows("data/manual/fixed_odds_shadow_ledger.csv") if r["date"] == "2026-09-07"]

lines = [
    "# 2026-09-07销售日9场详细复盘", "",
    f"完成时间：{datetime.now().astimezone().isoformat(timespec='seconds')}。体彩销售窗口延伸至9月8日，官方导入16条赛果；001—009按编号、主客队和已完成状态唯一核实，9场均取得90分钟正式赛果。所有金额均为本地模拟或理论观察，不代表真实下注。", "",
    "## 当日完整赛程与逐场赛果", "",
    "|编号|赛事|比赛|半场|90分钟|SPF|让球赛果|赛前主要方向|结果|", "|---|---|---|---|---|---|---|---|---|",
]
for number in sorted(results):
    r, card = results[number], cards[number]
    lines.append(f"|{number}|{r['competition']}|{r['home_team']}—{r['away_team']}|{r['half_time_score']}|{r['full_time_score']}|{r['spf_result']}|{r['handicap']} {r['rqspf_result']}|{card['main']}|{'命中' if card['main_hit'] else '未中'}|")

lines += ["", "## 逐场预测、多玩法与错误归因", ""]
for item in theoretical:
    number, card, r = item["number"], cards[item["number"]], results[item["number"]]
    lines += [
        f"### {number} {r['home_team']} vs {r['away_team']}（{r['full_time_score']}）",
        f"- 胜负方向：{card['main']}，{'命中' if card['main_hit'] else '未中'}；让球方向：{card['handicap']}，{'命中/风险识别有效' if card['handicap_hit'] else '未中'}。",
        f"- 总进球观察：{'/'.join(card['goals'])}，实际{item['actual_goals']}球，{'命中' if item['goal_hit'] else '未中'}；假设本金{item['goal_stake']:.0f}元、返奖{item['goal_payout']:.2f}元、净收益{item['goal_payout']-item['goal_stake']:.2f}元。",
        f"- 比分观察：{'/'.join(card['scores'])}，实际{r['full_time_score']}，{'命中' if item['score_hit'] else '未中'}；假设本金{item['score_stake']:.0f}元、返奖{item['score_payout']:.2f}元、净收益{item['score_payout']-item['score_stake']:.2f}元。",
        f"- 半全场观察：{'/'.join(card['hf'])}，实际{item['actual_hf']}，{'命中' if item['hf_hit'] else '未中'}。",
        f"- 归因：{card['cause']}", "",
    ]

lines += ["## 正式模拟方案逐腿结算", ""]
for row in real:
    lines += [
        f"### {row['plan_type']}：{row['plan_id']}",
        f"- 冻结选择：{row['selections']}。",
        f"- 逐腿：{row['review_note'].replace('体彩官方接口自动复盘：', '')}。",
        f"- 结果：{row['result']}；模拟本金{float(row['stake']):.2f}元，返奖{float(row['payout']):.2f}元，净收益{float(row['net_profit']):.2f}元，ROI {float(row['roi']):.2%}。", "",
    ]

real_stake = sum(float(r["stake"]) for r in real)
real_payout = sum(float(r["payout"]) for r in real)
lines += [
    "## 其他冻结组合（观察，不入正式台账）", "",
    "|方案|选择|结果|理论本金|理论返奖|净收益|", "|---|---|---|---:|---:|---:|",
    "|防冷|001主/平 × 002主/平|命中主胜×平局子注|8.00|9.91|+1.91|",
    "|博高|001让平 × 002让平 × 003让平|未中：002、003均为让负|2.00|0.00|-2.00|",
    "|强胆复式|004客胜 × 001主/平|命中004客胜×001主胜子注|4.00|5.57|+1.57|", "",
    "## 固定赔率影子与邪修影子", "",
]
for row in fixed:
    lines += [
        f"- 固定赔率影子 `{row['plan_id']}`：006客胜命中，007主胜未中（0:0断腿）；组合{row['result']}。虚拟本金{float(row['stake']):.2f}元，返奖{float(row['payout']):.2f}元，净收益{float(row['net_profit']):.2f}元。",
    ]
lines += [
    "- 邪修影子：007阿罗卡客胜@2.53，实际0:0，未中；虚拟本金2.00元，返奖0元，净收益-2.00元。体彩和外盘同时向客队移动，但亚洲0球仍保护主队；说明赔率异动只能触发复核或避开，不能直接等同客胜。", "",
    "## 汇总与下一轮修正", "",
    f"- 逐场胜负主方向：{sum(c['main_hit'] for c in cards.values())}/9，命中率{sum(c['main_hit'] for c in cards.values())/9:.2%}。总进球观察4/9；比分观察4/9；半全场观察3/9。",
    f"- 正式模拟方案：{len(real)}组，命中0组；模拟投入{real_stake:.2f}元，返奖{real_payout:.2f}元，净收益{real_payout-real_stake:.2f}元，ROI {(real_payout-real_stake)/real_stake:.2%}。",
    "- 两组正式方案共享004且004兑现，但各自分别被005低赔主胜爆冷、003主胜冷平截断。组合相关性约束没有失守，问题在于把赔率最低的005当作安全腿，以及对003降赔主胜的信任过高。",
    "- 固定赔率影子与邪修影子均未中；007最终0:0同时否定固定影子的主胜和邪修影子的客胜，反而支持常规层的放弃/主不败策略。",
    "- 改进：低于1.20的主胜若与深盘穿盘定价矛盾，不得自动进入稳健组合；主胜和让球穿盘必须分开评分；赔率异动只作为降级、复核或放弃信号；低比分均衡盘继续优先双选和1—2球结构。",
]

report_path = ROOT / "artifacts/data/sporttery_full_review_2026-09-07_1300_detailed.md"
report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
audit = {
    "sales_day": "2026-09-07", "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    "official_matches": 9, "main_hits": sum(c["main_hit"] for c in cards.values()),
    "goal_hits": sum(i["goal_hit"] for i in theoretical), "score_hits": sum(i["score_hit"] for i in theoretical),
    "half_full_hits": sum(i["hf_hit"] for i in theoretical),
    "formal": {"plans": len(real), "hits": sum(r["result"] == "命中" for r in real), "stake": real_stake, "payout": real_payout, "net": real_payout-real_stake},
    "fixed_shadow": {"plans": len(fixed), "hits": sum(r["result"] == "命中" for r in fixed)},
    "contrarian_shadow": {"plans": 1, "hits": 0, "stake": 2.0, "payout": 0.0, "net": -2.0},
    "report": str(report_path.relative_to(ROOT)).replace("\\", "/"),
    "production_ledger_sha256": hashlib.sha256((ROOT / "data/manual/betting_plan_ledger.csv").read_bytes()).hexdigest(),
}
audit_path = ROOT / "artifacts/data/review_20260907_1300_detailed.json"
audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(audit, ensure_ascii=False, indent=2))
