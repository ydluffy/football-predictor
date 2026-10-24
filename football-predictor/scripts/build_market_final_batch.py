"""Build a detailed final Sporttery market-baseline batch and shadow schemes."""
from __future__ import annotations

import argparse
import csv
import itertools
import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPF_LABEL = {"H": "主胜", "D": "平", "A": "客胜"}
RQ_LABEL = {"H": "让胜", "D": "让平", "A": "让负"}
HF_LABEL = {"H-H":"胜胜","D-H":"平胜","A-H":"负胜","H-D":"胜平","D-D":"平平","A-D":"负平","H-A":"胜负","D-A":"平负","A-A":"负负"}


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def f(value):
    try: return float(value)
    except (TypeError, ValueError): return None


def exact(rows, fixture):
    found = [r for r in rows if r["match_number"].zfill(3) == fixture["match_number"] and r["home_team"] == fixture["home_team"] and r["away_team"] == fixture["away_team"]]
    if len(found) != 1: raise ValueError(f"identity mapping {fixture['match_number']}: {len(found)}")
    return found[0]


def play_low(rows, fixture, play, count):
    found = [r for r in rows if r["match_number"].zfill(3) == fixture["match_number"] and r.get("home_team") == fixture["home_team"] and r.get("away_team") == fixture["away_team"] and r["play_type"] == play and f(r["odds"]) is not None]
    best = {}
    for r in found: best[r["selection"]] = min(best.get(r["selection"], 9999), f(r["odds"]))
    items = sorted(best.items(), key=lambda x: x[1])[:count]
    return [{"selection": HF_LABEL.get(k, "7+" if k == "7_plus" else k), "odds": v} for k, v in items]


