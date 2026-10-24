"""Freeze read-only market baseline, never generate or record betting plans."""
import csv
import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TZ = timezone(timedelta(hours=8))
def js(p):
    return json.loads((ROOT / p).read_text(encoding='utf-8-sig'))
def rows(p):
    with (ROOT / p).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))
def sha(p):
    return hashlib.sha256((ROOT / p).read_bytes()).hexdigest()

scanpath = 'artifacts/data/sporttery_sales_window_scan_2026-09-06_1505_confirm.json'
mp = 'data/manual/sporttery_handicap_markets_2026-09-06_1505_confirm.csv'
pp = 'data/manual/sporttery_play_odds_2026-09-06_1505_confirm.csv'
oldmp = 'data/manual/sporttery_handicap_markets_2026-09-06_1106_confirm.csv'
scan, markets, plays, oldmarkets = js(scanpath), rows(mp), rows(pp), rows(oldmp)
outer = js('artifacts/data/the_odds_api_sporttery_latest.json')
ledger = 'data/manual/betting_plan_ledger.csv'
before = sha(ledger)
evidence = [
    {'matches':['006'], 'finding':'英冠联赛，不是杯赛；体彩原页标英冠。狼队官方确认9月6日12:00英国当地时间开赛。', 'url':'https://www.wolves.co.uk/news/club/20260904-matchday-guide-birmingham-vs-wolves/'},
    {'matches':['009'], 'finding':'威尼斯官网赛前名单明确为意甲第3轮，9月6日15:00意大利当地时间。', 'url':'https://www.veneziafc.it/news/i-convocati-per-frosinone-venezia'},
    {'matches':['011'], 'finding':'特鲁瓦官网赛程明确为法甲第3轮，9月6日15:00法国当地时间。', 'url':'https://www.estac.fr/equipe-premiere/calendrier-resultats/'},
    {'matches':['012'], 'finding':'德甲官方赛程明确第2轮汉堡—美因茨，13:30 UTC即北京时间21:30；非21:00。', 'url':'https://products.bundesliga.com/fixtures'},
    {'matches':['024'], 'finding':'帕尔梅拉斯官网积分榜：帕尔梅拉斯第1，25场52分；博塔弗戈第12，24场30分。是对阵榜首而非榜首两队交锋。', 'url':'https://www.palmeiras.com.br/classificacao/brasileiro'},
    {'matches':['024'], 'finding':'博塔弗戈官网公布巴甲第26轮，9月6日18:30巴西当地时间，即北京时间9月7日05:30。', 'url':'https://botafogo.com.br/noticias/ingressos-botafogo-x-palmeiras-br26'},
]
report = ['# 2026-09-06 T1赔率与赛事属性基线', '',
          f"计划15:00；实际有效采集{scan['scanned_at']}。此前15:03尝试因沙箱抓取及归档权限失败，未当作有效基线；恢复后重新采集，不伪造15:00整点快照。", '',
          '本轮只冻结基线，不出终版或投注方案。方向仅为最低赔率所代表的市场倾向，不是独立模型预测，也不代表高置信或正期望。', '',
          '## 重点属性核验', '']
for e in evidence:
    report.append(f"- {','.join(e['matches'])}：{e['finding']} [官方来源]({e['url']})")
report += ['', '- 013：体彩整数让球为主队巴伦西亚+2，而不是巴萨+2。013全场禁串保持。', '- 015：本次主胜1.21，需与11:06冻结值比较；用户给出的1.22不是本次现价。015全场禁串保持。', '', '## 24场全量赔率与行程', '',
           '胜平负及让球三项均依次为主胜/平/客胜；让球是主队视角。Δ为相对11:06逐项绝对差，不是概率变化。所有时间为北京时间。', '',
           '|编号|赛事|主队—客队|开赛|SPF胜/平/负|主让球|RQSPF胜/平/负|SPF Δ|销售|T2/硬锁|', '|---|---|---|---|---|---|---|---|---|---|']
details=[]
def matchrow(f, table):
    found=[r for r in table if r['match_number']==f['match_number'] and r['home_team']==f['home_team'] and r['away_team']==f['away_team']]
    assert len(found)==1,(f['match_number'],len(found))
    return found[0]
def triple(r,prefix):
    return [float(r[f'{prefix}_odds_{x}']) for x in ['home','draw','away']]
def fmt(v):
    return '/'.join(f'{x:.2f}' for x in v)
