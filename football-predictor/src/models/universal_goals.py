"""Transferable odds-free club baseline; strict prior-day history only.

Shared coefficients act on smoothed team form relative to a league baseline.
No team-name coefficient or market field is a model input. This is a research
candidate, not permission to predict unknown teams or national/cup fixtures.
"""
from collections import defaultdict
import numpy as np
import pandas as pd
from scipy.optimize import minimize

FEATURES = ('intercept', 'home', 'log_league_goals', 'log_attack', 'log_opponent_defence')
REQUIRED = ('league', 'date', 'home_team', 'away_team', 'home_goals', 'away_goals')


def validate_history(frame):
    f = frame[list(REQUIRED)].copy()
    f['date'] = pd.to_datetime(f.date, utc=True, errors='raise', format='ISO8601').dt.floor('D')
    if f.isna().any().any():
        raise ValueError('missing history identity or score')
    for c in ('home_goals', 'away_goals'):
        v = pd.to_numeric(f[c], errors='raise')
        if not np.isfinite(v).all() or (v < 0).any() or (v % 1 != 0).any():
            raise ValueError('invalid completed score')
        f[c] = v.astype(int)
    for c in ('league', 'home_team', 'away_team'):
        if not f[c].map(lambda x: isinstance(x, str) and bool(x.strip())).all():
            raise ValueError('empty identity')
    if (f.home_team == f.away_team).any():
        raise ValueError('self fixture')
    if f.duplicated(['league', 'date', 'home_team', 'away_team']).any():
        raise ValueError('duplicate fixture; resolve sources explicitly')
    return f.sort_values(['date', 'league', 'home_team', 'away_team']).reset_index(drop=True)


class FormHistory:
    def __init__(self, alpha=.12, prior=8.):
        self.alpha, self.prior = alpha, prior
        self.teams = {}
        self.leagues = defaultdict(lambda: [0., 0])

    def features(self, league, home, away, date, min_games=5, max_age_days=120):
        states = [self.teams.get((league, t)) for t in (home, away)]
        if any(s is None or s['n'] < min_games for s in states):
            return None, 'insufficient_team_history'
        date = pd.Timestamp(date)
        if any(s['last'] >= date for s in states):
            return None, 'history_not_before_fixture'
        if any((date-s['last']).days > max_age_days for s in states):
            return None, 'stale_team_history'
        total, count = self.leagues[league]
        baseline = (total + 40*1.3)/(count + 40)
        def rate(s, key):
            w = s['n']/(s['n']+self.prior)
            return (w*s[key]+(1-w)*baseline)/baseline
        h, a = states
        x = [[1., 1., np.log(baseline), np.log(rate(h,'gf')), np.log(rate(a,'ga'))],
             [1., 0., np.log(baseline), np.log(rate(a,'gf')), np.log(rate(h,'ga'))]]
        return np.asarray(x), None

    def update(self, r):
        for team, gf, ga in ((r.home_team,r.home_goals,r.away_goals),
                             (r.away_team,r.away_goals,r.home_goals)):
            key = (r.league, team)
            old = self.teams.get(key)
            self.teams[key] = {'gf': float(gf) if old is None else (1-self.alpha)*old['gf']+self.alpha*gf,
                               'ga': float(ga) if old is None else (1-self.alpha)*old['ga']+self.alpha*ga,
                               'n': 1 if old is None else old['n']+1, 'last': r.date}
        v = self.leagues[r.league]
        v[0] += r.home_goals+r.away_goals
        v[1] += 2


def chronological_features(frame):
    f = validate_history(frame)
    state = FormHistory()
    rows, x, skipped = [], [], []
    for _, day in f.groupby('date', sort=True):
        # All fixtures on the same date are predicted before any result updates.
        for r in day.itertuples(index=False):
            features, reason = state.features(r.league, r.home_team, r.away_team, r.date)
            if features is None:
                skipped.append({**r._asdict(), 'reason': reason})
            else:
                rows.append(r._asdict()); x.append(features)
        for r in day.itertuples(index=False):
            state.update(r)
    return pd.DataFrame(rows), np.asarray(x), state, skipped


def fit_coefficients(x, goals, penalty=1.):
    x = np.asarray(x).reshape(-1,len(FEATURES))
    y = np.asarray(goals).reshape(-1)
    if len(y) < 50 or not np.isfinite(x).all():
        raise ValueError('insufficient or invalid training data')
    def loss(b):
        eta=x@b; mu=np.exp(eta)
        return float(np.mean(mu-y*eta)+penalty*np.sum(b[1:]**2)/(2*len(y))), x.T@(mu-y)/len(y)+np.r_[0,penalty*b[1:]/len(y)]
    result=minimize(loss,np.zeros(len(FEATURES)),jac=True,method='L-BFGS-B',bounds=[(-3,3)]*len(FEATURES))
    if not result.success:
        raise RuntimeError(result.message)
    return result.x


def expected_goals(x, coefficients):
    return np.clip(np.exp(np.asarray(x)@np.asarray(coefficients)), .1, 6.)


def restore_history(artifact):
    s=FormHistory(artifact['alpha'],artifact['prior'])
    s.leagues.update(artifact['leagues'])
    for item in artifact['teams']:
        s.teams[(item['league'],item['team'])]={k:(pd.Timestamp(v) if k=='last' else v)
                                             for k,v in item.items() if k not in ('league','team')}
    return s
