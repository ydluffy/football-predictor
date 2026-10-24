"""Outcome taxonomy for pregame favorites; no wager or production access."""
import math
import numpy as np
from evaluate.asian_handicap_research import split_asian_line,normalize_quarter_line

def no_vig(values):
    x=np.asarray(values,dtype=float)
    if len(x)!=3 or not np.isfinite(x).all() or (x<=1).any():raise ValueError('three current valid prices required')
    inv=1/x
    return inv/inv.sum()

def favorite_side(probabilities,minimum=.5):
    p=np.asarray(probabilities)
    if abs(p[0]-p[2])<1e-12:return None
    i=0 if p[0]>p[2] else 2
    return i if p[i]>=minimum else None

def classify(home_goals,away_goals,side,home_line):
    """Three risks and fourth safe outcome; half wins are not full covers."""
    d=(int(home_goals)-int(away_goals))*(1 if side==0 else -1)
    line=normalize_quarter_line(home_line)
    selected=line if side==0 else -line if line is not None else None
    valid=selected is not None and selected<0
    threshold=max(-x for x in split_asian_line(selected)) if valid else None
    category='favorite_loss' if d<0 else 'favorite_draw' if d==0 else ('win_not_full_cover' if valid and d<=threshold else 'full_cover' if valid else 'win_handicap_unknown')
    return {'favorite_margin':d,'category':category,'cover_valid':valid,'full_cover_threshold':threshold,'nine_bin_cover_supported':valid and threshold<4}

def risk_probabilities(nine,side,threshold):
    p=np.asarray(nine,dtype=float)
    if len(p)!=9 or not np.isfinite(p).all() or (p<0).any() or not np.isclose(p.sum(),1):raise ValueError('invalid nine-bin probabilities')
    if threshold>=4:raise ValueError('nine-bin 4plus cannot resolve this cover boundary')
    margin=np.arange(-4,5)*(1 if side==0 else -1)
    return np.array([p[margin<0].sum(),p[margin==0].sum(),p[(margin>0)&(margin<=threshold)].sum(),p[margin>threshold].sum()])

def binary_metrics(p,y):
    p=np.clip(np.asarray(p,dtype=float),1e-15,1-1e-15);y=np.asarray(y,dtype=float)
    return {'n':len(y),'observed_rate':float(y.mean()),'mean_probability':float(p.mean()),'log_loss':float(-(y*np.log(p)+(1-y)*np.log(1-p)).mean()),'brier':float(((p-y)**2).mean()),'calibration_bias_observed_minus_predicted':float((y-p).mean())}
