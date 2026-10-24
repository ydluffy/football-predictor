"""Separate universal research forecast; cannot write comparison/production ledgers."""
import argparse,json,hashlib,sys
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from models.universal_goals import restore_history,expected_goals
from strategy.goal_distribution_tracking import forecast_fields
from models.independent_goals import score_distribution,aggregate
from data.competition_registry import load_team_alias_registry,load_competition_registry,normalize_alias


def main():
    p=argparse.ArgumentParser();p.add_argument('--scan-json',required=True);p.add_argument('--output',required=True);p.add_argument('--coverage-only',action='store_true');a=p.parse_args()
    cfg=json.loads((R/'config/universal_goals_research.json').read_text(encoding='utf-8'))
    source=R/cfg['model_artifact'];model=json.loads(source.read_text(encoding='utf-8'));state=restore_history(model)
    scanpath=R/a.scan_json;scan=json.loads(scanpath.read_text(encoding='utf-8-sig'));now=pd.Timestamp.now(tz='UTC')
    reg=load_team_alias_registry();comps=load_competition_registry()
    def key(t):return normalize_alias(reg.resolve(t) or t)
    rows=[]
    for f in scan['fixtures']:
        r={k:f[k] for k in ('match_id','home_team','away_team','kickoff')}
        r.update(model_id=model['model_id'],prediction_at=now.isoformat(),production_probability_change_allowed=False,can_trigger_bet_alone=False,route='universal_research_preview')
        comp=comps.resolve(f.get('competition_id')) or comps.resolve(f.get('competition'))
        league=cfg['competition_codes'].get(comp.competition_id) if comp and comp.competition_type=='league' else None
        reason=None;names={}
        for l,t in state.teams:
            if l==league:names.setdefault(key(t),[]).append(t)
        h=names.get(key(f['home_team']),[]);aw=names.get(key(f['away_team']),[])
        if pd.Timestamp(f['kickoff'])<=now:reason='after_kickoff'
        elif league is None:reason='unsupported_competition_type_or_league'
        elif len(h)!=1 or len(aw)!=1:reason='unknown_or_ambiguous_team'
        elif pd.Timestamp(model['trained_through'])>=now.floor('D'):reason='training_not_before_prediction_day'
        else:
            x,reason=state.features(league,h[0],aw[0],now.floor('D'),min_games=cfg['min_team_games'],max_age_days=cfg['max_team_history_age_days'])
        if reason:r.update(status='blocked',reason=reason)
        else:
            r.update(status='coverage_ready' if a.coverage_only else 'research_preview',league=league,reason='research_candidate_not_production',train_through=model['trained_through'])
            if not a.coverage_only:
                rates=expected_goals(x,model['coefficients']);joint,tail=score_distribution(*rates,temperature=model['temperature']);three,nine=aggregate(joint);r.update(forecast_fields(joint))
                r.update(lambda_home=float(rates[0]),lambda_away=float(rates[1]),tail_mass=tail)
                r.update({'p_'+k:float(v) for k,v in zip(('home','draw','away'),three)})
                r.update({'margin_probability_'+str(k):float(v) for k,v in zip(range(-4,5),nine)})
        rows.append(r)
    out=R/a.output;out.parent.mkdir(parents=True,exist_ok=True)
    result={'created_at':now.isoformat(),'coverage_only':a.coverage_only,'model_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'scan_sha256':hashlib.sha256(scanpath.read_bytes()).hexdigest(),'rows':rows,'production_promotion_allowed':False,'controller_live_enabled':False}
    result['prospective_shadow_enabled']=cfg.get('prospective_shadow_enabled',False)
    result['provenance_sha256']={str(path.relative_to(R)):hashlib.sha256(path.read_bytes()).hexdigest() for path in [R/'config/universal_goals_research.json',R/'data/mappings/team_aliases.json',R/'config/competitions.json',Path(__file__)]}
    with out.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps({'output':str(out),'ready':sum(r['status']!='blocked' for r in rows),'rows':len(rows),'coverage_only':a.coverage_only}))


if __name__=='__main__':main()
