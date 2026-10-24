"""Matched-universe paper comparisons; no production ledger access."""
from math import isfinite
from strategy.research_cards import research_cards
from strategy.cross_play_selection import select_cross_play
from models.independent_goals import handicap_probability
from strategy.october_research import KEYS,LABELS,number,timestamp

def probabilities(values):
    v=[float(x) for x in values]
    if not all(isfinite(x) and 0<=x<=1 for x in v) or abs(sum(v)-1)>1e-6:raise ValueError('invalid probability vector')
    return v

def build_comparison(markets,predictions,budget=12.,weight=.5,policies=('direction',)):
    if budget<=0 or not 0<=weight<=1:raise ValueError('invalid research settings')
    if not policies or any(p not in {'direction','estimated_value'} for p in policies):raise ValueError('invalid comparison policies')
    experiments=[];matches=[];skips=[];groups={}
    for r in markets:
        n=number(r['match_number'])
        ps=[p for p in predictions if str(p.get('match_id','')).endswith('|'+n) and p['home_team']==r['home_team'] and p['away_team']==r['away_team'] and timestamp(p['kickoff'])==timestamp(r['kickoff_time'])]
        if len(ps)!=1:
            skips.append({'match_number':n,'reason':'model_identity_missing_or_ambiguous'});continue
        if ps[0]['status']!='research_only':
            skips.append({'match_number':n,'reason':ps[0].get('reason') or 'model_status_unavailable'});continue
        p=ps[0];nine=probabilities([p['margin_probability_'+str(k)] for k in range(-4,5)])
        match={**r,'handicap_model_id':p['model_id'],'margin_probability_source':'team_history_no_odds','prediction_at':p['prediction_at'],'p_home':float(p['p_home']),'p_draw':float(p['p_draw']),'p_away':float(p['p_away']),'stale_history_days':p.get('stale_history_days'),'comparison_probabilities':{}}
        match.update({k:float(v) if k!='goal_distribution_protocol' else v for k,v in p.items() if k.startswith('total_probability_') or k in {'expected_total_goals','expected_goal_margin','primary_total_bucket','goal_distribution_protocol'}})
        names=['away_4plus','away_3','away_2','away_1','draw','home_1','home_2','home_3','home_4plus']
        match.update({'margin_probability_'+name:x for name,x in zip(names,nine)});matches.append(match)
        for play in ['spf','rqspf']:
            try:
                odds=[float(r[f'{play}_odds_{k}']) for k in KEYS]
                if not all(isfinite(x) and x>1 for x in odds):raise ValueError('missing odds')
                independent=probabilities([p['p_'+k] for k in KEYS] if play=='spf' else handicap_probability(nine,float(r['home_handicap'])))
            except (ValueError,KeyError,TypeError):skips.append({'match_number':n,'play':play,'reason':'odds_or_supported_handicap_missing'});continue
            inv=[1/x for x in odds];market=[x/sum(inv) for x in inv]
            arms={'market':market,'independent':independent,'fusion':[(1-weight)*a+weight*b for a,b in zip(market,independent)]}
            match['comparison_probabilities'][play]=arms
            for arm,probs in arms.items():
                for policy in policies:
                    ev=[a*b-1 for a,b in zip(probs,odds)]
                    idx=max(range(3),key=lambda i:probs[i] if policy=='direction' else ev[i])
                    family=arm+'_'+play+'_'+policy;groups.setdefault(family,[])
                    if policy=='estimated_value' and ev[idx]<=0:continue
                    leg={'match_number':n,'home_team':r['home_team'],'away_team':r['away_team'],'kickoff_time':r['kickoff_time'],'home_handicap':r['home_handicap'],'play':play,'probability_source':arm,'selections':[{'key':KEYS[idx],'label':LABELS[play][idx],'odds':odds[idx],'probability':probs[idx]}]}
                    groups[family].append({'experiment_id':family+'_'+n,'family':family,'structure':'single_theoretical_equal_budget','is_shadow':True,'real_money_allowed':False,'ticket_eligibility':'unverified_theoretical','positive_ev_claim':False,'model_estimated_ev':ev[idx],'legs':[leg],'tickets':[{'keys':[KEYS[idx]],'odds':odds[idx]}]})
    allocations={}
    for family,items in groups.items():
        stake=budget/len(items) if items else 0.
        allocations[family]={'budget':budget,'invested':budget if items else 0.,'unused':0. if items else budget,'plans':len(items)}
        for e in items:e['stake']=stake;e['tickets'][0]['stake']=stake;experiments.append(e)
    result = {'experiments':experiments,'matches':matches,'skips':skips,'allocations':allocations,'fusion_weight':weight,'warning':'Direction is mechanical observation; positive estimated EV is not validated advantage. Fractional equal stakes are theoretical normalization, not issued tickets.'}
    result['research_cards']=research_cards(result)
    cross=select_cross_play(matches)
    result['cross_play_selection']=cross
    result['experiments'].extend(cross['experiments'])
    result['allocations']['cross_play_stress_v1']=cross['allocation']
    result['research_cards'].append({'label':'跨玩法估值筛选：单场与二串一对照','family':'cross_play_stress_v1',**cross['allocation'],'plans':cross['experiments'],'status':'generated' if cross['experiments'] else 'empty','reason':None if cross['experiments'] else 'no_option_passed_rules','validated_advantage':False,'simulation_only':True,'additional_stake':cross['allocation']['invested'],'budget_note':'separate research family, 12 total including single and double tickets; never add again from card view'})
    return result