for f in scan['fixtures']:
    n=f['match_number']; m=matchrow(f,markets); old=matchrow(f,oldmarkets)
    sp,rq=triple(m,'spf'),triple(m,'rqspf'); osp,orq=triple(old,'spf'),triple(old,'rqspf')
    delta=[round(a-b,2) for a,b in zip(sp,osp)]
    batch,lock=('16:30','16:45') if int(n)<=5 else (('18:15','18:45') if int(n)<=14 else ('22:30','22:45'))
    p=[r for r in plays if r['match_number']==n and r['home_team']==f['home_team'] and r['away_team']==f['away_team']]
    coverage={k:len([r for r in p if r['play_type']==k]) for k in ['total_goals','correct_score','half_full_time']}
    top={k:[{'selection':r['selection'],'odds':float(r['odds'])} for r in sorted([r for r in p if r['play_type']==k],key=lambda r:float(r['odds']))[:2]] for k in coverage}
    assert coverage=={'total_goals':8,'correct_score':31,'half_full_time':9},(n,coverage)
    d={**f,'home_handicap':m['home_handicap'],'spf':sp,'rqspf':rq,'spf_delta_from_1106':delta,'rqspf_delta_from_1106':[round(a-b,2) for a,b in zip(rq,orq)],'old_spf':osp,'old_rqspf':orq,'old_home_handicap':old['home_handicap'],'play_counts':coverage,'market_lowest_two':top,'all_play_odds':p,'t2_at':batch,'hard_lock':lock,'parlay_excluded':n in ['013','015'],'confidence':'market_only_no_independent_model','lineups':'not_verified','absences':'not_verified'}
    details.append(d)
    report.append(f"|{n}|{f['competition']}|{f['home_team']}—{f['away_team']}|{f['kickoff'][5:16].replace('T',' ')}|{fmt(sp)}|{m['home_handicap']}|{fmt(rq)}|{'/'.join(f'{x:+.2f}' for x in delta)}|{f['sale_status']}|{batch}/{lock}|")
report += ['', '## 四玩法覆盖与最低赔率参考（非预测方案）', '',
           '24场均取得SPF、RQSPF、8项总进球、31项比分、9项半全场；本日有效单玩法明细1152项。原抓取1536项包括其他销售日，已按编号和主客队严格筛选。', '',
           '|编号|SPF最低赔|RQSPF最低赔|总进球最低两项|比分最低两项|半全场最低两项|限制|', '|---|---|---|---|---|---|---|']
for d in details:
    s=['主胜','平','客胜'][d['spf'].index(min(d['spf']))]
    r=['让胜','让平','让负'][d['rqspf'].index(min(d['rqspf']))]
    vals=[' / '.join(f"{v['selection']}@{v['odds']:g}" for v in d['market_lowest_two'][k]) for k in ['total_goals','correct_score','half_full_time']]
    report.append(f"|{d['match_number']}|{s}@{min(d['spf']):g}|{r}@{min(d['rqspf']):g}|{'|'.join(vals)}|{'全场禁串' if d['parlay_excluded'] else '待T2刷新；非独立模型'}|")
report += ['', '## 外盘与数据边界', '', f"外盘状态：{outer.get('status')}；采集时间：{outer.get('captured_at')}。外盘映射仅使用同队同时间且唯一的记录，不能把未匹配视作无赔率。完整映射及请求审计见JSON。", '',
           '未验证首发、伤停、xG及旅行负荷，不能写成无伤停或阵容完整；不启用新的生产模型权重。杯赛疑点核验不自动授权模型晋级。', '',
           '## 真实入账方案', '', '本轮0新增，不生成投注方案；正式台账SHA-256执行前后相同。', '',
           '## 固定赔率影子方案（不入账）', '', 'T1不属于终版，不生成或登记2元虚拟组合。013、015禁串约束在后续所有串关候选及影子中保持。', '',
           '## 后续任务', '', '16:30 001—005；18:15 006—014；22:30 015—024；明天13:00详细复盘。T2必须引用本次15:05有效冻结基线并重新抓取。', '',
           '## 审计', '', f'- 官方扫描：{scanpath}', f'- 官方市场：{mp}', f'- 单玩法：{pp}', '- 次日注册表当前不存在，次日固定10:00/11:05/13:00仍由心跳保留。']
assert len(details)==24 and len({d['match_number'] for d in details})==24
assert before==sha(ledger)
out={'sales_day':'2026-09-06','stage':'T1_baseline','scheduled_at':'2026-09-06T15:00:00+08:00','captured_at':scan['scanned_at'],'completed_at':datetime.now(TZ).isoformat(),'scan_path':scanpath,'market_path':mp,'play_path':pp,'fixtures':details,'evidence':evidence,'external_odds_audit':outer,'source_sha256':{p:sha(p) for p in [scanpath,mp,pp,oldmp]},'ledger_sha256_before':before,'ledger_sha256_after':sha(ledger),'production_ledger_write_performed':False,'shadow_plan_write_performed':False,'initial_attempt_failure':'15:03 sandbox fetch failed and snapshot directory permission denied; refreshed under approved execution','next_day_registry_missing':True}
reportpath='artifacts/betting/sporttery_t1_baseline_2026-09-06_1505.md'
auditpath='artifacts/data/sporttery_t1_baseline_2026-09-06_1505.json'
(ROOT/reportpath).write_text('\n'.join(report)+'\n',encoding='utf-8')
(ROOT/auditpath).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'report':reportpath,'audit':auditpath,'completed_at':out['completed_at'],'fixtures':24,'spf_changed':sum(any(d['spf_delta_from_1106']) for d in details),'rqspf_changed':sum(any(d['rqspf_delta_from_1106']) for d in details),'outer_status':outer.get('status'),'outer_mapping':outer.get('alignment_summary'),'ledger_unchanged':before==sha(ledger)},ensure_ascii=False))

