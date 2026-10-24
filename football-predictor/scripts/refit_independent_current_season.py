"""Versioned current-season refit; frozen historical evaluation remains separate."""
import argparse, hashlib, json, sys
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from models.independent_goals import IndependentGoals, score_distribution, aggregate
from data.competition_registry import load_team_alias_registry, normalize_alias

# Explicit provider-to-history identities. No fuzzy or substring matching.
ALIASES={
'AFC Bournemouth':'Bournemouth','Arsenal FC':'Arsenal','Aston Villa FC':'Aston Villa','Brentford FC':'Brentford','Brighton & Hove Albion FC':'Brighton','Chelsea FC':'Chelsea','Coventry City FC':'Coventry','Crystal Palace FC':'Crystal Palace','Fulham FC':'Fulham','Hull City AFC':'Hull','Ipswich Town FC':'Ipswich','Leeds United FC':'Leeds','Liverpool FC':'Liverpool','Manchester City FC':'Man City','Manchester United FC':'Man United','Newcastle United FC':'Newcastle','Nottingham Forest FC':"Nott'm Forest",'Sunderland AFC':'Sunderland','Tottenham Hotspur FC':'Tottenham',
'1. FC Köln':'FC Koln','1. FC Union Berlin':'Union Berlin','Bayer 04 Leverkusen':'Leverkusen','Borussia Dortmund':'Dortmund','Borussia Mönchengladbach':"M'gladbach",'Eintracht Frankfurt':'Ein Frankfurt','FC Augsburg':'Augsburg','FC Bayern München':'Bayern Munich','FC Schalke 04':'Schalke 04','SC Freiburg':'Freiburg','SC Paderborn 07':'Paderborn','SV 07 Elversberg':'Elversberg','SV Werder Bremen':'Werder Bremen','TSG 1899 Hoffenheim':'Hoffenheim','VfB Stuttgart':'Stuttgart',
'ADO Den Haag':'Den Haag','AZ':'AZ Alkmaar','FC Groningen':'Groningen',"FC Twente '65":'Twente','FC Utrecht':'Utrecht','Fortuna Sittard':'For Sittard','NEC':'Nijmegen','PEC Zwolle':'Zwolle','PSV':'PSV Eindhoven','SC Cambuur-Leeuwarden':'Cambuur','Telstar 1963':'Telstar','Willem II Tilburg':'Willem II',
'AJ Auxerre':'Auxerre','AS Monaco FC':'Monaco','Angers SCO':'Angers','ES Troyes AC':'Troyes','FC Lorient':'Lorient','Le Havre AC':'Le Havre','Le Mans FC':'Le Mans','Lille OSC':'Lille','OGC Nice':'Nice','Olympique Lyonnais':'Lyon','Olympique de Marseille':'Marseille','Paris Saint-Germain FC':'Paris SG','Racing Club de Lens':'Lens','Stade Brestois 29':'Brest','Stade Rennais FC 1901':'Rennes','Toulouse FC':'Toulouse',
'Athletic Club':'Ath Bilbao','CA Osasuna':'Osasuna','Club Atlético de Madrid':'Ath Madrid','Deportivo Alavés':'Alaves','Getafe CF':'Getafe','Málaga CF':'Malaga','RC Celta de Vigo':'Celta','RC Deportivo La Coruña':'La Coruna','RCD Espanyol de Barcelona':'Espanol','Rayo Vallecano de Madrid':'Vallecano','Real Betis Balompié':'Betis','Real Racing Club de Santander':'Santander','Real Sociedad de Fútbol':'Sociedad',
'Académico de Viseu FC':'Academico Viseu','CF Estrela da Amadora':'Estrela','FC Porto':'Porto','Sport Lisboa e Benfica':'Benfica','Sporting Clube de Braga':'Sp Braga','Sporting Clube de Portugal':'Sp Lisbon','Vitória SC':'Guimaraes',
'AC Milan':'Milan','ACF Fiorentina':'Fiorentina','AS Roma':'Roma','Bologna FC 1909':'Bologna','Cagliari Calcio':'Cagliari','Como 1907':'Como','FC Internazionale Milano':'Inter','Genoa CFC':'Genoa','Juventus FC':'Juventus','SS Lazio':'Lazio','SSC Napoli':'Napoli','US Lecce':'Lecce','US Sassuolo Calcio':'Sassuolo'}
CODES={'PL':'E0','BL1':'D1','FL1':'F1','SA':'I1','DED':'N1','PPL':'P1','PD':'SP1'}

