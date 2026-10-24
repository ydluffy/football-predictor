import csv, hashlib, json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TZ = timezone(timedelta(hours=8))
NOW = datetime.now(TZ)
assert NOW < datetime(2026, 9, 6, 22, 45, tzinfo=TZ), "hard lock passed"


def read(path):
    with (ROOT / path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


def dump(path, value):
    (ROOT / path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


p = "artifacts/data/t2_crossday_20260906"
markets = read(p + "_markets_all.csv")
match_rows = {r["match_number"].zfill(3): r for r in read(p + "_matches.csv")}
signals = {r["match_number"].zfill(3): r for r in read(p + "_signals.csv")}
models = {r["match_number"].zfill(3): r for r in read(p + "_model.csv")}
plans = read(p + "_plans.csv")
plays = read(p + "_allplays.csv")
baseline = {r["match_number"]: r for r in load("artifacts/data/sporttery_t1_baseline_2026-09-06_1505.json")["fixtures"]}
ledger = ROOT / "data/manual/betting_plan_ledger.csv"
ledger_hash = hashlib.sha256(ledger.read_bytes()).hexdigest()

comments = {
    "015": "主胜低至1.21，热度极高；即使维持强势也缺乏赔率缓冲。按用户规则禁止进入任何串关。",
    "016": "阿森纳主胜占优，但竞彩-1深于外盘-0.5；模型25%辅助选让负，重点防一球小胜或不穿。",
    "017": "法兰克福主胜占优，但无安全外盘终值；赢球与穿-1分开，主胜仅观察。",
    "018": "博洛尼亚主胜轻度占优，-1让负为低赔端；防小胜、不穿和平局。",
    "019": "主胜仅弱优势且平局权重高；-1让负明显低赔，优先低比分与主队不穿。",
    "020": "主客胜差距很小，属于均衡盘；不设胆，防平及客队不败。",
    "021": "尤文主胜有优势但平局权重高；强强对话不支持深串，防平与一球差。",
    "022": "马赛主胜占优，但无外盘终值验证；可作主胜观察，-1仍防不穿。",
    "023": "西班牙人仅弱主胜优势且平局高；优先防平，-1让负方向更稳。",
    "024": "帕梅拉斯客胜占优但博塔弗戈+1保护明显；帕梅拉斯是第1、博塔弗戈第12，不称榜首战，防主队受让胜。",
}

report = [
    "# 2026-09-06 T2跨天批015—024（数据闸门阻断版）", "",
    f"冻结时间：{NOW.isoformat()}，硬锁22:45。22:30—22:40连续三次官方刷新尝试及网页直连均超时；最近完整官方快照为18:19。由于不是临锁新鲜快照，终版数据闸门为BLOCKED_DATA_GATE，本批不得创建或登记正式方案。", "",
    "## 逐场观察分析", "",
    "以下仅用于保留赛前分析和明日复盘基准，不是可执行终版票。外盘只有016形成安全唯一映射，其余9场不得填造外盘。", "",
    "|编号/比赛/开赛|SPF主/平/客|让球及RQSPF主/平/客|外盘/模型|方向、进球与风险|", "|---|---|---|---|---|",
]
details = []
for market in markets:
    n = market["match_number"].zfill(3)
    spf = [float(market["spf_odds_" + k]) for k in ("home", "draw", "away")]
    rq = [float(market["rqspf_odds_" + k]) for k in ("home", "draw", "away")]
    base = baseline[n]
    match = match_rows.get(n, {})
    signal = signals[n]
    model = models[n]
    suggestions = "/".join(filter(None, [match.get("total_goals_suggestion"), match.get("correct_score_suggestion"), match.get("half_full_suggestion")])) or "低赔强热，仅观察"
    outer = signal.get("external_latest_home_spread_point") or "缺失"
    model_text = model["handicap_model_usage"]
    if model.get("handicap_model_weight"):
        model_text += f" {float(model['handicap_model_weight']):.0%}/{model['handicap_model_pick']}"
    report.append(f"|{n} {market['home_team']}vs{market['away_team']} {market['kickoff_time'][5:]}|{'/'.join(f'{v:.2f}' for v in spf)}|{market['home_handicap']} {'/'.join(f'{v:.2f}' for v in rq)}|{outer}；{model_text}|{comments[n]} 参考：{suggestions}|" )
    details.append({"match_number": n, "market": market, "spf_delta_from_t1": [round(v-o,2) for v,o in zip(spf,base["spf"])], "rqspf_delta_from_t1": [round(v-o,2) for v,o in zip(rq,base["rqspf"])], "signal": signal, "model": model, "analysis": comments[n]})

report += ["", "## 方案审查", "", "生成器基于18:19旧快照曾产生以下理论结构，但因临锁官方刷新失败、数据闸门阻断，全部作废，不得视为正式候选："]
for plan in plans:
    report += ["", f"- {plan['plan_type']}（作废）：{plan['selections']}；理论赔率{plan['estimated_odds_min']}—{plan['estimated_odds_max']}。"]
report += ["", "015已从所有串关输入中排除。30条总进球/比分/半全场观察卡仅供复盘，不代表单关资格或实投建议。真实台账新增0，固定赔率影子新增0。", "", "## 失败证据与后续", "", "官方抓取页面在22:30后多次超时，四玩法无法形成同一时间的新鲜快照；因此没有拿18:19数据冒充22:30终值。下一有效节点为明日10:00预扫描、11:05确认、13:00逐场复盘。"]

artifact = {"sales_day":"2026-09-06","batch":"015-024","frozen_at":NOW.isoformat(),"status":"completed_blocked_data_gate","official_snapshot_used":"2026-09-06T18:19:03.389415+08:00","fresh_refresh_ok":False,"refresh_failures":["three local official refresh attempts timed out","official web fetch timed out"],"fixtures":details,"void_theoretical_plans":plans,"play_observation_count":len(plays),"parlay_exclusions_enforced":["015"],"real_ledger_write":False,"fixed_shadow_write":False,"ledger_sha256":ledger_hash}
(ROOT/(p+"_detailed.md")).write_text("\n".join(report)+"\n",encoding="utf-8")
dump(p+"_detailed.json",artifact)
registry_path="artifacts/data/sporttery_task_registry_2026-09-06.json"
registry=load(registry_path)
for task in registry["tasks"]:
    if task["key"]=="2026-09-06|015-024|T2跨天批":
        task.update({"status":"completed","completed_at":NOW.isoformat(),"completion_status":"blocked_data_gate_no_formal_plan","artifact":p+"_detailed.json","report":p+"_detailed.md"})
registry["updated_at"]=NOW.isoformat();dump(registry_path,registry)
override_path="artifacts/data/sporttery_daily_schedule_override_2026-09-06.json"
override=load(override_path)
for task in override["stages"]:
    if task["key"]=="2026-09-06|015-024|T2跨天批":
        task.update({"status":"completed","completed_at":NOW.isoformat(),"completion_status":"blocked_data_gate_no_formal_plan","artifact":p+"_detailed.json","report":p+"_detailed.md"})
override["updated_at"]=NOW.isoformat();dump(override_path,override)
assert hashlib.sha256(ledger.read_bytes()).hexdigest()==ledger_hash
print(json.dumps({"frozen_at":NOW.isoformat(),"status":"completed_blocked_data_gate","report":p+"_detailed.md","ledger_unchanged":True},ensure_ascii=False))
