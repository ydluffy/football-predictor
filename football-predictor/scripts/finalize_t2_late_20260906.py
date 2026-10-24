import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TZ = timezone(timedelta(hours=8))
NOW = datetime.now(TZ)
LOCK = datetime(2026, 9, 6, 18, 45, tzinfo=TZ)
assert NOW < LOCK, "T2 late hard lock passed"


def rows(path):
    with (ROOT / path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


def dump(path, value):
    (ROOT / path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


prefix = "artifacts/data/t2_late_20260906"
markets = rows(prefix + "_markets_all.csv")
matches = {r["match_number"].zfill(3): r for r in rows(prefix + "_matches.csv")}
signals = {r["match_number"].zfill(3): r for r in rows(prefix + "_signals.csv")}
model = {r["match_number"].zfill(3): r for r in rows(prefix + "_model.csv")}
v2 = {r["match_number"].zfill(3): r for r in rows(prefix + "_v2.csv")}
plans = rows(prefix + "_plans.csv")
plays = rows(prefix + "_allplays.csv")
baseline = {f["match_number"]: f for f in load("artifacts/data/sporttery_t1_baseline_2026-09-06_1505.json")["fixtures"]}
ledger = ROOT / "data/manual/betting_plan_ledger.csv"
ledger_hash = hashlib.sha256(ledger.read_bytes()).hexdigest()

comments = {
    "006": "SPF客胜仅小幅领先，竞彩主队+1却把让胜压到1.50；外盘平手，比竞彩+1更支持主队。主方向防主队不败，客胜不能当胆。",
    "007": "阿尔克马是SPF热门，但外盘仅客让0.5，弱于竞彩主队+1的整球表达；主队受让方向有保护，客胜只作进取分支。",
    "008": "曼联SPF热门，但外盘客让0.5，竞彩为埃弗顿+1；两端均支持曼联但外盘未到整球。首选埃弗顿+1胜，防曼联一球小胜。",
    "009": "SPF接近均衡，外盘平手，而竞彩给弗洛西诺+1；外盘对主队更友好。主队+1胜是相对稳方向，胜平负不设强胆。",
    "010": "竞彩帕尔马-1明显深于外盘平手，深盘不一致；模型主选让负且EV仍为负。防帕尔马赢球不穿，首选让负。",
    "011": "斯特拉斯SPF占优，但外盘平手，竞彩特鲁瓦+1；外盘对主队更友好。优先特鲁瓦+1胜，客胜降级。",
    "012": "竞彩汉堡+1且让胜1.44，但终版德甲外盘请求SSL失败，没有安全外盘快照；仅按官方赔率观察，禁止当稳胆。",
    "013": "官方是巴伦西亚主场+2；可用外盘为巴伦西亚+1.5，竞彩比外盘多半球保护。模型倾向让胜但仅10%辅助；按用户规则全体串关禁用。",
    "014": "竞彩圣克拉拉-1深于外盘-0.5，模型主选让负；防主队仅一球或不胜，首选让负，不做主胜穿盘胆。",
}

dispositions = {
    "防冷": "仅影子展示；006/007双选覆盖，但两个场次均属内外盘深度不一致，不进真实台账。",
    "博高": "高波动让平三串一，仅小额理论观察。",
    "固定赔率观察": "拒绝登记：006客胜、007客胜、011客胜均与外盘较浅/主队受让保护冲突，不满足低风险方向。",
}

report = [
    "# 2026-09-06 T2晚批006—014详细分析",
    "",
    f"冻结时间：{NOW.isoformat()}；官方竞彩四玩法采集：2026-09-06T18:19:03+08:00；终版外盘刷新：18:23:33（部分成功）；硬锁18:45。",
    "",
    "## 内外盘如何进入本轮模型",
    "",
    "先用球队别名和开赛时间做唯一映射，再把所有亚洲盘统一成主队视角的精确档位（含0、±0.5、±1.5），之后计算竞彩整数让球与外盘盘口差。外盘不是直接替代竞彩概率：训练域内仅以25%权重辅助，受控扩展域仅10%，训练域外或无安全快照直接阻断。模型本身不得单独触发投注。",
    "",
    "本批9场中8场有赛前安全外盘盘口（006/007/008/009/010/011/013/014），012缺失；v1为2场25%辅助、5场10%辅助、2场阻断。终版API有5场成功刷新，其余沿用同一批18:19前后安全快照；没有把失败值伪装成终值。",
    "",
    "## 当日比赛行程与逐场方案",
    "",
    "概率为去水市场概率或受控混合值，不等于确定胜率；首发和临场伤停尚未形成可核验完整清单。",
    "",
    "|编号/开赛/比赛|SPF 主/平/客|竞彩让球及RQSPF 主/平/客|外盘主队线|模型使用|主要方向|进球/比分/半全场|风险|",
    "|---|---|---|---:|---|---|---|---|",
]

details = []
for market in markets:
    number = market["match_number"].zfill(3)
    match = matches.get(number, {})
    signal = signals[number]
    pred = model[number]
    base = baseline[number]
    spf = [float(market["spf_odds_" + key]) for key in ("home", "draw", "away")]
    rq = [float(market["rqspf_odds_" + key]) for key in ("home", "draw", "away")]
    spf_delta = [round(value - old, 2) for value, old in zip(spf, base["spf"])]
    rq_delta = [round(value - old, 2) for value, old in zip(rq, base["rqspf"])]
    usage = pred["handicap_model_usage"]
    if pred.get("handicap_model_weight"):
        usage += f"({float(pred['handicap_model_weight']):.0%})/{pred['handicap_model_pick']}"
    outer = signal.get("external_latest_home_spread_point") or "缺失"
    suggestions = "/".join(filter(None, [match.get("total_goals_suggestion"), match.get("correct_score_suggestion"), match.get("half_full_suggestion")]))
    report.append(
        f"|{number} {market['kickoff_time'][11:]} {market['home_team']}vs{market['away_team']}|"
        f"{'/'.join(f'{x:.2f}' for x in spf)}|{market['home_handicap']} {'/'.join(f'{x:.2f}' for x in rq)}|"
        f"{outer}|{usage}|{comments[number]}|{suggestions or '仅赔率方向'}|{signal['market_signal_strength']}；首发伤停未完整核实|"
    )
    details.append({
        "match_number": number,
        "market": market,
        "spf_delta_from_t1": spf_delta,
        "rqspf_delta_from_t1": rq_delta,
        "external_signal": signal,
        "controlled_model": pred,
        "shadow_v2": v2.get(number),
        "analysis": comments[number],
        "lineups": "unverified",
        "injuries": "unverified",
    })

report += [
    "",
    "## 赔率变化说明",
    "",
    "详细JSON逐场保存15:05→18:19的SPF与RQSPF六项差值。方向判断以18:19官方赔率为准；外盘按最后一个不晚于分析时点的安全快照，不跨越开赛时间。",
    "",
    "## 多方案与审查",
    "",
    "以下全是理论/影子方案，金额只是复盘计量单位；真实投注台账新增0。方案之间共享场次，不能把各自预算相加理解为建议投入。",
]
for plan in plans:
    disposition = dispositions[plan["plan_type"]]
    plan["review_disposition"] = disposition
    report += [
        "",
        f"### {plan['plan_type']}：{disposition}",
        "",
        plan["selections"],
        f"假设本金{plan['total_stake']}元，{plan['bet_count']}注；组合赔率{plan['estimated_odds_min']}—{plan['estimated_odds_max']}；命中返奖{plan['estimated_payout_min']}—{plan['estimated_payout_max']}元，命中净收益{plan['estimated_net_min']}—{plan['estimated_net_max']}元。",
        plan["risk_notes"],
    ]

report += [
    "",
    "## 单场玩法扩展",
    "",
    f"已为9场生成{len(plays)}条总进球/比分/半全场观察卡（每场3条），详表保存在CSV。它们是高波动影子候选，不代表已核实单关资格，不进入真实台账。013只允许逐场分析与单场观察，未进入任何串关。",
    "",
    "## 固定赔率与台账结论",
    "",
    "生成器原始固定赔率影子为006客胜×007客胜×011客胜，理论赔率7.8045、虚拟2元、命中理论返奖15.61元。由于三腿都与外盘浅盘/主队受让保护存在冲突，本轮拒绝登记；固定赔率影子新增0，真实台账新增0。",
    "",
    "## 数据缺口和下个节点",
    "",
    "012终版德甲外盘请求SSL失败，模型按no_safe_external_snapshot阻断；006英冠不在训练域而阻断。首发、伤停没有完整可验证输入，不填‘无伤停’。下一任务为22:30的015—024，硬锁22:45；015继续禁串。",
]

artifact = {
    "sales_day": "2026-09-06",
    "batch": "006-014",
    "frozen_at": NOW.isoformat(),
    "official_captured_at": "2026-09-06T18:19:03.389415+08:00",
    "external_final_captured_at": "2026-09-06T10:23:33+00:00",
    "external_covered_rows": 8,
    "external_final_refresh_mapped_rows": 5,
    "fixtures": details,
    "plans": plans,
    "play_candidates_count": len(plays),
    "real_ledger_write": False,
    "ledger_sha256": ledger_hash,
    "fixed_shadow_recorded": False,
    "fixed_shadow_rejection": "all three legs conflict with shallower external lines or home handicap protection",
    "parlay_exclusions_enforced": ["013", "015"],
    "gate": load(prefix + "_gate.json"),
    "model_audit": load(prefix + "_model_audit.json"),
    "v2_audit": load(prefix + "_v2_audit.json"),
    "signal_audit": load(prefix + "_signals_audit.json"),
}
(ROOT / (prefix + "_detailed.md")).write_text("\n".join(report) + "\n", encoding="utf-8")
dump(prefix + "_detailed.json", artifact)

registry_path = "artifacts/data/sporttery_task_registry_2026-09-06.json"
registry = load(registry_path)
for task in registry["tasks"]:
    if task["key"] == "2026-09-06|006-014|T2晚批":
        task.update({
            "status": "completed",
            "completed_at": NOW.isoformat(),
            "artifact": prefix + "_detailed.json",
            "report": prefix + "_detailed.md",
        })
registry["updated_at"] = NOW.isoformat()
dump(registry_path, registry)

override_path = "artifacts/data/sporttery_daily_schedule_override_2026-09-06.json"
override = load(override_path)
for task in override.get("stages", override.get("tasks", [])):
    if task.get("purpose") == "T2晚批" or task.get("time_group") == "6-14":
        task.update({"status": "completed", "completed_at": NOW.isoformat(), "artifact": prefix + "_detailed.json", "report": prefix + "_detailed.md"})
override["updated_at"] = NOW.isoformat()
dump(override_path, override)

state_path = "artifacts/data/football_automation_controller_state.json"
state = load(state_path)
state.update({
    "last_completed_stage": "2026-09-06 T2晚批006-014",
    "last_completed_at": NOW.isoformat(),
    "last_stage_status": "completed_before_lock_real_ledger_unchanged",
    "last_stage_artifact": prefix + "_detailed.json",
    "next_dynamic_task_key": "2026-09-06|015-024|T2跨天批",
    "next_dynamic_task_at": "2026-09-06T22:30:00+08:00",
    "next_required_stage": "22:30 T2跨天批015-024",
    "next_required_at": "2026-09-06T22:30:00+08:00",
    "inner_outer_alignment_status": "2026-09-06_1823_late_8_of_9_safe_external_lines_5_final_refresh_012_missing",
})
dump(state_path, state)
assert hashlib.sha256(ledger.read_bytes()).hexdigest() == ledger_hash
print(json.dumps({"frozen_at": NOW.isoformat(), "report": prefix + "_detailed.md", "artifact": prefix + "_detailed.json", "ledger_unchanged": True}, ensure_ascii=False))
