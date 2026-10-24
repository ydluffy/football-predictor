"""Odds-free, regularized attack/defence Poisson research model."""
from dataclasses import dataclass
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

INPUT_COLUMNS = ('date','home_team','away_team','home_goals','away_goals')

@dataclass
class IndependentGoals:
    teams: list
    coefficients: np.ndarray
    trained_through: str
    penalty: float
    half_life: float

    @classmethod
    def fit(cls, frame, penalty=1., half_life=365.):
        f=frame[list(INPUT_COLUMNS)].copy()
        dates=pd.to_datetime(f.date)
        teams=sorted(set(f.home_team)|set(f.away_team)); index={t:i for i,t in enumerate(teams)}
        n=len(teams); x=np.zeros((2*len(f),2+2*n)); y=np.empty(2*len(f))
        for i,r in enumerate(f.itertuples(index=False)):
            h,a=index[r.home_team],index[r.away_team]
            x[2*i,[0,1,2+h,2+n+a]]=1.; x[2*i+1,[0,2+a,2+n+h]]=1.
            y[2*i:2*i+2]=r.home_goals,r.away_goals
        w=np.repeat(np.exp(-np.log(2)*(dates.max()-dates).dt.days.to_numpy()/half_life),2)
        def objective(beta):
            eta=x@beta; mu=np.exp(eta)
            loss=np.sum(w*(mu-y*eta))+penalty*np.sum(beta[2:]**2)/2
            grad=x.T@(w*(mu-y)); grad[2:]+=penalty*beta[2:]
            return loss,grad
        initial=np.zeros(x.shape[1]);initial[0]=np.log(max(y.mean(),.1))
        result=minimize(objective,initial,jac=True,method='L-BFGS-B',bounds=[(-4,4)]*len(initial))
        if not result.success:raise RuntimeError(result.message)
        return cls(teams,result.x,dates.max().isoformat(),float(penalty),float(half_life))

    def rates(self, home, away):
        idx={t:i for i,t in enumerate(self.teams)};n=len(idx);b=self.coefficients
        def attack(t):return b[2+idx[t]] if t in idx else 0.
        def defence(t):return b[2+n+idx[t]] if t in idx else 0.
        return np.exp([b[0]+b[1]+attack(home)+defence(away),b[0]+attack(away)+defence(home)])

def score_distribution(home_rate,away_rate,temperature=1.,max_goals=20):
    if home_rate<=0 or away_rate<=0 or temperature<=0:raise ValueError('rates and temperature must be positive')
    goals=np.arange(max_goals+1)
    logp=poisson.logpmf(goals,home_rate)[:,None]+poisson.logpmf(goals,away_rate)[None,:]
    scaled=logp/temperature;scaled-=scaled.max();p=np.exp(scaled);p/=p.sum()
    tail=1-poisson.cdf(max_goals,home_rate)*poisson.cdf(max_goals,away_rate)
    return p,float(tail)

def aggregate(p):
    h,a=np.indices(p.shape);margin=h-a
    nine=np.array([p[np.clip(margin,-4,4)==i].sum() for i in range(-4,5)])
    return np.array([p[margin>0].sum(),p[margin==0].sum(),p[margin<0].sum()]),nine

def handicap_probability(nine,handicap):
    if handicap not in [-2,-1,1,2]:raise ValueError('nine-bin tails support only -2/-1/+1/+2')
    nine=np.asarray(nine,dtype=float)
    shifted=np.arange(-4,5)+handicap
    return np.array([nine[shifted>0].sum(),nine[shifted==0].sum(),nine[shifted<0].sum()])
