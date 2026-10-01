import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts/betting/sporttery_final_analysis_2026-09-15_1847_004-005.md"
AUDIT = ROOT / "artifacts/data/sporttery_final_analysis_2026-09-15_1847_004-005.json"
PLANS = ROOT / "artifacts/data/sporttery_plans_2026-09-15_1847_004-005.csv"

matches = [
    {"number":"004","competition":"亚冠精英","kickoff":"20:15","home":"柔佛","away":"布里兰","handicap":"-1","spf":{"H":1.35,"D":4.45,"A":6.10},"rq":{"H":2.22,"D":3.25,"A":2.70},"movement":"SPF胜-0.15/平+0.45/负+1.40；让胜-0.35/让平-0.13/让负+0.45","primary":"主胜","defense":"平","rq_pick":"让胜","goals":"3@3.60/2@4.00","scores":"2:1@7.00/2:0@7.25/1:0@8.00","half_full":"胜胜@2.12/平胜@4.05","orthodox":"柔佛主胜，且-1让胜同步增强，胜与穿盘方向一致。","contrarian":"主胜快速压低到1.35，热门拥挤；若临场继续降而让胜不再下降，则防只赢一球。","confidence":"中等"},
    {"number":"005","competition":"亚冠精英","kickoff":"20:15","home":"北京国安","away":"浦项制铁","handicap":"-1","spf":{"H":1.54,"D":3.80,"A":4.60},"rq":{"H":3.02,"D":3.08,"A":2.11},"movement":"SPF胜-0.13/平+0.24/负+0.60；让胜-0.12/让平-0.37/让负+0.19","primary":"主胜","defense":"平","rq_pick":"让负，次选让平","goals":"3@3.65/2@3.75","scores":"2:1@6.75/1:1@7.25/1:0@8.00","half_full":"胜胜@2.50/平胜@4.25","orthodox":"国安主胜由1.67降至1.54，但-1让负仍为最低2.11，更偏主队小胜而非大胜。","contrarian":"让平从3.45压到3.08，精准一球差信号明显；邪修单场观察国安-1让平。","confidence":"中等偏低"},
]

schemes = [
    {"id":"SAFE","type":"稳健观察","selection":"004柔佛主胜@1.35 + 005北京国安主胜@1.54","bets":1,"stake":50,"omin":2.079,"omax":2.079,"risk":"同属亚冠且均为主队热门，轮换或早段意外会造成双断。"},
    {"id":"VALUE","type":"价值观察","selection":"004柔佛(-1)让胜@2.22 + 005北京国安主胜@1.54","bets":1,"stake":20,"omin":3.4188,"omax":3.4188,"risk":"004需要至少赢两球，穿盘风险高于胜负。"},
    {"id":"HANDICAP","type":"让球结构观察","selection":"004柔佛(-1)让胜@2.22 + 005北京国安(-1)让负@2.11","bets":1,"stake":20,"omin":4.6842,"omax":4.6842,"risk":"两场采用相反穿盘结构，依赖盘口解释准确。"},
    {"id":"HEDGE","type":"防冷复式","selection":"004让胜@2.22/让平@3.25 + 005让负@2.11/让平@3.08","bets":4,"stake":8,"omin":4.6842,"omax":10.01,"risk":"仅覆盖让球双选，不覆盖004让负或005让胜。"},
    {"id":"GOALS","type":"总进球复式","selection":"004总进球3@3.60/2@4.00 + 005总进球3@3.65/2@3.75","bets":4,"stake":8,"omin":13.14,"omax":15.00,"risk":"进球数窄覆盖，单场4球即断票。"},
    {"id":"SCORE","type":"比分观察","selection":"004比分2:1@7.00/2:0@7.25 + 005比分2:1@6.75/1:1@7.25","bets":4,"stake":8,"omin":47.25,"omax":52.56,"risk":"高方差窄覆盖，只作赛后结构检验。"},
    {"id":"HALF_FULL","type":"半全场观察","selection":"004胜胜@2.12 + 005胜胜@2.50","bets":1,"stake":2,"omin":5.30,"omax":5.30,"risk":"两队均须半场领先并保持到终场。"},
    {"id":"CONTRARIAN","type":"邪修方案","selection":"005北京国安(-1)让平@3.08","bets":1,"stake":2,"omin":3.08,"omax":3.08,"risk":"单关资格未核实，只作理论影子；赔率变化不等于赛果预告。"},
]

fields=["plan_id","plan_type","title","stake","bet_count","base_bet_unit","multiplier","amount_per_bet","total_stake","unused_budget","estimated_odds_min","estimated_odds_max","estimated_payout_min","estimated_payout_max","estimated_net_min","estimated_net_max","selections","rationale","risk_notes","is_shadow","eligibility_note"]
with PLANS.open("w",encoding="utf-8-sig",newline="") as h:
    w=csv.DictWriter(h,fieldnames=fields);w.writeheader()
    for s in schemes:
        pmin=s["stake"]*s["omin"];pmax=s["stake"]*s["omax"]
        w.writerow({"plan_id":f"SHADOW_20260915_1847_{s['id']}","plan_type":s["type"],"title":s["type"],"stake":s["stake"],"bet_count":s["bets"],"base_bet_unit":2,"multiplier":1,"amount_per_bet":s["stake"]/s["bets"],"total_stake":s["stake"],"unused_budget":0,"estimated_odds_min":s["omin"],"estimated_odds_max":s["omax"],"estimated_payout_min":round(pmin,2),"estimated_payout_max":round(pmax,2),"estimated_net_min":round(pmin-s["stake"],2),"estimated_net_max":round(pmax-s["stake"],2),"selections":s["selection"],"rationale":"18:46体彩官方赔率结构观察。","risk_notes":s["risk"],"is_shadow":True,"eligibility_note":"影子研究，不进入正式模拟投注台账。"})

