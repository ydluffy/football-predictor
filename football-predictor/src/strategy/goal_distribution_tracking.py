"""Prospective goal distributions and proper scoring, independent of stakes."""
import math
import re
import numpy as np
from strategy.october_research import number, timestamp

NAMES = ['away_4plus','away_3','away_2','away_1','draw','home_1','home_2','home_3','home_4plus']

def forecast_fields(joint):
    h,a=np.indices(joint.shape)
    total=h+a
    probs=[float(joint[np.minimum(total,7)==i].sum()) for i in range(8)]
    return {**{'total_probability_'+str(i):v for i,v in enumerate(probs)},
            'expected_total_goals':float((joint*total).sum()),
            'expected_goal_margin':float((joint*(h-a)).sum()),
            'primary_total_bucket':int(np.argmax(probs)),
            'goal_distribution_protocol':'joint_score_aggregate_v1'}

def score_goals(matches, results):
    scores=[];pending=[]
    for m in matches:
        candidates=[r for r in results if number(r.get('match_number',''))==number(m['match_number']) and r.get('home_team')==m['home_team'] and r.get('away_team')==m['away_team'] and r.get('date')==timestamp(m['kickoff_time']).date().isoformat() and r.get('status') in {'已完成','finished','completed'}]
        if len(candidates)!=1:
            pending.append({'match_number':m['match_number'],'reason':'official_result_missing_or_ambiguous'});continue
        text=str(candidates[0].get('full_time_score','')).strip()
        if text=='无效场次':continue
        parsed=re.fullmatch(r'(\d+)[:：](\d+)',text)
        if not parsed:
            pending.append({'match_number':m['match_number'],'reason':'official_score_incomplete'});continue
        h,a=map(int,parsed.groups())
        for play,keys,target in [('total_goals',[f'total_probability_{i}' for i in range(8)],min(7,h+a)),('nine_bin_margin',['margin_probability_'+k for k in NAMES],min(4,max(-4,h-a))+4)]:
            if not all(k in m for k in keys):
                pending.append({'match_number':m['match_number'],'play':play,'reason':'not_frozen_in_original_snapshot'});continue
            p=np.array([float(m[k]) for k in keys])
            if not np.isfinite(p).all() or (p<0).any() or abs(p.sum()-1)>1e-6:raise ValueError('invalid frozen goal distribution')
            scores.append({'match_number':m['match_number'],'play':play,'model_id':m.get('handicap_model_id'),'target':target,'log_loss':-math.log(max(p[target],1e-15)),'brier':float(((p-np.eye(len(p))[target])**2).sum()),'ranked_probability_score':float(((p.cumsum()[:-1]-(target<=np.arange(len(p)-1)))**2).mean()),'top_bucket_hit':int(p.argmax()==target)})
    summaries={}
    for play in ('total_goals','nine_bin_margin'):
        rows=[r for r in scores if r['play']==play]
        if rows:summaries[play]={'n':len(rows),**{k:sum(r[k] for r in rows)/len(rows) for k in ('log_loss','brier','ranked_probability_score','top_bucket_hit')}}
    return {'scores':scores,'summary':summaries,'pending':pending,'probability_and_return_separate':True}
