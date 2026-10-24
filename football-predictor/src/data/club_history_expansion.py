"""Strict historical provider labels for independent club research."""
from collections import Counter
import pandas as pd

def verified_ucl_matches(payload, requested_season, cutoff):
    rows=[];rejected=Counter();seen=set();cutoff=pd.Timestamp(cutoff)
    for m in payload.get('matches',[]):
        if m.get('id') in seen:raise ValueError('duplicate provider match identity')
        seen.add(m.get('id'))
        if str(m.get('season',{}).get('startDate',''))[:4]!=str(requested_season):
            raise ValueError('provider season does not match requested season')
        date=pd.Timestamp(m.get('utcDate'));score=m.get('score',{});ft=score.get('fullTime',{})
        if m.get('status')!='FINISHED':rejected['not_finished']+=1;continue
        if date>=cutoff:rejected['not_before_cutoff']+=1;continue
        if score.get('duration')!='REGULAR':rejected['not_verified_90_minutes']+=1;continue
        goals=[ft.get('home'),ft.get('away')]
        if any(not isinstance(g,int) or isinstance(g,bool) or g<0 for g in goals):rejected['invalid_score']+=1;continue
        if m['homeTeam']['id']==m['awayTeam']['id']:raise ValueError('self fixture')
        rows.append({'source_match_id':m['id'],'date':date.isoformat(),'home_id':m['homeTeam']['id'],'away_id':m['awayTeam']['id'],'home_team':m['homeTeam']['name'],'away_team':m['awayTeam']['name'],'home_goals':goals[0],'away_goals':goals[1],'stage':m.get('stage'),'competition':'CL','season':requested_season})
    return rows,dict(rejected)