def score(probs,targets):
    p=np.array(probs);y=np.array(targets,dtype=int)
    return {'n':len(y),'log_loss':float(-np.log(np.clip(p[np.arange(len(y)),y],1e-15,1)).mean()),'brier':float(((p-np.eye(p.shape[1])[y])**2).sum(axis=1).mean())}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--raw-directory',type=Path,required=True);a=parser.parse_args()
    now=datetime.now(timezone.utc);stamp=now.strftime('%Y%m%dT%H%M%SZ');out=R/'artifacts/eval'/('independent_refresh_'+stamp);out.mkdir(parents=True,exist_ok=False)
    base=R/'data/processed/historical_matches_europe_extended_candidate.csv';f=pd.read_csv(base);f['date']=pd.to_datetime(f.date)
    oldpath=R/'artifacts/eval/independent_goals_20261012/research_models.json';old=json.loads(oldpath.read_text(encoding='utf-8'));reg=load_team_alias_registry()
    names={}
    for name in set(f.home_team)|set(f.away_team):names.setdefault(normalize_alias(reg.resolve(name) or name),set()).add(name)
    rows=[];rejected=[];hashes={}
    def identity(name):
        if name in ALIASES:return ALIASES[name]
        found=names.get(normalize_alias(reg.resolve(name) or name),set())
        return next(iter(found)) if len(found)==1 else None
    for code,league in CODES.items():
        path=a.raw_directory/(code+'.json')
        if not path.exists():rejected.append({'league':league,'reason':'provider_missing'});continue
        hashes[code]=hashlib.sha256(path.read_bytes()).hexdigest()
        for m in json.loads(path.read_text(encoding='utf-8')).get('matches',[]):
            dt=pd.Timestamp(m['utcDate']);s=m.get('score',{});g=s.get('fullTime',{})
            home=identity(m['homeTeam']['name']);away=identity(m['awayTeam']['name'])
            if m.get('status')!='FINISHED' or s.get('duration')!='REGULAR' or dt>=pd.Timestamp(now) or not home or not away or any(type(g.get(k)) is not int or g[k]<0 for k in ['home','away']):
                rejected.append({'id':m.get('id'),'home':m['homeTeam']['name'],'away':m['awayTeam']['name'],'reason':'identity_status_time_or_score'});continue
            rows.append({'match_id':'football_data_org_'+str(m['id']),'league':league,'season':'2026-2027','date':dt.tz_convert('UTC').tz_localize(None),'home_team':home,'away_team':away,'home_goals':g['home'],'away_goals':g['away']})
    recent=pd.DataFrame(rows)
    if recent.empty:raise ValueError('no valid new history; existing artifact retained')
    if recent.duplicated(['league','date','home_team','away_team']).any():raise ValueError('duplicate current-season identity')
    combined=pd.concat([f,recent],ignore_index=True).sort_values('date')
    if combined.duplicated(['league','date','home_team','away_team']).any():raise ValueError('overlapping source identities require review')
    combined.to_csv(out/'training_data.csv',index=False,encoding='utf-8-sig')
    models={};evaluation={}
    for league,group in combined.groupby('league'):
        v=old[league];new=recent[recent.league==league].sort_values('date')
        if len(new)<10:raise ValueError('insufficient current-season history: '+league)
        # Pre-update model was frozen on Oct 12. Older Aug/Sep outcomes are a
        # retrospective stress check, never relabelled as prospective validation.
        model=IndependentGoals(v['teams'],np.array(v['coefficients']),v['trained_through'],v['penalty'],v['half_life'])
        p3=[];p9=[];y3=[];y9=[]
        for row in new.itertuples():
            three,nine=aggregate(score_distribution(*model.rates(row.home_team,row.away_team),temperature=v['temperature'])[0]);margin=row.home_goals-row.away_goals
            p3.append(three);p9.append(nine);y3.append(0 if margin>0 else 2 if margin<0 else 1);y9.append(min(4,max(-4,margin))+4)
        evaluation[league]={'historical_model_current_season_stress_1x2':score(p3,y3),'historical_model_current_season_stress_margin':score(p9,y9),'new_rows':len(new)}
        fitted=IndependentGoals.fit(group,v['penalty'],v['half_life'])
        models[league]={**v,'teams':fitted.teams,'coefficients':fitted.coefficients.tolist(),'trained_through':fitted.trained_through,'scope':'research_only_current_season_refit','temperature':v['temperature']}
    (out/'research_models.json').write_text(json.dumps(models,ensure_ascii=False,indent=2),encoding='utf-8')
    report={'created_at':now.isoformat(),'new_rows':len(recent),'rejected':rejected,'source_hashes':hashes,'base_sha256':hashlib.sha256(base.read_bytes()).hexdigest(),'evaluation':evaluation,'calibration':'Inherited frozen prior-season temperatures; no tuning on current-season stress results','prospective_validation_complete':False,'production_promotion_allowed':False,'model_artifact':str((out/'research_models.json').relative_to(R))}
    (out/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=True),flush=True)

if __name__=='__main__':main()
