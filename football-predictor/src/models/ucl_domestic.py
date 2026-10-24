"""Odds-free cross-competition Elo plus prior-day domestic attack/defence.
Research only. Elo starts with equal priors; relative league strength is learned
only through past cross-league matches, never external rankings or future results.
"""
from collections import defaultdict
import numpy as np
import pandas as pd
FEATURES=['intercept','home','elo_difference','domestic_attack','opponent_domestic_defence','domestic_goal_level']
class ClubState:
 def __init__(self):
  self.elo={};self.domestic={};self.leagues={};self.last={}
 def features(self,home,away,date,enhanced=True):
  date=pd.Timestamp(date);states=[self.domestic.get(str(t)) for t in [home,away]]
  if any(s is None or s['n']<5 for s in states):return None,'insufficient_domestic_history'
  if any(pd.Timestamp(s['last'])>=date for s in states):return None,'history_not_before_fixture'
  if any((date-pd.Timestamp(s['last'])).days>120 for s in states):return None,'stale_domestic_history'
  h,a=states;eh=self.elo.get(str(home),1500.);ea=self.elo.get(str(away),1500.)
  def values(s):
   total,n=self.leagues[s['league']];base=(total+52)/(n+40);w=s['n']/(s['n']+8)
   return (w*s['gf']+(1-w)*base)/base,(w*s['ga']+(1-w)*base)/base,base
  ha,hd,hb=values(h);aa,ad,ab=values(a)
  x=np.array([[1,1,(eh-ea)/400,np.log(ha),np.log(ad),np.log((hb+ab)/2)],
              [1,0,(ea-eh)/400,np.log(aa),np.log(hd),np.log((hb+ab)/2)]],dtype=float)
  if not enhanced:x[:,3:]=0
  return x,None
 def update(self,r):
  h,a=str(r['home_id']),str(r['away_id']);hg,ag=int(r['home_goals']),int(r['away_goals']);d=pd.Timestamp(r['date']).isoformat()
  eh,ea=self.elo.get(h,1500.),self.elo.get(a,1500.);q=1/(1+10**(-(eh+80-ea)/400));y=1 if hg>ag else .5 if hg==ag else 0;delta=20*(y-q)
  self.elo[h]=eh+delta;self.elo[a]=ea-delta;self.last[h]=d;self.last[a]=d
  if r['competition']=='CL':return
  league=r['competition'];v=self.leagues.setdefault(league,[0.,0]);v[0]+=hg+ag;v[1]+=2
  for t,gf,ga in [(h,hg,ag),(a,ag,hg)]:
   old=self.domestic.get(t);same=old is not None and old['league']==league
   self.domestic[t]={'league':league,'gf':.88*old['gf']+.12*gf if same else float(gf),'ga':.88*old['ga']+.12*ga if same else float(ga),'n':old['n']+1 if same else 1,'last':d}
 def as_dict(self):return {'elo':self.elo,'domestic':self.domestic,'leagues':self.leagues,'last':self.last}
 @classmethod
 def restore(cls,v):
  obj=cls()
  for key in ['elo','domestic','leagues','last']:setattr(obj,key,v[key])
  return obj

def chronological_examples(frame):
 frame=frame.copy();frame['date']=pd.to_datetime(frame.date,utc=True,format='ISO8601');frame=frame.sort_values(['date','source_match_id']);state=ClubState();rows=[];features=[];skips=[]
 if frame.source_match_id.duplicated().any():raise ValueError('duplicate provider match ID')
 # Prior UTC day only: all predictions generated before any same-day updates.
 for _,day in frame.groupby(frame.date.dt.floor('D'),sort=True):
  for r in day.to_dict('records'):
   if r['competition']!='CL' or r.get('stage')=='FINAL':continue
   x,reason=state.features(r['home_id'],r['away_id'],r['date'])
   if reason:skips.append({'source_match_id':r['source_match_id'],'reason':reason,'season':r['season']})
   else:rows.append(r);features.append(x)
  for r in day.to_dict('records'):state.update(r)
 return pd.DataFrame(rows),np.array(features),state,skips
