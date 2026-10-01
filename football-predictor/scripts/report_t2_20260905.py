import csv,json,hashlib
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):
    with (ROOT/p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
markets=read('artifacts/data/t2_2201_markets.csv')
pred={r['match_number']:r for r in read('artifacts/data/t2_2201_predictions.csv')}
old=[]
for stamp in ['1632','1731']:
    old.append({(r['home_team'],r['away_team']):r for r in read(f'data/manual/sporttery_handicap_markets_2026-09-05_{stamp}_confirm.csv')})
rows=[]
for r in markets:
    n=r['match_number']; p=pred.get(n,{})
    rq=min(['home','draw','away'],key=lambda k:float(r['rqspf_odds_'+k]))
    label={'home':'让胜','draw':'让平','away':'让负'}[rq]
    pick=p.get('favorite_label','SPF缺失')
    side={'主胜':'home','平':'draw','客胜':'away'}.get(pick)
    movement='SPF缺失'
    if side:
        movement='→'.join([o[(r['home_team'],r['away_team'])]['spf_odds_'+side] for o in old]+[r['spf_odds_'+side]])
    row={'编号':n,'比赛':r['home_team']+'—'+r['away_team'],'开赛':r['kickoff_time'][5:], 'SPF':pick,'赔率1632→1731→2201':movement,'让球':r['home_handicap']+label+'@'+r['rqspf_odds_'+rq],'进球':p.get('total_goals_suggestion','未形成模型判断'),'比分':p.get('correct_score_suggestion','未形成模型判断'),'半全场':p.get('half_full_suggestion','未形成模型判断'),'置信':'中低' if p.get('candidate_tier')=='强胆' else '低'}
    rows.append(row)
lines=['# 2026-09-05 T2第二批017—029','',f'生成时间：{datetime.now().astimezone().isoformat()}；官方快照22:01:58；13场在售。','', '全部方向主要来自赔率，比分和半全场为市场脚本，不是独立校准预测。阵容和伤停未在本轮核验。021缺SPF，027主客同赔；028辅助模型权重25%，让胜模型概率41.55%、融合43.12%，期望值为负。','']
lines+=['|'+'|'.join(rows[0])+'|','|'+'|'.join(['---']*len(rows[0]))+'|']
lines+=['|'+'|'.join(r.values())+'|' for r in rows]
lines+=['','## 真实入账方案','','本次0入账，未实际下单。稳健候选与价值候选共享028且无保护，不能同时作为正式组合；价值降级观察。所有返奖均以选项命中为条件，落空损失全部对应本金。','']
plans=read('artifacts/data/t2_2201_plans.csv')
for p in plans:
    lines += [f"- {p['plan_type']}：{p['selections']}；{p['bet_count']}注×{p['multiplier']}倍，金额{p['stake']}元；赔率{p['estimated_odds_min']}—{p['estimated_odds_max']}；命中返奖{p['estimated_payout_min']}—{p['estimated_payout_max']}元。未写真实台账。"]
lines+=['','## 固定赔率影子方案（不入账）','','7.9091倍候选含027主胜，但027主客同赔、无法认定低风险；本次仅保留候选，0条新增固定赔率台账。','', '## 总进球、比分、半全场观察','','以下39条为算法生成的独立观察候选，单关许可未逐场核验，不能直接认定可出票；不合并下注。']
for p in read('artifacts/data/t2_2201_candidates.csv'):
    lines += [f"- {p['title']}：{p['selections']}；{p['bet_count']}注×{p['multiplier']}倍，共{p['total_stake']}元虚拟金额；命中返奖{p['estimated_payout_min']}—{p['estimated_payout_max']}元；净收益{p['estimated_net_min']}—{p['estimated_net_max']}元。"]
lines+=['','外部结构对照：单关许可未核验，三种结构等权对照本次不可比，跳过。v2已记录13条预测，0虚拟组合。','']
(ROOT/'artifacts/data/t2_2201_detailed.md').write_text('\n'.join(lines),encoding='utf-8')
audit={'completed_at':datetime.now().astimezone().isoformat(),'scope':'017-029','markets':13,'plays':624,'real_ledger_write':False,'fixed_shadow_write':False,'value_status':'observation_shared_core_028_unprotected','fixed_status':'rejected_low_risk_not_established_027','external_structure':'skipped_single_market_permission_unverified','report':'artifacts/data/t2_2201_detailed.md','ledger_sha256':hashlib.sha256((ROOT/'data/manual/betting_plan_ledger.csv').read_bytes()).hexdigest(),'rows':rows}
(ROOT/'artifacts/data/t2_2201_completion.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(rows,ensure_ascii=False))
