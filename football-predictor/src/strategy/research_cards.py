"""Named views of existing equal-budget controls; never additional tickets."""
def research_cards(comparison):
    definitions = [
        ('market_spf_direction','市场胜平负基准'),
        ('independent_spf_direction','独立模型胜平负'),
        ('independent_rqspf_direction','独立净胜球映射整数让球'),
        ('fusion_rqspf_direction','净胜球与市场固定50%融合'),
    ]
    cards=[]
    for family,label in definitions:
        plans=[e for e in comparison['experiments'] if e['family']==family]
        allocation=comparison['allocations'].get(family,{'budget':12.,'invested':0.,'unused':12.,'plans':0})
        cards.append({'label':label,'family':family,**allocation,'status':'generated' if plans else 'empty',
                      'reason':None if plans else 'no_eligible_model_market_identity_or_play',
                      'plans':plans,'simulation_only':True,'additional_stake':0.,
                      'budget_note':'view of existing experiments; do not add this stake again',
                      'evidence':'frozen_model_probabilities_and_current_official_odds',
                      'validated_advantage':False})
    return cards
