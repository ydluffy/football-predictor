"""Separate fallback-only prospective cohort and probability scoring."""
from strategy.goal_distribution_tracking import score_goals
import math
import re
from strategy.independent_comparison import build_comparison, probabilities
from strategy.october_research import number, timestamp, settle


def fallback_comparison(markets, universal, specialist):
    selected=[];route_skips=[]
    for row in markets:
        n=number(row['match_number'])
        def matches(p):
            return p.get('match_id','').endswith('|'+n) and p.get('home_team')==row['home_team'] and p.get('away_team')==row['away_team'] and timestamp(p['kickoff'])==timestamp(row['kickoff_time'])
        primary=[p for p in specialist if matches(p)]
        candidates=[p for p in universal if matches(p)]
        if len(primary)!=1:
            route_skips.append({'match_number':n,'reason':'specialist_identity_missing_or_ambiguous'});continue
        if primary[0]['status']=='research_only':
            route_skips.append({'match_number':n,'reason':'specialist_already_covers'});continue
        if primary[0]['status']!='blocked' or primary[0].get('reason') not in {'outside_training_leagues','unknown_or_ambiguous_training_team'}:
            route_skips.append({'match_number':n,'reason':'specialist_skip_not_eligible_for_fallback'});continue
        if len(candidates)!=1:
            route_skips.append({'match_number':n,'reason':'universal_identity_missing_or_ambiguous'});continue
        candidate=dict(candidates[0])
        if candidate.get('status')!='research_preview':
            route_skips.append({'match_number':n,'reason':candidate.get('reason','universal_unavailable')});continue
        candidate.update(status='research_only',reason='prospective_universal_fallback_research')
        candidate['specialist_skip_reason']=primary[0].get('reason')
        selected.append(candidate)
    result=build_comparison(markets,selected)
    # Exclude the generic identity skips for intentionally routed specialist rows.
    selected_numbers={p['match_id'].split('|')[-1] for p in selected}
    result['skips']=[s for s in result['skips'] if s['match_number'] in selected_numbers]+route_skips
    result['forecasts']=selected
    result['cohort']='specialist_unavailable_universal_fallback_only'
    result['protocol_version']='universal_fallback_v1'
    result['arm_labels']={'market':'market','independent':'universal_fallback','fusion':'fixed_50pct_universal_market'}
    return result


def score_snapshot(snapshot,results):
    review=settle(snapshot,results);review['goal_distribution_review']=score_goals(snapshot['matches'],results);scores=[];pending=[];void=[]
    names=['away_4plus','away_3','away_2','away_1','draw','home_1','home_2','home_3','home_4plus']
    for m in snapshot['matches']:
        matches=[r for r in results if number(r['match_number'])==number(m['match_number']) and r.get('home_team')==m['home_team'] and r.get('away_team')==m['away_team'] and r.get('date')==timestamp(m['kickoff_time']).date().isoformat() and r.get('status') in {'已完成','finished','completed'}]
        if len(matches)!=1:
            pending.append({'match_number':m['match_number'],'reason':'official_result_missing_or_ambiguous'});continue
        text=str(matches[0].get('full_time_score','')).strip()
        if text=='无效场次':void.append(m['match_number']);continue
        parsed=re.fullmatch(r'(\d+)[:：](\d+)',text)
        if not parsed:pending.append({'match_number':m['match_number'],'reason':'official_score_incomplete'});continue
        home,away=map(int,parsed.groups());margin=home-away
        def add(play,arm,probs,target):
            p=probabilities(probs)
            row={'match_number':m['match_number'],'play':play,'arm':arm,'target':target,'log_loss':-math.log(max(p[target],1e-15)),'brier':sum((v-(i==target))**2 for i,v in enumerate(p))}
            if play=='nine_bin_margin':
                row['ranked_probability_score']=sum((sum(p[:k+1])-(target<=k))**2 for k in range(len(p)-1))/(len(p)-1)
            scores.append(row)
        for play,arms in m.get('comparison_probabilities',{}).items():
            value=margin+(float(m['home_handicap']) if play=='rqspf' else 0)
            target=0 if value>0 else 2 if value<0 else 1
            for arm,probs in arms.items():add(play,arm,probs,target)
        add('nine_bin_margin','universal',[m['margin_probability_'+k] for k in names],min(4,max(-4,margin))+4)
    summaries={}
    for row in scores:summaries.setdefault(row['play']+'|'+row['arm'],[]).append(row)
    summaries={k:{'n':len(v),'log_loss':sum(r['log_loss'] for r in v)/len(v),'brier':sum(r['brier'] for r in v)/len(v),**({'ranked_probability_score':sum(r['ranked_probability_score'] for r in v)/len(v)} if 'ranked_probability_score' in v[0] else {})} for k,v in summaries.items()}
    review.update(probability_scores=scores,probability_summary=summaries,unique_matches_scored=len({s['match_number'] for s in scores}),probability_pending=pending,void_excluded_from_probability=void,probability_and_return_separate=True,cohort=snapshot['cohort'])
    return review
