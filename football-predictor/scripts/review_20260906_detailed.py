import csv, json, re, math, hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict

R=Path(__file__).resolve().parents[1]
def read(p):
    with (R/p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
raw=read('data/manual/sporttery_results_2026-09-06_sales_window.csv')
base=json.loads((R/'artifacts/data/sporttery_t1_baseline_2026-09-06_1505.json').read_text(encoding='utf-8'))
results={}
for f in base['fixtures']:
    hits=[r for r in raw if r['match_number'].endswith(f['match_number']) and r['home_team']==f['home_team'] and r['away_team']==f['away_team'] and r['status']=='已完成']
    assert len(hits)==1,(f['match_number'],len(hits),f['home_team'],f['away_team'])
    r=hits[0];assert re.fullmatch(r'\d+:\d+',r['full_time_score']);results[f['match_number']]=r
assert len(results)==24

groups=[
 ('T2早批001-005','artifacts/data/t2_early_20260906_plans.csv','artifacts/data/t2_early_20260906_plays.csv','artifacts/data/t2_early_20260906_markets.csv','正式前瞻候选/未入账'),
 ('T2晚批006-014','artifacts/data/t2_late_20260906_plans.csv','artifacts/data/t2_late_20260906_allplays.csv','artifacts/data/t2_late_20260906_markets_all.csv','正式前瞻候选/未入账'),
 ('T2跨天015-024','artifacts/data/t2_crossday_20260906_plans.csv','artifacts/data/t2_crossday_20260906_allplays.csv','artifacts/data/t2_crossday_20260906_markets_all.csv','数据闸门阻断/赛前已作废'),
]
plans=[];singles=[]
for batch,pp,cp,mp,classification in groups:
    markets={m['match_number'].zfill(3):m for m in read(mp)}
    for p in read(pp):
        legs=[];factors=[]
        for leg in p['selections'].split(' + '):
            n=leg[:3];rr=results[n];m=markets[n];typ='rqspf' if '让球胜平负:' in leg else 'spf';picks=leg.split(':')[-1].split('/')
            actual=rr['rqspf_result'] if typ=='rqspf' else {'胜':'主胜','平':'平','负':'客胜'}[rr['spf_result']]
            hit=actual in picks;key={'主胜':'home','平':'draw','客胜':'away','让胜':'home','让平':'draw','让负':'away'}[actual]
            factors.append(float(m[typ+'_odds_'+key]) if hit else 0);legs.append({'selection':leg,'score':rr['full_time_score'],'actual':actual,'hit':hit})
        amount=float(p.get('amount_per_bet') or 2);stake=float(p.get('total_stake') or p.get('stake') or 0)
        payout=round(amount*math.prod(factors),2)
        plans.append({'batch':batch,'type':p['plan_type'],'classification':classification,'legs':legs,'stake':stake,'payout':payout,'net':round(payout-stake,2),'roi':round((payout-stake)/stake,6) if stake else None,'hit':all(l['hit'] for l in legs)})
    for p in read(cp):
        n=f"{int(p['title'].split()[0]):03}";rr=results[n];h,a=map(int,rr['full_time_score'].split(':'));hh,ha=map(int,rr['half_time_score'].split(':'))
        outcome=lambda x,y:'H' if x>y else 'D' if x==y else 'A'
        actual={'total_goals':str(min(h+a,7)),'correct_score':rr['full_time_score'],'half_full_time':outcome(hh,ha)+'-'+outcome(h,a)}[p['play_type']]
        win=0
        for part in p['selections'].split(' / '):
            pick,odd=part.rsplit('@',1);hit=pick==actual or (p['play_type']=='total_goals' and h+a>=7 and pick in ['7+','7'])
            if hit:win+=2*int(p['multiplier'])*float(odd)
        stake=float(p['total_stake']);singles.append({'batch':batch,'classification':classification,'number':n,'type':p['plan_type'],'selections':p['selections'],'actual':actual,'stake':stake,'payout':round(win,2),'net':round(win-stake,2),'hit':win>0})

def summary(xs):
    s=sum(x['stake'] for x in xs);p=sum(x['payout'] for x in xs)
    return {'count':len(xs),'hits':sum(x['hit'] for x in xs),'stake':round(s,2),'payout':round(p,2),'net':round(p-s,2),'roi':round((p-s)/s,6) if s else None}

primary={
'001':('主胜','miss'),'002':('客胜','hit'),'003':('客胜','hit'),'004':('主胜','miss'),'005':('主胜','hit'),
'006':('主队不败/受让胜','hit'),'007':('主队+1让胜','miss'),'008':('埃弗顿+1让胜','hit'),'009':('弗洛西诺+1让胜','hit'),
'010':('帕尔马-1让负','hit'),'011':('特鲁瓦+1让胜','miss'),'012':('汉堡+1让胜/仅观察','miss'),'013':('巴伦西亚+2让胜/禁串','miss'),'014':('圣克拉拉-1让负','miss'),
'015':('莫尔德主胜/禁串观察','hit'),'016':('阿森纳-1让负','miss'),'017':('法兰克福主胜','miss'),'018':('博洛尼亚-1让负','hit'),
'019':('阿拉维斯-1让负','miss'),'020':('防平及客不败','hit'),'021':('防平','hit'),'022':('马赛主胜','miss'),'023':('防平','hit'),'024':('博塔弗戈+1让胜','hit')}
fixed=read('data/manual/fixed_odds_shadow_ledger.csv');fixed_today=[r for r in fixed if r['date']=='2026-09-06'];fixed_done=[r for r in fixed if r['result'] in ['命中','未中']]
real_today=[r for r in read('data/manual/betting_plan_ledger.csv') if r['date']=='2026-09-06']
shadow_pred=[r for r in read('data/manual/shadow_prediction_ledger_v2.csv') if r['sales_day']=='2026-09-06']
shadow_port=[r for r in read('data/manual/shadow_portfolio_ledger_v2.csv') if r['sales_day']=='2026-09-06']
equity=peak=dd=0
for p in fixed_done:
    equity+=float(p['net_profit']);peak=max(peak,equity);dd=max(dd,peak-equity)
valid_plans=[p for p in plans if '作废' not in p['classification']];void_plans=[p for p in plans if '作废' in p['classification']]
valid_singles=[p for p in singles if '作废' not in p['classification']];void_singles=[p for p in singles if '作废' in p['classification']]
report=['# 2026-09-06销售日24场详细复盘','',f'完成时间：{datetime.now().astimezone().isoformat()}。官方销售窗口扩展至9月7日，共导入36条赛果；按编号+主客队唯一映射本批24场，全部取得90分钟赛果。','',f'真实台账本日{len(real_today)}条；实际投入、返奖和收益均为0。早批和晚批候选没有真实入账，只做理论回测；跨天批在赛前已因数据闸门阻断作废，单列诊断，不计正式命中率或收益。','', '## 24场赛果与赛前主要方向','', '|编号|比赛|半场|90分钟|SPF|让球赛果|赛前主要方向|核验|','|---|---|---|---|---|---|---|---|']
for n,r in sorted(results.items()):
    d,status=primary[n];report.append(f"|{n}|{r['home_team']}—{r['away_team']}|{r['half_time_score']}|{r['full_time_score']}|{r['spf_result']}|{r['handicap']} {r['rqspf_result']}|{d}|{'命中' if status=='hit' else '未中'}|")
report+=['','## 早批和晚批全部组合逐腿核验','','下列金额均是未入账候选的理论回测。双选方案按实际命中的子注计算，方案间共享场次，不能当独立样本。']
for p in valid_plans:
    report+=['',f"### {p['batch']}／{p['type']}"]
    for l in p['legs']:report.append(f"- {l['selection']}：90分钟{l['score']}，实际{l['actual']}，{'命中' if l['hit'] else '未中，断票腿'}。")
    report.append(f"- 假设本金{p['stake']:.2f}元，理论返奖{p['payout']:.2f}元，净收益{p['net']:.2f}元，ROI {p['roi']:.2%}。")
report+=['','## 跨天批作废结构诊断','','这些结构在赛前22:42已经标记作废。以下只说明如果按18:19旧赔率表达会发生什么，不计任何正式统计。']
for p in void_plans:
    broken=[l['selection'] for l in p['legs'] if not l['hit']]
    report.append(f"- {p['type']}：{'理论命中' if p['hit'] else '理论未中'}；断腿：{'；'.join(broken) if broken else '无'}；假设返奖{p['payout']:.2f}元。")
report+=['','## 多玩法逐场核验','','每场总进球、比分、半全场各一张观察卡；没有单关资格冻结，以下仍属理论诊断。','|批次/场次|玩法|冻结选择|实际|假设本金|理论返奖|净收益|','|---|---|---|---|---|---|---|']
for p in singles:report.append(f"|{p['batch']}/{p['number']}|{p['type']}|{p['selections']}|{p['actual']}|{p['stake']:.2f}|{p['payout']:.2f}|{p['net']:.2f}|")
report+=['','## 真实入账、固定赔率影子与v2影子','',f'- 真实入账：{len(real_today)}条，本日实际投入0元、返奖0元、净收益0元。',f'- 9月6日固定赔率影子新增{len(fixed_today)}条；早批和晚批均在赛前拒绝登记，跨天批作废，因此本日不新增固定赔率样本。',f'- 固定赔率影子累计已结算{len(fixed_done)}条，命中{sum(r['result']=='命中' for r in fixed_done)}条，虚拟投入{sum(float(r['stake']) for r in fixed_done):.2f}元，返奖{sum(float(r['payout']) for r in fixed_done):.2f}元，ROI {(sum(float(r['payout']) for r in fixed_done)-sum(float(r['stake']) for r in fixed_done))/sum(float(r['stake']) for r in fixed_done):.2%}，最大回撤{dd:.2f}元。',f'- v2预测证据{len(shadow_pred)}条，均因日职/韩职不在训练域而blocked/not_evaluable；v2组合{len(shadow_port)}条，故没有9月6日可结算v2虚拟票。','- 邪修方案于9月7日才登记，不回填9月6日赛前样本；本次邪修统计为0。']
report+=['','## 汇总','','```json',json.dumps({'正式候选组合':summary(valid_plans),'正式候选多玩法':summary(valid_singles),'赛前作废组合_仅诊断':summary(void_plans),'赛前作废多玩法_仅诊断':summary(void_singles)},ensure_ascii=False,indent=2),'```','','## 错误归因与下一轮改进','', '- 006、008、009的主队受让保护验证有效；007的一球差落在让平，说明把“有保护”直接压成让胜会损失中间结果。','- 010让负命中，但014让负被4:0穿盘击败；体彩比外盘更深是风险提示，不是自动反向信号。','- 011、012、013连续大比分客胜，受让方向全部失败；缺阵容与伤停证据时，受让低赔不能升为稳胆。','- 016实际一球小胜落在让平，符合“主胜不等于穿盘”的风险判断，但单选让负仍未中；以后深浅盘冲突优先让平/让负双分支或放弃。','- 019以5:2穿盘，证明高平局权重的市场判断也可能被早段比赛状态打破；不能把低比分脚本当确定方向。','- 020、021、023防平命中，024主队受让胜命中；均衡盘更适合做覆盖或放弃，不适合强行设单胆。','- 跨天批因终版刷新失败而作废是正确风控；即使其中部分方向赛后命中，也不恢复其前瞻资格。','- 新增邪修方案从今天21:00开始留前瞻证据，异常优先触发复核和放弃，不能无脑反热门。']
out='artifacts/data/sporttery_full_review_2026-09-06_1300_detailed.md';(R/out).write_text('\n'.join(report)+'\n',encoding='utf-8')
audit={'sales_day':'2026-09-06','completed_at':datetime.now().astimezone().isoformat(),'official_matches':24,'real_plans':len(real_today),'primary_direction_hits':sum(v[1]=='hit' for v in primary.values()),'primary_direction_total':24,'plans':plans,'single_candidates':singles,'summaries':{'valid_plans':summary(valid_plans),'valid_singles':summary(valid_singles),'void_plans':summary(void_plans),'void_singles':summary(void_singles)},'fixed_today':len(fixed_today),'fixed_cumulative_count':len(fixed_done),'fixed_max_drawdown':dd,'shadow_predictions_today':len(shadow_pred),'shadow_portfolios_today':len(shadow_port),'contrarian_samples_today':0,'report':out,'production_ledger_sha256':hashlib.sha256((R/'data/manual/betting_plan_ledger.csv').read_bytes()).hexdigest()}
(R/'artifacts/data/review_20260906_1300_detailed.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'official_matches':24,'primary_hits':audit['primary_direction_hits'],'valid_plans':audit['summaries']['valid_plans'],'valid_singles':audit['summaries']['valid_singles'],'void_plans':audit['summaries']['void_plans'],'report':out},ensure_ascii=False))
