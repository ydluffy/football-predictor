"""Bounded free CSV archive for F2/SWE/BRA; never mutates live models."""
import argparse, hashlib, io, json
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import Request, urlopen
import pandas as pd


def main():
    p=argparse.ArgumentParser();p.add_argument('--output-directory',required=True);a=p.parse_args()
    out=Path(a.output_directory);out.mkdir(parents=True,exist_ok=False)
    sources=[('F2',f'https://www.football-data.co.uk/mmz4281/{y:02d}{y+1:02d}/F2.csv') for y in range(20,27)]
    sources += [(c,f'https://www.football-data.co.uk/new/{c}.csv') for c in ('SWE','BRA')]
    audit={'captured_at':datetime.now(timezone.utc).isoformat(),'sources':[],'production_change_allowed':False};rows=[]
    today=pd.Timestamp.now(tz='UTC').floor('D')
    for i,(league,url) in enumerate(sources):
        record={'league':league,'url':url}
        try:
            with urlopen(Request(url,headers={'User-Agent':'football-predictor-research/1.0'}),timeout=25) as response:
                raw=response.read()
            path=out/f'{i:02d}_{league}.csv';path.write_bytes(raw)
            f=pd.read_csv(io.BytesIO(raw),encoding='utf-8-sig')
            if league=='F2':cols=['Date','HomeTeam','AwayTeam','FTHG','FTAG']
            else:cols=['Date','Home','Away','HG','AG']
            z=f[cols].copy();z.columns=['date','home_team','away_team','home_goals','away_goals']
            z['date']=pd.to_datetime(z.date,dayfirst=True,utc=True,errors='coerce')
            for c in ('home_goals','away_goals'):z[c]=pd.to_numeric(z[c],errors='coerce')
            valid=z.notna().all(axis=1)&(z.date<today)&(z.date>=pd.Timestamp('2020-01-01',tz='UTC'))
            valid &= (z.home_goals>=0)&(z.away_goals>=0)&(z.home_goals%1==0)&(z.away_goals%1==0)
            z=z[valid].copy();z['league']=league;rows.append(z)
            record.update(status='ok',raw_rows=len(f),accepted_rows=len(z),excluded_rows=len(f)-len(z),sha256=hashlib.sha256(raw).hexdigest(),raw=str(path))
        except Exception as exc:record.update(status='failed',error_type=type(exc).__name__)
        audit['sources'].append(record)
        (out/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(record),flush=True)
    if rows:
        z=pd.concat(rows,ignore_index=True)
        if z.duplicated(['league','date','home_team','away_team']).any():raise ValueError('duplicate archive identities')
        z.to_csv(out/'history.csv',index=False)
        audit.update(rows=len(z),league_counts=z.groupby('league').size().to_dict(),history_sha256=hashlib.sha256((out/'history.csv').read_bytes()).hexdigest())
    audit['status']='complete' if all(r['status']=='ok' for r in audit['sources']) else 'partial'
    (out/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
