from __future__ import annotations

import csv, json, re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-09-20"

def rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f: return list(csv.DictReader(f))

def side(score):
    h,a=map(int,score.split(":")); return "主胜" if h>a else "平" if h==a else "客胜"

def half_full(half, full):
    m={"主胜":"胜","平":"平","客胜":"负"}; return m[side(half)]+m[side(full)]

def main():
    result_rows=[r for r in rows(ROOT/'artifacts/data/sporttery_results_2026-09-20.csv') if r['match_number'].startswith('周日')]
    official={r['match_number'][-3:]:r for r in result_rows}
    assert set(official)=={f"{i:03d}" for i in range(1,31)}
    files=sorted((ROOT/'artifacts/data').glob('sporttery_final_analysis_2026-09-20_*.json'))
    predictions={}; schemes=[]
    for path in files:
        data=json.loads(path.read_text(encoding='utf-8'))
        for item in data['matches']:
            number=item['number']; assert number not in predictions; predictions[number]=item
        for scheme in data.get('shadow_schemes',[]): schemes.append({**scheme,'batch':data['scope']})
    assert set(predictions)=={f"{i:03d}" for i in range(2,31)}
    metrics=Counter(); per=[]
    for number in sorted(official):
        r=official[number]; p=predictions.get(number)
        h,a=map(int,r['full_time_score'].split(':')); actual_spf=side(r['full_time_score'])
        actual_rq=r['rqspf_result']; actual_goals=str(h+a) if h+a<7 else '7+'
        actual_hf=half_full(r['half_time_score'],r['full_time_score'])
        if not p:
            per.append({'number':number,'result':r,'missing':True}); continue
        prim=p['primary']['selection'] if p.get('primary') else ''
        defense=p['defense']['selection'] if p.get('defense') else ''
        rqprim=p['rq_primary']['selection']; rqdef=p['rq_defense']['selection']
        goals=[x['selection'] for x in p.get('goals',[])]; scores=[x['selection'] for x in p.get('scores',[])]; hfs=[x['selection'] for x in p.get('half_full',[])]
        if prim:
            metrics['spf_total']+=1; metrics['spf_primary_hits']+=prim==actual_spf; metrics['spf_covered_hits']+=actual_spf in (prim,defense)
        metrics['rq_total']+=1; metrics['rq_primary_hits']+=rqprim==actual_rq; metrics['rq_covered_hits']+=actual_rq in (rqprim,rqdef)
        for name, choices, actual in [('goals',goals,actual_goals),('score',scores,r['full_time_score']),('half_full',hfs,actual_hf)]:
            if choices: metrics[name+'_total']+=1; metrics[name+'_hits']+=actual in choices
        per.append({'number':number,'result':r,'missing':False,'prediction':p,'actual_spf':actual_spf,'actual_rq':actual_rq,'actual_goals':actual_goals,'actual_hf':actual_hf,'spf_hit':prim==actual_spf,'rq_hit':rqprim==actual_rq,'goals_hit':actual_goals in goals,'score_hit':r['full_time_score'] in scores,'hf_hit':actual_hf in hfs})
    formal=[r for r in rows(ROOT/'data/manual/betting_plan_ledger.csv') if r['date']==DAY]
    fixed=[r for r in rows(ROOT/'data/manual/fixed_odds_shadow_ledger.csv') if r['date']==DAY]
    fstake=sum(float(r['stake']) for r in formal); fpayout=sum(float(r['payout'] or 0) for r in formal); fnet=fpayout-fstake
    audit={'sales_day':DAY,'status':'completed','official_matches':len(official),'prediction_coverage':f"{len(predictions)}/30",'missing_prediction':['001'],'metrics':dict(metrics),'formal':formal,'formal_summary':{'plans':len(formal),'hits':sum(r['result']=='命中' for r in formal),'stake':fstake,'payout':fpayout,'net':fnet,'roi':fnet/fstake if fstake else None},'fixed_odds_shadow':fixed,'fixed_note':'当天终版报告生成了候选，但未调用固定赔率冻结命令，因此没有可结算的前瞻固定赔率票，不作事后补录。','displayed_shadow_scheme_count':len(schemes),'displayed_shadow_note':'报告展示方案未写影子组合台账，不能事后按正式收益入账。','per_match':per,'sources':[str(p.relative_to(ROOT)) for p in files],'supabase_sync':'not_authorized'}
    outj=ROOT/'artifacts/data/sporttery_full_review_2026-09-20_1300_detailed.json'; outj.write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# 2026-09-20销售日30场详细复盘','',f"官方赛果覆盖30/30；冻结终版预测覆盖29/30（001赛前终版漏跑，不补造）。正式模拟方案{len(formal)}组，命中{sum(r['result']=='命中' for r in formal)}组，投入{fstake:.2f}元、返奖{fpayout:.2f}元、净收益{fnet:+.2f}元、ROI {fnet/fstake:.2%}。未获当日Supabase同步授权。",'', '## 逐场核验','', '|编号|比赛|半场/全场|SPF首选→实际|让球首选→实际|进球候选→实际|比分/半全场|结论|','|---|---|---|---|---|---|---|---|']
    for x in per:
        r=x['result']; match=f"{r['home_team']}—{r['away_team']}"
        if x['missing']:
            lines.append(f"|{x['number']}|{match}|{r['half_time_score']} / {r['full_time_score']}|无冻结预测→{r['spf_result']}|无冻结预测→{r['rqspf_result']}|不计|不计|终版漏跑，只核实赛果|"); continue
        p=x['prediction']; gs='/'.join(i['selection'] for i in p.get('goals',[])); sc='/'.join(i['selection'] for i in p.get('scores',[])); hf='/'.join(i['selection'] for i in p.get('half_full',[])) or '未开'
        verdict=[]
        if not x['spf_hit']: verdict.append('SPF失')
        if not x['rq_hit']: verdict.append('让球失')
        if not x['goals_hit']: verdict.append('进球失')
        lines.append(f"|{x['number']}|{match}|{r['half_time_score']} / {r['full_time_score']}|{p['primary']['selection']}→{x['actual_spf']}（{'中' if x['spf_hit'] else '失'}）|{p['rq_primary']['selection']}→{x['actual_rq']}（{'中' if x['rq_hit'] else '失'}）|{gs}→{x['actual_goals']}（{'中' if x['goals_hit'] else '失'}）|{sc}；{hf}→{r['full_time_score']}/{x['actual_hf']}|{'、'.join(verdict) or '主要方向覆盖'}|")
    lines += ['', '## 正式模拟方案逐票复盘','', '|方案|完整选择|逐腿赛果|投入|返奖|净收益|ROI|','|---|---|---|---:|---:|---:|---:|']
    for r in formal: lines.append(f"|{r['plan_type']} {r['plan_id']}|{r['selections']}|{r['review_note']}|{float(r['stake']):.2f}|{float(r['payout']):.2f}|{float(r['net_profit']):+.2f}|{float(r['roi']):.2%}|")
    lines += ['', '## 指标汇总','', f"- SPF首选：{metrics['spf_primary_hits']}/{metrics['spf_total']}；首选+防守覆盖：{metrics['spf_covered_hits']}/{metrics['spf_total']}。", f"- 让球首选：{metrics['rq_primary_hits']}/{metrics['rq_total']}；首选+防守覆盖：{metrics['rq_covered_hits']}/{metrics['rq_total']}。", f"- 总进球候选：{metrics['goals_hits']}/{metrics['goals_total']}；比分候选：{metrics['score_hits']}/{metrics['score_total']}；半全场候选：{metrics['half_full_hits']}/{metrics['half_full_total']}。", '', '## 影子方案与错误归因','', f"- 当日报告展示影子方案共{len(schemes)}组，但未写入独立组合台账，故不事后补造投入、返奖或ROI。", '- 固定赔率影子：0个已冻结前瞻票；报告虽显示候选，未调用冻结命令，因此不能赛后补录。', '- 正式两组早批均断在014科莫客胜；晚批两组均命中，但共享027巴黎圣曼客胜，组合相关性较高。', '- 001没有冻结终版预测，是调度覆盖缺口；复盘只列0:0赛果，不生成赛后预测。', '- 外盘缺失时仅能评价体彩市场基线，不能把赛果反推为机构信号。', '', f"完整结构化审计：`{outj.relative_to(ROOT)}`"]
    outm=ROOT/'artifacts/reviews/sporttery_full_review_2026-09-20_1300_detailed.md'; outm.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'matches':30,'predictions':len(predictions),'formal':len(formal),'hits':sum(r['result']=='命中' for r in formal),'stake':fstake,'payout':fpayout,'net':fnet,'roi':fnet/fstake,'report':str(outm)},ensure_ascii=False))

if __name__=='__main__': main()
