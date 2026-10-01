import csv, json, hashlib
from pathlib import Path
from datetime import datetime,timezone,timedelta
ROOT=Path(__file__).resolve().parents[1]
TZ=timezone(timedelta(hours=8)); now=datetime.now(TZ)
assert now<datetime(2026,9,6,16,45,tzinfo=TZ),'locked'
def read(p):
    with (ROOT/p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def js(p):return json.loads((ROOT/p).read_text(encoding='utf-8-sig'))
prefix='artifacts/data/t2_early_20260906'
markets=read(prefix+'_markets.csv'); matches=read(prefix+'_matches.csv'); plans=read(prefix+'_plans.csv'); plays=read(prefix+'_plays.csv')
baseline={f['match_number']:f for f in js('artifacts/data/sporttery_t1_baseline_2026-09-06_1505.json')['fixtures']}
assert len(markets)==len(matches)==5 and len(plays)==15
ledger=ROOT/'data/manual/betting_plan_ledger.csv';ledger_hash=hashlib.sha256(ledger.read_bytes()).hexdigest()
outer=js('artifacts/data/the_odds_api_sporttery_latest.json')
dispositions={'稳健':'候选展示；未经授权未入账；非独立模型优势','价值':'降为观察：与稳健无保护共享005，不作为第二个正式候选','防冷':'仅观察：002主胜/客胜漏平，不是全面防冷','博高':'高风险观察，不建议实投','强胆复式观察':'仅结构观察，重复004暴露不可叠加','固定赔率观察':'拒绝登记：002和003均为仅观察，不满足低风险方向要求'}
report=['# 2026-09-06 T2早批001—005详细分析','',f'冻结时间：{now.isoformat()}；官方赔率采集16:32:05，基线15:05:01。16:34闸门通过，截止16:45。本报告不写真实台账。','',
'## 逐场分析与赔率变化','', '所有概率均为去水市场隐含值，非独立预测；日职及韩职不在当前让球模型训练域，v1/v2五场均blocked。置信等级仅为市场相对排序，不宣称模型高置信。', '',
'|编号/比赛/开赛|SPF主/平/客|主让球及RQSPF主/平/客|主要方向与T1变化|总进球参考|比分参考|半全场参考|风险|','|---|---|---|---|---|---|---|---|']
comments={'001':'主胜相对占优；1.62→1.59。赢球不等于穿-1，保留平局风险。','002':'客胜仅轻微占优；1.92→1.99回升。均衡盘，仅观察，不当串关核心。','003':'客胜轻微占优；2.07→2.12回升。主队+1不败方向更低赔，仅观察。','004':'主胜相对最强；1.46→1.42。-1让负2.40与让胜2.50接近，不宜强推穿盘。','005':'主胜相对占优；1.48持平。主胜和让负可同时成立，注意小胜/平局。'}
details=[]
for m,r in zip(markets,matches):
    n=m['match_number'];assert n==r['match_number'].zfill(3)
    sp=[float(m['spf_odds_'+k]) for k in ['home','draw','away']];rq=[float(m['rqspf_odds_'+k]) for k in ['home','draw','away']]
    d={'market':m,'analysis':r,'spf_delta_from_t1':[round(a-b,2) for a,b in zip(sp,baseline[n]['spf'])],'rqspf_delta_from_t1':[round(a-b,2) for a,b in zip(rq,baseline[n]['rqspf'])],'comment':comments[n],'lineups':'unverified','injuries':'unverified','confidence':'low' if n in ['002','003'] else 'medium_market_only'};details.append(d)
    report.append(f"|{n} {r['match_name']} {m['kickoff_time'][11:]}|{'/'.join(f'{x:.2f}' for x in sp)}|{m['home_handicap']} {'/'.join(f'{x:.2f}' for x in rq)}|{comments[n]}|{r['total_goals_suggestion']}|{r['correct_score_suggestion']}|{r['half_full_suggestion']}|{r['candidate_tier']}；首发伤停未验证|")
report+=['','## 全部组合与审查结论','','下列金额仅为假设/虚拟金额，返奖与净收益区间是命中条件下的值；未中返奖0，损失该假设本金。各方案共享比赛，不是相互独立，不应合计作为投入建议。']
for p in plans:
    p['review_disposition']=dispositions[p['plan_type']];report+=['',f"### {p['plan_type']}：{p['review_disposition']}",p['selections'],f"注数{p['bet_count']}，倍数{p['multiplier']}，每注金额{p['amount_per_bet']}元，假设合计{p['total_stake']}元；组合赔率{p['estimated_odds_min']}—{p['estimated_odds_max']}；命中返奖{p['estimated_payout_min']}—{p['estimated_payout_max']}元，命中净收益{p['estimated_net_min']}—{p['estimated_net_max']}元。",p['risk_notes']]
report+=['','## 15条单玩法观察候选','','H/D/A分别代表主胜/平/客胜。单关销售资格未独立核实，以下为理论观察，不能称可直接出票方案；生成器原始“符合体彩规则”文案不代表本次核验。比分/半全场候选包含防冷脚本，与主方向未必一致，不宣称概率最优。','','|场次/玩法|选项@赔率|假设注数/本金|命中返奖|命中净收益|','|---|---|---|---|---|']
for p in plays:report.append(f"|{p['title']}|{p['selections']}|{p['bet_count']}/{p['total_stake']}元|{p['estimated_payout_min']}—{p['estimated_payout_max']}|{p['estimated_net_min']}—{p['estimated_net_max']}|")
report+=['','## 真实入账方案','','0新增，未实际下注。稳健候选004主胜1.42×005主胜1.48=2.1016，仅展示；价值候选005×001因无保护共享005降观察。','','## 固定赔率影子方案（不入账）','','原始生成器给出001主胜×002客胜×003客胜，6.7079、虚拟2元、命中理论13.42元。但002/003为均衡盘仅观察，故拒绝登记；本轮固定赔率影子0新增。原始候选保留作为审计，不冒充已登记虚拟票。','','## 独立模型及外部结构观察','','v1/v2不适用于本批日职/韩职，五场均blocked。v2已冻结5条阻断证据，虚拟组合0新增。外盘仅001匹配，其余四场缺唯一映射。首发伤停未验证，不能填零。','外部三场结构对照：单关许可未核实，单关/三组二串/三串一体对照标记不可比，不计算收益或晋级。原候选比分分支按原样保存，不新增高风险比分串。','','## 下个节点','','18:15的006—014；22:30的015—024；013/015禁串保持。禁止把本次全站采集当晚批终版，晚批须重新抓取。']
out={'sales_day':'2026-09-06','batch':'001-005','frozen_at':now.isoformat(),'official_captured_at':'2026-09-06T16:32:05.692025+08:00','baseline':'artifacts/data/sporttery_t1_baseline_2026-09-06_1505.json','gate':js(prefix+'_gate.json'),'fixtures':details,'plans':plans,'play_candidates':plays,'external_odds':outer,'real_ledger_write':False,'ledger_sha256':ledger_hash,'fixed_shadow_recorded':False,'fixed_shadow_rejection':'002/003 observation-only directions fail low-risk requirement','external_structure_comparable':False,'external_structure_reason':'single-bet eligibility not verified','shadow_v2':js(prefix+'_shadow_v2.json')}
(ROOT/(prefix+'_detailed.md')).write_text('\n'.join(report)+'\n',encoding='utf-8')
(ROOT/(prefix+'_detailed.json')).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
(ROOT/'artifacts/data/external_structure_shadow_2026-09-06_001-005.json').write_text(json.dumps({'experiment_id':'20260906_001_005','is_shadow':True,'frozen_at':now.isoformat(),'comparable':False,'reason':'single-bet eligibility not verified','source':prefix+'_detailed.json','production_ledger_write':False},ensure_ascii=False,indent=2),encoding='utf-8')
assert hashlib.sha256(ledger.read_bytes()).hexdigest()==ledger_hash
print(json.dumps({'frozen_at':now.isoformat(),'report':prefix+'_detailed.md','real_ledger_unchanged':True,'fixed_shadow_rejected':True},ensure_ascii=False))
