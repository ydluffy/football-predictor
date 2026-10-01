import csv,json,re,math,hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict
R=Path(__file__).resolve().parents[1]
def read(p):
    with (R/p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
raw=read('artifacts/data/results_20260905.csv')
scan=json.loads((R/'artifacts/data/sporttery_sales_window_scan_2026-09-05_1731_confirm.json').read_text(encoding='utf-8'))
results={}
for f in scan['fixtures']:
    hits=[r for r in raw if r['match_number'].endswith(f['match_number']) and r['home_team']==f['home_team'] and r['away_team']==f['away_team'] and r['status']=='已完成']
    assert len(hits)==1,(f['match_number'],len(hits))
    r=hits[0]; assert re.fullmatch(r'\d+:\d+',r['full_time_score'])
    results[f['match_number']]=r
assert len(results)==29
groups=[('T2第一批001-003','artifacts/data/sporttery_plans_2026-09-05_1731_001-003.csv','artifacts/data/sporttery_all_play_candidates_2026-09-05_1731_001-003.csv','data/manual/sporttery_handicap_markets_2026-09-05_1731_confirm.csv'),('T2第一批004-016','artifacts/data/sporttery_plans_2026-09-05_1731_004-016.csv','artifacts/data/sporttery_all_play_candidates_2026-09-05_1731_004-016.csv','data/manual/sporttery_handicap_markets_2026-09-05_1731_confirm.csv'),('T2第二批017-029','artifacts/data/t2_2201_plans.csv','artifacts/data/t2_2201_candidates.csv','artifacts/data/t2_2201_markets.csv')]
plans=[]; singles=[]
for batch,pp,cp,mp in groups:
    markets={}
    for m in read(mp):
        n=m['match_number']; rr=results.get(n)
        if rr and (m['home_team'],m['away_team'])==(rr['home_team'],rr['away_team']): markets[n]=m
    for p in read(pp):
        legs=[]; factors=[]
        for leg in p['selections'].split(' + '):
            n=leg[:3]; rr=results[n]; m=markets[n]; typ='rqspf' if '让球胜平负:' in leg else 'spf'
            picks=leg.split(':')[-1].split('/')
            actual=rr['rqspf_result'] if typ=='rqspf' else {'胜':'主胜','平':'平','负':'客胜'}[rr['spf_result']]
            hit=actual in picks
            key={'主胜':'home','平':'draw','客胜':'away','让胜':'home','让平':'draw','让负':'away'}[actual]
            factors.append(float(m[typ+'_odds_'+key]) if hit else 0)
            legs.append({'selection':leg,'score':rr['full_time_score'],'actual':actual,'hit':hit})
        payout=round(float(p['amount_per_bet'])*math.prod(factors),2); stake=float(p['stake'])
        plans.append({'batch':batch,'type':p['plan_type'],'legs':legs,'stake':stake,'payout':payout,'net':round(payout-stake,2),'roi':round((payout-stake)/stake,6),'hit':all(l['hit'] for l in legs),'classification':'未入账候选理论回测'})
    for p in read(cp):
        n=f"{int(p['title'].split()[0]):03}"; rr=results[n]; h,a=map(int,rr['full_time_score'].split(':')); hh,ha=map(int,rr['half_time_score'].split(':'))
        outcome=lambda x,y:'H' if x>y else 'D' if x==y else 'A'
        actual={'total_goals':str(min(h+a,7)),'correct_score':rr['full_time_score'],'half_full_time':outcome(hh,ha)+'-'+outcome(h,a)}[p['play_type']]
        choices=[]; win=0
        for part in p['selections'].split(' / '):
            pick,odd=part.rsplit('@',1); hit=pick==actual or (p['play_type']=='total_goals' and h+a>=7 and pick in ['7+','7'])
            choices.append({'pick':pick,'odds':float(odd),'hit':hit})
            if hit:win+=2*int(p['multiplier'])*float(odd)
        stake=float(p['total_stake']); singles.append({'batch':batch,'number':n,'type':p['plan_type'],'selections':p['selections'],'actual':actual,'stake':stake,'payout':round(win,2),'net':round(win-stake,2),'hit':win>0})
def summary(xs):
    s=sum(x['stake'] for x in xs); p=sum(x['payout'] for x in xs)
    return {'count':len(xs),'hits':sum(x['hit'] for x in xs),'stake':round(s,2),'payout':round(p,2),'net':round(p-s,2),'roi':round((p-s)/s,6) if s else None}
fixed=read('data/manual/fixed_odds_shadow_ledger.csv'); today=[r for r in fixed if r['date']=='2026-09-05']; cumulative=[r for r in fixed if r['result'] in ['命中','未中']]
real=[r for r in read('data/manual/betting_plan_ledger.csv') if r['date']=='2026-09-05']; assert not real
sg={k:summary([p for p in singles if p['type']==k]) for k in ['总进球','比分','半全场']}
pg={k:summary([p for p in plans if p['batch']==k]) for k,_,_,_ in groups}
report=['# 2026-09-05销售日详细复盘','',f'实际完成时间：{datetime.now().astimezone().isoformat()}。原13:00节点，本次14:01后补执行。','', '官方跨日43条记录中，按编号+主客队唯一映射昨日29场，均取得90分钟赛果。真实台账昨日0条，实际投入和返奖无记录；下列候选回测均为理论值，不能当作实际中奖或收益。','', '|编号|比赛|半场|90分钟|SPF|让球结果|','|---|---|---|---|---|---|']
for n,r in sorted(results.items()):report.append(f"|{n}|{r['home_team']}—{r['away_team']}|{r['half_time_score']}|{r['full_time_score']}|{r['spf_result']}|{r['handicap']} {r['rqspf_result']}|")
report+=['','## 两批全部冻结组合逐腿回测','', '双选按每个实际命中子注计算返奖。未登记候选不并入固定影子累计；共享比赛不视为独立样本。']
for p in plans:
    report += ['',f"### {p['batch']} {p['type']}"]
    for l in p['legs']:report.append(f"- {l['selection']}：90分钟{l['score']}，实际{l['actual']}，{'命中' if l['hit'] else '未中／断票腿'}。")
    report.append(f"- 假设金额{p['stake']:.2f}，理论返奖{p['payout']:.2f}，净收益{p['net']:.2f}，ROI {p['roi']:.2%}。")
report+=['','## 固定赔率已登记影子','','16:32原全场观察单独列示，不计为T2批次。']
for p in today:report += [f"- {p['time_window']}：{p['selections']}；{p['review_note']}；虚拟投入{p['stake']}、返奖{p['payout']}、净收益{p['net_profit']}。"]
report += [f"- 累计{len(cumulative)}条已结算，命中{sum(r['result']=='命中' for r in cumulative)}条，累计投入{sum(float(r['stake']) for r in cumulative):.2f}、返奖{sum(float(r['payout']) for r in cumulative):.2f}元。"]
equity=peak=dd=0
for p in cumulative:
    equity+=float(p['net_profit']);peak=max(peak,equity);dd=max(dd,peak-equity)
report += [f'- 固定赔率影子累计最大回撤：{dd:.2f}元。','', '## 按批次、玩法汇总（理论）','',json.dumps({'组合按批次':pg,'多玩法':sg},ensure_ascii=False,indent=2),'','## 多玩法逐项核验','','单关许可未逐场冻结核验，以下仅作理论收益诊断，不宣称实际可出票；一行命中不等于所有选项命中。','|批次/场次|玩法|冻结选择|实际结果|假设金额|理论返奖|净收益|','|---|---|---|---|---|---|---|']
for p in singles:report.append(f"|{p['batch']}/{p['number']}|{p['type']}|{p['selections']}|{p['actual']}|{p['stake']}|{p['payout']}|{p['net']}|")
report+=['','## 错误归因和改进','', '- 首批稳健与价值共享014，次批共享028，不能将同核心的两张票当作风险分散；次批价值已赛前降级。','- 低赔及降赔只能反映市场定价，不足以证明正期望；模型、阵容和伤停覆盖不足时降低结论置信度。','- 固定赔率凑到目标区间不代表低风险，027主客同赔的候选已赛前拒绝登记，后续保持这一约束。','- 16:32观察、T2正式候选、已登记虚拟票必须分开统计，不能筛选中奖时段或把未下注候选当作实际收益。','- 多玩法报告本轮保留全部命中与未中项；先核验单关许可，再评价可出票组合。']
out='artifacts/reviews/sporttery_full_review_2026-09-05_detailed.md';(R/out).write_text('\n'.join(report),encoding='utf-8')
audit={'sales_day':'2026-09-05','completed_at':datetime.now().astimezone().isoformat(),'official_matches':29,'real_plans':0,'plans':plans,'single_candidates':singles,'batch_summary':pg,'play_summary':sg,'fixed_today':today,'fixed_cumulative_count':len(cumulative),'fixed_max_drawdown':dd,'report':out,'production_ledger_sha256':hashlib.sha256((R/'data/manual/betting_plan_ledger.csv').read_bytes()).hexdigest()}
(R/'artifacts/data/review_20260905_detailed.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'results':{n:r['full_time_score'] for n,r in sorted(results.items())},'plans':[{k:p[k] for k in ['batch','type','hit','payout','net']} for p in plans],'batch':pg,'plays':sg,'report':out},ensure_ascii=False))
