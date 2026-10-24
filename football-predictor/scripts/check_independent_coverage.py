"""Read-only preflight; never creates probabilities or frozen predictions."""
import argparse,json,sys
from collections import Counter
from pathlib import Path
import pandas as pd
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from data.competition_registry import load_team_alias_registry,normalize_alias
LEAGUES={'ENG_PREMIER_LEAGUE':'E0','GER_BUNDESLIGA':'D1','FRA_LIGUE_1':'F1','ITA_SERIE_A':'I1','NED_EREDIVISIE':'N1','POR_PRIMEIRA_LIGA':'P1','ESP_LA_LIGA':'SP1'}

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser();p.add_argument('--scan-json',type=Path,required=True);a=p.parse_args()
    config=json.loads((R/'config/independent_goals_research.json').read_text(encoding='utf-8'));models=json.loads((R/config['model_artifact']).read_text(encoding='utf-8'));registry=load_team_alias_registry();now=pd.Timestamp.now(tz='UTC');rows=[]
    def key(name):return normalize_alias(registry.resolve(name) or name)
    for fixture in json.loads(a.scan_json.read_text(encoding='utf-8-sig'))['fixtures']:
        league=LEAGUES.get(fixture['competition_id']);v=models.get(league);reason='outside_training_leagues';age=None
        if v:
            counts=Counter(key(t) for t in v['teams']);reason='supported' if all(counts[key(fixture[k])]==1 for k in ['home_team','away_team']) else 'unknown_or_ambiguous_training_team'
            age=(now-pd.Timestamp(v['trained_through']).tz_localize('UTC')).days
        rows.append({'match_id':fixture['match_id'],'home_team':fixture['home_team'],'away_team':fixture['away_team'],'coverage':reason,'history_age_days':age})
    print(json.dumps({'model':config['model_artifact'],'diagnostic_only':True,'not_a_frozen_prediction':True,'counts':dict(Counter(r['coverage'] for r in rows)),'fixtures':rows},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