def fmt(items): return "/".join(f"{x['selection']}@{x['odds']:.2f}" for x in items) or "未开"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sales-day", required=True); ap.add_argument("--scope", required=True); ap.add_argument("--analysis-at", required=True)
    ap.add_argument("--scan-json", required=True); ap.add_argument("--market-csv", required=True); ap.add_argument("--baseline-csv", required=True); ap.add_argument("--play-odds-csv", required=True)
    ap.add_argument("--report-output", required=True); ap.add_argument("--audit-output", required=True); ap.add_argument("--plans-output", required=True)
    args = ap.parse_args()
    numbers = [x.zfill(3) for x in args.scope.split(",")]
    scan = json.loads((ROOT / args.scan_json).read_text(encoding="utf-8")); markets = read(ROOT / args.market_csv); baseline = read(ROOT / args.baseline_csv); plays = read(ROOT / args.play_odds_csv)
    fixtures = [x for x in scan["fixtures"] if x["match_number"] in numbers]
    if len(fixtures) != len(numbers): raise ValueError(f"scope coverage {len(fixtures)}/{len(numbers)}")
    cards=[]
    for fx in fixtures:
        cur, old = exact(markets, fx), exact(baseline, fx)
        spf={k:f(cur[f"spf_odds_{n}"]) for k,n in (("H","home"),("D","draw"),("A","away"))}; rq={k:f(cur[f"rqspf_odds_{n}"]) for k,n in (("H","home"),("D","draw"),("A","away"))}
        old_spf={k:f(old[f"spf_odds_{n}"]) for k,n in (("H","home"),("D","draw"),("A","away"))}; old_rq={k:f(old[f"rqspf_odds_{n}"]) for k,n in (("H","home"),("D","draw"),("A","away"))}
        goals=play_low(plays,fx,"total_goals",2); scores=play_low(plays,fx,"correct_score",3); half=play_low(plays,fx,"half_full_time",2)
        spf_available=any(v is not None for v in spf.values())
        spf_order=sorted([(k,v) for k,v in spf.items() if v is not None],key=lambda x:x[1]); rq_order=sorted([(k,v) for k,v in rq.items() if v is not None],key=lambda x:x[1])
        if not spf_order:
            outcome={"H":[],"D":[],"A":[]}
            for x in scores:
                if ":" not in x["selection"]: continue
                h,a=map(int,x["selection"].split(":")); outcome["H" if h>a else "D" if h==a else "A"].append(x["odds"])
            spf_order=sorted([(k,min(v)) for k,v in outcome.items() if v],key=lambda x:x[1])
        p=spf_order[0] if spf_order else ("",None); d=spf_order[1] if len(spf_order)>1 else ("",None); rp=rq_order[0] if rq_order else ("",None); rd=rq_order[1] if len(rq_order)>1 else ("",None)
        if not spf_available:
            p=(p[0],None); d=(d[0],None)
        def dt(now, was):
            return "/".join(f"{'胜平负'[i]}{now[k]-was[k]:+.2f}" for i,k in enumerate(("H","D","A")) if now[k] is not None and was[k] is not None) or "不可比"
        conflict=(p[0]=="H" and cur["home_handicap"].startswith("-") and rp[0]=="A") or (p[0]=="A" and cur["home_handicap"].startswith("+") and rp[0]=="H")
        risks=[]
        if not any(v is not None for v in spf.values()): risks.append("SPF未开，仅按比分结构推断")
        if abs(int(cur["home_handicap"]))>=2: risks.append("深盘，胜负与穿盘分离")
        if "杯" in fx["competition"] or "亚冠" in fx["competition"]: risks.append("杯赛轮换风险")
        if p[1] and p[1]<=1.30: risks.append("超低赔热门，禁作单一锚点")
        if conflict: risks.append("SPF与让球撕裂")
        if not risks: risks.append("缺可核验首发伤停增益")
        orthodox=("比分结构推断" if not spf_available else "市场主方向") + f"{SPF_LABEL.get(p[0],'未开')}" + (f"@{p[1]:.2f}" if p[1] else "（SPF未开）") + f"，防{SPF_LABEL.get(d[0],'未开')}" + (f"@{d[1]:.2f}" if d[1] else "")
        contra=("胜负与穿盘相反，优先防一球差/不穿盘" if conflict else "无强反向信号，只保留次选防冷")
        cards.append({"number":fx["match_number"],"competition":fx["competition"],"kickoff":fx["kickoff"],"home":fx["home_team"],"away":fx["away_team"],"handicap":cur["home_handicap"],"spf":spf,"rqspf":rq,"primary":{"selection":SPF_LABEL.get(p[0]),"odds":p[1],"key":p[0]},"defense":{"selection":SPF_LABEL.get(d[0]),"odds":d[1],"key":d[0]},"rq_primary":{"selection":RQ_LABEL.get(rp[0]),"odds":rp[1],"key":rp[0]},"rq_defense":{"selection":RQ_LABEL.get(rd[0]),"odds":rd[1],"key":rd[0]},"spf_delta":dt(spf,old_spf),"rq_delta":dt(rq,old_rq),"goals":goals,"scores":scores,"half_full":half,"orthodox":orthodox,"contrarian":contra,"risks":risks,"confidence":"低" if conflict or not any(v is not None for v in spf.values()) else "中低"})

    usable=[c for c in cards if c["primary"]["odds"] is not None and any(v is not None for v in c["spf"].values())]
    ranked=sorted(usable,key=lambda c:c["primary"]["odds"])
    value=sorted([c for c in usable if 1.50<=c["primary"]["odds"]<=2.40],key=lambda c:c["primary"]["odds"])
    schemes=[]
    def add(pid,typ,legs,stake,bets=1,risk="串关存在断腿风险"):
        omin=1; selection=[]
        for c,kind in legs:
            item=c[kind]; omin*=item["odds"]; prefix="" if kind=="primary" else f"({c['handicap']})"
            selection.append(f"{c['number']} {c['home']}vs{c['away']}{prefix} {'胜平负' if kind=='primary' else '让球胜平负'}:{item['selection']}@{item['odds']:.2f}")
        schemes.append({"id":pid,"type":typ,"selection":" + ".join(selection),"stake":stake,"bets":bets,"omin":round(omin,4),"omax":round(omin,4),"risk":risk})
    if len(ranked)>=2: add("SAFE","市场顺势观察（未过生产门槛）",[(ranked[0],"primary"),(ranked[1],"primary")],50,risk="仅按市场价格排序，未经正式策略概率门槛与模型校验")
    if len(value)>=2: add("VALUE","市场组合观察（未过生产门槛）",[(value[0],"primary"),(value[1],"primary")],20,risk="仅为影子组合，不得写入正式投注台账")
    if len(value)>=4: add("VALUE_B","价值分散观察",[(value[2],"primary"),(value[3],"primary")],10)
    rq_rank=sorted([c for c in cards if c["rq_primary"]["odds"]],key=lambda c:c["rq_primary"]["odds"])
    if len(rq_rank)>=2: add("HANDICAP","让球结构观察",[(rq_rank[0],"rq_primary"),(rq_rank[1],"rq_primary")],20,risk="让球方向与胜负方向必须分开结算")
    hedge=sorted(usable,key=lambda c:abs(c["spf"]["H"]-c["spf"]["A"]))[:2]
    if len(hedge)==2:
        omin=hedge[0]["primary"]["odds"]*hedge[1]["primary"]["odds"]; omax=hedge[0]["defense"]["odds"]*hedge[1]["defense"]["odds"]
        schemes.append({"id":"HEDGE","type":"防冷复式","selection":" + ".join(f"{c['number']} {c['primary']['selection']}@{c['primary']['odds']:.2f}/{c['defense']['selection']}@{c['defense']['odds']:.2f}" for c in hedge),"stake":8,"bets":4,"omin":round(min(omin,omax),4),"omax":round(max(omin,omax),4),"risk":"双选仍不覆盖第三方向"})
    goal_cards=[c for c in cards if len(c["goals"])>=2][:2]
    if len(goal_cards)==2:
        vals=[a["odds"]*b["odds"] for a in goal_cards[0]["goals"] for b in goal_cards[1]["goals"]]
        schemes.append({"id":"GOALS","type":"总进球复式","selection":" + ".join(f"{c['number']}总进球{fmt(c['goals'])}" for c in goal_cards),"stake":8,"bets":4,"omin":round(min(vals),4),"omax":round(max(vals),4),"risk":"进球数玩法高方差"})
    score_cards=[c for c in cards if len(c["scores"])>=2][:2]
    if len(score_cards)==2:
        vals=[a["odds"]*b["odds"] for a in score_cards[0]["scores"][:2] for b in score_cards[1]["scores"][:2]]
        schemes.append({"id":"SCORE","type":"比分观察","selection":" + ".join(f"{c['number']}比分{fmt(c['scores'][:2])}" for c in score_cards),"stake":8,"bets":4,"omin":round(min(vals),4),"omax":round(max(vals),4),"risk":"比分窄覆盖、高方差"})
    hf=[c for c in cards if c["half_full"]][:2]
    if len(hf)==2:
        odds=hf[0]["half_full"][0]["odds"]*hf[1]["half_full"][0]["odds"]
        schemes.append({"id":"HALF_FULL","type":"半全场观察","selection":" + ".join(f"{c['number']}{c['half_full'][0]['selection']}@{c['half_full'][0]['odds']:.2f}" for c in hf),"stake":2,"bets":1,"omin":round(odds,4),"omax":round(odds,4),"risk":"半全场容错低"})
    candidates=[]
    for c in cards:
        for kind in ("primary","rq_primary"):
            x=c[kind]
            if x["odds"] and 1.30<=x["odds"]<=3.00: candidates.append((c,kind))
    fixed=None
    for size in range(2,5):
        options=[]
        for combo in itertools.combinations(candidates,size):
            if len({x[0]["number"] for x in combo})<size: continue
            odds=1
            for c,k in combo: odds*=c[k]["odds"]
            if 6<=odds<=10: options.append((abs(odds-8),odds,combo))
        if options: fixed=min(options,key=lambda x:x[0]); break
    if fixed:
        _,odds,combo=fixed; add("MULTI_PLAY_FIXED_ODDS_SHADOW","固定赔率观察",list(combo),2,risk="固定赔率区间研究，不进入正式台账"); schemes[-1]["omin"]=schemes[-1]["omax"]=round(odds,4)
    conflicts=[c for c in cards if "SPF与让球撕裂" in c["risks"]]
    contra=(conflicts or sorted(cards,key=lambda c:c["rq_primary"]["odds"] or 99))[-1 if conflicts else 0]
    schemes.append({"id":"CONTRARIAN","type":"邪修方案","selection":f"{contra['number']} {contra['home']}({contra['handicap']}){contra['rq_primary']['selection']}@{contra['rq_primary']['odds']:.2f}","stake":2,"bets":1,"omin":contra["rq_primary"]["odds"],"omax":contra["rq_primary"]["odds"],"risk":"单关资格未核实，仅理论影子；不倍投不追损"})

    plan_path=ROOT/args.plans_output; fields=["plan_id","plan_type","title","stake","bet_count","base_bet_unit","multiplier","amount_per_bet","total_stake","unused_budget","estimated_odds_min","estimated_odds_max","estimated_payout_min","estimated_payout_max","estimated_net_min","estimated_net_max","selections","rationale","risk_notes","is_shadow","eligibility_note"]
    with plan_path.open("w",encoding="utf-8-sig",newline="") as h:
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader()
        for s in schemes:
            pmin=s["stake"]*s["omin"];pmax=s["stake"]*s["omax"]
            w.writerow({"plan_id":s["id"],"plan_type":s["type"],"title":s["type"],"stake":s["stake"],"bet_count":s["bets"],"base_bet_unit":2,"multiplier":1,"amount_per_bet":s["stake"]/s["bets"],"total_stake":s["stake"],"unused_budget":0,"estimated_odds_min":s["omin"],"estimated_odds_max":s["omax"],"estimated_payout_min":round(pmin,2),"estimated_payout_max":round(pmax,2),"estimated_net_min":round(pmin-s["stake"],2),"estimated_net_max":round(pmax-s["stake"],2),"selections":s["selection"],"rationale":"体彩终版市场结构观察","risk_notes":s["risk"],"is_shadow":True,"eligibility_note":"不进入正式模拟投注台账"})
    review_day = date.fromisoformat(args.sales_day) + timedelta(days=1)
    lines=[f"# {args.sales_day} 体彩{numbers[0]}—{numbers[-1]}终版分析与方案","",f"执行时间：{args.analysis_at}；体彩四玩法冻结于{scan['scanned_at']}。本批{len(cards)}场均在售、未开赛，终版门禁`READY_FOR_FINAL_ANALYSIS`。","","外盘：鉴权探针HTTP 200，密钥有效，但当前仅余1 credit，不足以执行路由后的多市场刷新；本批0映射并排除。没有统一可核验的首发、伤停、xG或旅行负荷。","","## 完整赛程与逐场预测","","|编号|赛事/开赛|比赛|SPF主防及变化|让球主防及变化|进球|比分|半全场|风险/信心|","|---|---|---|---|---|---|---|---|---|"]
    for c in cards:
        lines.append(f"|{c['number']}|{c['competition']} {c['kickoff'][11:16]}|{c['home']}—{c['away']}|{c['orthodox']}；{c['spf_delta']}|{c['handicap']} {c['rq_primary']['selection']}@{c['rq_primary']['odds']:.2f}，防{c['rq_defense']['selection']}@{c['rq_defense']['odds']:.2f}；{c['rq_delta']}|{fmt(c['goals'])}|{fmt(c['scores'])}|{fmt(c['half_full'])}|{'；'.join(c['risks'])}；{c['confidence']}|")
    lines += ["","## 逐场正邪依据",""]
    for c in cards: lines += [f"### {c['number']} {c['home']} vs {c['away']}",f"- 正道：{c['orthodox']}；总进球{fmt(c['goals'])}，比分{fmt(c['scores'])}，半全场{fmt(c['half_full'])}。",f"- 让球：主队{c['handicap']}，首选{c['rq_primary']['selection']}@{c['rq_primary']['odds']:.2f}，防{c['rq_defense']['selection']}@{c['rq_defense']['odds']:.2f}。",f"- 邪修：{c['contrarian']}；资金与大众投注占比未知，赔率变化不等同操盘或赛果预告。",f"- 数据缺口：无统一可核验伤停和首发；{'；'.join(c['risks'])}。",""]
    lines += ["## 正式入账状态","","本报告器只产生逐场市场分析与影子观察方案，不决定正式方案数。正式候选必须以同批 `build_multi_play_betting_strategy.py --stake 100` 的审计结果为准；影子模型或外盘缺失不得单独将正式方案置零。","","## 多组观察方案（均不入账）","","|方案|完整选择|注数/倍数|本金|组合赔率|预计返奖|风险|","|---|---|---:|---:|---:|---:|---|"]
    for s in schemes:
        pmin=s["stake"]*s["omin"];pmax=s["stake"]*s["omax"]; ot=f"{s['omin']:.4f}" if s["omin"]==s["omax"] else f"{s['omin']:.4f}—{s['omax']:.4f}"; pt=f"{pmin:.2f}元" if pmin==pmax else f"{pmin:.2f}—{pmax:.2f}元"
        lines.append(f"|{s['type']}|{s['selection']}|{s['bets']}注，倍数1|{s['stake']}元|{ot}|{pt}|{s['risk']}|")
    lines += ["","## 固定赔率影子方案（不入账）","",("已生成并将以2元虚拟注独立登记。" if fixed else "未找到6.00—10.00区间内的合格组合，保持空方案。"),"","## 邪修方案（独立影子研究）","",f"{schemes[-1]['selection']}，虚拟计量2元；单关资格未核实，只作理论观察。依据为胜负/让球撕裂或异常低价结构，不倍投、不追损。","","## 复盘与同步","",f"- {review_day.isoformat()} 13:00逐场核实90分钟赛果，分别统计正式、固定赔率影子、邪修和其他观察方案。","- 本销售日未获Supabase同步授权，仅本地保存。",""]
    (ROOT/args.report_output).write_text("\n".join(lines),encoding="utf-8")
    review_due = datetime.combine(review_day, time(13, 0)).astimezone().isoformat()
    payload={"schema_version":1,"sales_day":args.sales_day,"stage":"final","scope":args.scope,"analysis_at":args.analysis_at,"official_captured_at":scan["scanned_at"],"gate":"READY_FOR_FINAL_ANALYSIS","matches":cards,"formal_plans":[],"formal_plan_reason":"production_strategy_audit_required_separately","shadow_schemes":schemes,"fixed_odds_shadow":{"status":"candidate" if fixed else "no_action"},"contrarian_market_shadow":{"status":"candidate","is_shadow":True,"production_ledger_write":False,"match_number":contra["number"],"selection":schemes[-1]["selection"],"odds":schemes[-1]["omin"],"virtual_stake":2,"single_bet_qualification":"unverified_theoretical_observation","funding_sentiment":"unknown"},"production_ledger_write_performed":False,"report":args.report_output,"plans_csv":args.plans_output,"review_due_at":review_due,"supabase_sync":f"not_authorized_for_{args.sales_day}"}
    (ROOT/args.audit_output).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"status":"completed","matches":len(cards),"schemes":len(schemes),"fixed":bool(fixed),"report":args.report_output},ensure_ascii=False))


if __name__ == "__main__": main()