lines=["# 2026-09-15 体彩004—005终版分析与方案","","执行时间：北京时间2026-09-15 18:47；18:46重新抓取体彩四玩法。两场均在售、未开赛，门禁`READY_FOR_FINAL_ANALYSIS`，20:00硬锁。","","外盘状态：The Odds此前HTTP 401且仅余1 credit，本批外盘0/2并排除。两场影子v2均因亚冠不在训练域而blocked；无统一可核验伤停、首发、xG或旅行负荷，不能宣称阵容完整。","","## 完整赛程与逐场预测","","|编号|赛事/时间|比赛|SPF终版及14:30变化|让球终版|总进球|比分|半全场|信心|","|---|---|---|---|---|---|---|---|---|"]
for m in matches:
    lines.append(f"|{m['number']}|{m['competition']} {m['kickoff']}|{m['home']}—{m['away']}|{m['primary']}；防{m['defense']}；{m['movement']}|{m['handicap']}：{m['rq_pick']}；H/D/A={m['rq']['H']:.2f}/{m['rq']['D']:.2f}/{m['rq']['A']:.2f}|{m['goals']}|{m['scores']}|{m['half_full']}|{m['confidence']}|")
lines += ["","## 逐场正道与邪修依据",""]
for m in matches:
    lines += [f"### {m['number']} {m['home']} vs {m['away']}",f"- 正道：{m['orthodox']}",f"- 赔率/让球：{m['movement']}；主队{m['handicap']}，首选{m['rq_pick']}。",f"- 邪修：{m['contrarian']} 资金和大众投注占比未知，不把低赔等同真实热度。",f"- 多玩法：总进球{m['goals']}；比分{m['scores']}；半全场{m['half_full']}。",""]
lines += ["## 真实入账方案","","本批0组、0元。终版数据门禁通过，但两场均无独立模型概率且被训练域门禁拦截，不能用纯赔率市场方向写正式模拟台账。","","## 多组观察方案（均不入账）","","|方案|完整选择|注数/倍数|本金|组合赔率|预计返奖|风险|","|---|---|---:|---:|---:|---:|---|"]
for s in schemes:
    pmin=s["stake"]*s["omin"];pmax=s["stake"]*s["omax"]
    o=f"{s['omin']:.4f}" if s["omin"]==s["omax"] else f"{s['omin']:.4f}—{s['omax']:.4f}"
    p=f"{pmin:.2f}元" if pmin==pmax else f"{pmin:.2f}—{pmax:.2f}元"
    lines.append(f"|{s['type']}|{s['selection']}|{s['bets']}注，倍数1|{s['stake']}元|{o}|{p}|{s['risk']}|")
lines += ["","## 固定赔率影子方案（不入账）","","本批只有两场；在每场最多选一腿的前提下，没有低风险组合落入[6.00,10.00]，因此固定赔率影子为空，不向固定台账凑数。","","## 邪修方案（独立影子研究）","","005北京国安(-1)让平@3.08，虚拟计量2元，单关资格未核实，按理论观察留档。核心证据是SPF主胜1.67→1.54增强，同时让平3.45→3.08显著压低，倾向国安恰好赢一球；不据此倍投。","","## 后续与复盘","","- 21:00处理006—014，必须重新抓取终版赔率。","- 2026-09-16 13:00逐场复盘，分别统计正式、固定赔率影子、邪修及其他观察方案。","- 本销售日未获Supabase同步授权，仅本地保存。",""]
REPORT.write_text("\n".join(lines),encoding="utf-8")
payload={"schema_version":1,"sales_day":"2026-09-15","stage":"final","scope":"004-005","analysis_at":"2026-09-15T18:47:00+08:00","official_captured_at":"2026-09-15T18:46:00.878382+08:00","gate":"READY_FOR_FINAL_ANALYSIS","matches":matches,"formal_plans":[],"formal_plan_reason":"no independent model probability; both matches outside training domain","shadow_schemes":schemes,"fixed_odds_shadow":{"status":"no_action","reason":"no low-risk one-leg-per-match combination in [6.00,10.00]"},"contrarian_market_shadow":{"status":"candidate","is_shadow":True,"production_ledger_write":False,"match_number":"005","selection":"北京国安(-1)让平","odds":3.08,"virtual_stake":2.0,"single_bet_qualification":"unverified_theoretical_observation","funding_sentiment":"unknown","evidence":"SPF主胜1.67→1.54且让平3.45→3.08","data_gap":"无成交量、投注占比、统一伤停与首发"},"production_ledger_write_performed":False,"report":str(REPORT.relative_to(ROOT)).replace('\\','/'),"plans_csv":str(PLANS.relative_to(ROOT)).replace('\\','/'),"review_due_at":"2026-09-16T13:00:00+08:00","supabase_sync":"not_authorized_for_2026-09-15"}
AUDIT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"status":"completed","matches":2,"formal_plans":0,"shadow_schemes":len(schemes),"report":payload["report"]},ensure_ascii=False))
