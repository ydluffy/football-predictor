"""Frozen cross-play paper selection; heuristic stress is not confidence."""
from math import isfinite,prod
from strategy.october_research import KEYS,LABELS

POLICY={'version':'cross_play_stress_v1','budget':12.,'max_matches':2,
        'probability_stress':.05,'min_model_probability':.35,
        'min_estimated_ev':.05,'max_odds':5.,'production_enabled':False,
        'note':'Predeclared research heuristics, not calibrated confidence bounds or validated advantage.'}

def select_cross_play(matches):
    observations=[];candidates=[]
    for m in matches:
        options=[]
        for play,arms in m.get('comparison_probabilities',{}).items():
            for i,key in enumerate(KEYS):
                odds=float(m[f'{play}_odds_{key}']);p=float(arms['independent'][i]);market=float(arms['market'][i]);fusion=float(arms['fusion'][i])
                if not isfinite(odds) or odds<=1:continue
                ev=fusion*odds-1;stress=max(0.,fusion-POLICY['probability_stress']);stress_ev=stress*odds-1
                eligible=p>=POLICY['min_model_probability'] and odds<=POLICY['max_odds'] and ev>=POLICY['min_estimated_ev'] and stress_ev>=0
                options.append({'play':play,'key':key,'label':LABELS[play][i],'odds':odds,'independent_probability':p,'market_probability':market,'fusion_probability':fusion,'break_even_probability':1/odds,'model_estimated_ev':ev,'stress_probability':stress,'stress_estimated_ev':stress_ev,'eligible':eligible,'stress_is_confidence_bound':False})
        eligible=[x for x in options if x['eligible']]
        pick=max(eligible,key=lambda x:(x['stress_estimated_ev'],x['fusion_probability'])) if eligible else None
        observations.append({'match_number':m['match_number'],'home_team':m['home_team'],'away_team':m['away_team'],'home_handicap':m['home_handicap'],'model_id':m.get('handicap_model_id'),'options':options,'highest_probability':max(options,key=lambda x:x['independent_probability']) if options else None,'selected':pick,'reason':None if pick else 'no_option_passed_predeclared_price_probability_stress_rules'})
        if pick:candidates.append((m,pick))
    candidates=sorted(candidates,key=lambda x:(-x[1]['stress_estimated_ev'],x[0]['match_number']))[:POLICY['max_matches']]
    family='cross_play_stress_v1';experiments=[]
    def leg(m,p):
        return {**{k:m[k] for k in ['match_number','home_team','away_team','kickoff_time','home_handicap']},'play':p['play'],'probability_source':'fixed_50pct_model_market_stress_screen','selections':[{'key':p['key'],'label':p['label'],'odds':p['odds'],'probability':p['fusion_probability']}]}
    def experiment(suffix,items,stake):
        legs=[leg(m,p) for m,p in items]
        return {'experiment_id':family+'_'+suffix,'family':family,'structure':'single_theoretical' if len(items)==1 else 'two_leg_theoretical','is_shadow':True,'real_money_allowed':False,'positive_ev_claim':False,'ticket_eligibility':'unverified_theoretical','stake':stake,'legs':legs,'tickets':[{'keys':[p['key'] for m,p in items],'odds':prod(p['odds'] for m,p in items),'stake':stake}],'joint_probability_status':'not_estimated_correlation_unknown' if len(items)>1 else 'single_model_estimate'}
    for m,p in candidates:experiments.append(experiment(m['match_number'],[(m,p)],3. if len(candidates)==2 else 6.))
    if len(candidates)==2:experiments.append(experiment('double',candidates,6.))
    invested=sum(e['stake'] for e in experiments)
    return {'policy':dict(POLICY),'observations':observations,'experiments':experiments,'allocation':{'budget':12.,'invested':invested,'unused':12.-invested,'plans':len(experiments)},'simulation_only':True,'validated_advantage':False}
