"""Research-only forecast from saved odds-free goal models and verified scan."""
import argparse,json,sys,hashlib
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import pandas as pd
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from strategy.goal_distribution_tracking import forecast_fields
from models.independent_goals import IndependentGoals,score_distribution,aggregate,handicap_probability
from data.competition_registry import load_team_alias_registry,normalize_alias

def main():
    p=argparse.ArgumentParser();p.add_argument('--scan-json',required=True);p.add_argument('--output',required=True);p.add_argument('--model-json');a=p.parse_args()
    config=json.loads((R/'config/independent_goals_research.json').read_text(encoding='utf-8'))
    source=R/(a.model_json or config['model_artifact']);models=json.loads(source.read_text(encoding='utf-8'));scan=json.loads((R/a.scan_json).read_text(encoding='utf-8-sig'));registry=load_team_alias_registry();now=datetime.now(timezone.utc)
    leagues={'ENG_PREMIER_LEAGUE':'E0','GER_BUNDESLIGA':'D1','FRA_LIGUE_1':'F1','ITA_SERIE_A':'I1','NED_EREDIVISIE':'N1','POR_PRIMEIRA_LIGA':'P1','ESP_LA_LIGA':'SP1'}
    def key(name):return normalize_alias(registry.resolve(name) or name)
    rows=[]
    for f in scan['fixtures']:
        row={'match_id':f['match_id'],'home_team':f['home_team'],'away_team':f['away_team'],'kickoff':f['kickoff'],'prediction_at':now.isoformat(),'model_id':config['model_id'],'probability_source':'team_history_no_odds','can_trigger_bet_alone':False,'production_probability_change_allowed':False}
        league=leagues.get(f['competition_id']);row['league']=league
        if pd.Timestamp(f['kickoff'])<=pd.Timestamp(now):row.update(status='blocked',reason='after_kickoff')
        elif league not in models:row.update(status='blocked',reason='outside_training_leagues')
        else:
            v=models[league];names={}
            for t in v['teams']:names.setdefault(key(t),[]).append(t)
            home=names.get(key(f['home_team']),[]);away=names.get(key(f['away_team']),[])
            if len(home)!=1 or len(away)!=1:row.update(status='blocked',reason='unknown_or_ambiguous_training_team')
            elif pd.Timestamp(v['trained_through']).tz_localize('UTC')>=pd.Timestamp(now):row.update(status='blocked',reason='training_not_before_prediction')
            else:
                model=IndependentGoals(v['teams'],np.array(v['coefficients']),v['trained_through'],v['penalty'],v['half_life']);rates=model.rates(home[0],away[0]);joint,tail=score_distribution(*rates,temperature=v['temperature']);three,nine=aggregate(joint);row.update(forecast_fields(joint))
                age=(pd.Timestamp(now)-pd.Timestamp(v['trained_through']).tz_localize('UTC')).days
                row.update(status='research_only',reason='not_market_superior_in_holdout',train_through=v['trained_through'],lambda_home=rates[0],lambda_away=rates[1],tail_mass=tail,stale_history_days=age,history_freshness='stale' if age>config.get('history_warning_days',45) else 'current',primary_direction=['home','draw','away'][int(np.argmax(three))],primary_margin=int(np.argmax(nine))-4)
                for k,x in zip(['home','draw','away'],three):row['p_'+k]=x
                for k,x in zip(range(-4,5),nine):row['margin_probability_'+str(k)]=x
                for h in [-2,-1,1,2]:
                    for k,x in zip(['home','draw','away'],handicap_probability(nine,h)):row[f'handicap_{h}_p_{k}']=x
        rows.append(row)
    out=R/a.output;out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists():raise FileExistsError('research snapshot already exists; do not overwrite frozen forecasts')
    pd.DataFrame(rows).to_csv(out,index=False,encoding='utf-8-sig')
    audit={'prediction_at':now.isoformat(),'scan_sha256':hashlib.sha256((R/a.scan_json).read_bytes()).hexdigest(),'model_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'rows':len(rows),'research_eligible':sum(r['status']=='research_only' for r in rows),'production_promotion_allowed':False,'output':str(out)}
    out.with_suffix('.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(audit,ensure_ascii=True))

if __name__=='__main__':main()
