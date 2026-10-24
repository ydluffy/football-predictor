"""Same-phase market/odds-free margin ablation. Research, never production."""
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.stats import poisson
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder,StandardScaler
from threadpoolctl import threadpool_limits
from evaluate.handicap_margin_movement_v3 import build_movement_model_frame
from evaluate.sporttery_handicap_model import aligned_margin_probabilities
from models.universal_goals import chronological_features,fit_coefficients,expected_goals

LEVELS=('closing_ah_line','closing_ah_home_probability','closing_market_home_probability','closing_market_draw_probability','closing_market_away_probability')
TOTALS=('closing_over_25_probability',)
MOVEMENT=('home_line_strength_delta','ah_home_probability_delta','market_home_probability_delta','over_25_probability_delta','favorite_hot_without_line_support','line_upgrade_without_price_support')
DISPERSION=('book_home_probability_std','book_draw_probability_std','book_away_probability_std','book_quote_count')
FORM=('form_home_attack','form_away_attack','form_home_defence','form_away_defence','form_log_league_goals')
GROUPS={'market_levels':LEVELS,'plus_totals':LEVELS+TOTALS,'plus_movement':LEVELS+TOTALS+MOVEMENT,'plus_dispersion':LEVELS+TOTALS+MOVEMENT+DISPERSION,'plus_team_form':LEVELS+TOTALS+MOVEMENT+DISPERSION+FORM}
BOOKS=('BWC','IWC','PSC','WHC','VCC')
HANDICAPS=(-2,-1,1,2)


def class_metrics(p,y,ordered=False):
    p=np.asarray(p);y=np.asarray(y,dtype=int)
    if p.ndim!=2 or len(p)!=len(y) or not np.isfinite(p).all() or (p<0).any() or not np.allclose(p.sum(axis=1),1):raise ValueError('invalid probability matrix')
    n=len(y);one=np.eye(p.shape[1])[y];loss=-np.log(np.clip(p[np.arange(n),y],1e-15,1));brier=((p-one)**2).sum(axis=1)
    conf=p.max(axis=1);hit=p.argmax(axis=1)==y;ece=0.
    for low in np.arange(0,1,.1):
        mask=(conf>=low)&(conf<low+.1) if low<.9 else (conf>=low)&(conf<=1)
        if mask.any():ece+=mask.mean()*abs(conf[mask].mean()-hit[mask].mean())
    result={'n':n,'log_loss':float(loss.mean()),'brier':float(brier.mean()),'top_label_ece':float(ece),'direction_accuracy':float(hit.mean())}
    values={'log_loss':loss,'brier':brier}
    if ordered:
        rps=((p.cumsum(axis=1)[:,:-1]-one.cumsum(axis=1)[:,:-1])**2).mean(axis=1)
        result['rps']=float(rps.mean());values['rps']=rps
    return result,values


def temperature(p,t):
    z=np.log(np.clip(p,1e-15,1))/t;z-=z.max(axis=1,keepdims=True);q=np.exp(z);return q/q.sum(axis=1,keepdims=True)


def calibrate(p,y):
    return float(minimize_scalar(lambda t:class_metrics(temperature(p,t),y)[0]['log_loss'],bounds=(.6,1.8),method='bounded').x)


def aggregate_margin(p,handicap=0):
    shifted=np.arange(-4,5)+handicap
    return np.stack([p[:,shifted>0].sum(axis=1),p[:,shifted==0].sum(axis=1),p[:,shifted<0].sum(axis=1)],axis=1)


def target_three(margin,handicap=0):
    return np.where(margin+handicap>0,0,np.where(margin+handicap<0,2,1))


def poisson_margin(rates,t=1.):
    g=np.arange(21);d=np.clip(g[:,None]-g[None,:],-4,4)
    z=(poisson.logpmf(g[None,:],rates[:,0,None])[:,:,None]+poisson.logpmf(g[None,:],rates[:,1,None])[:,None,:])/t
    z-=z.max(axis=(1,2),keepdims=True);p=np.exp(z);p/=p.sum(axis=(1,2),keepdims=True)
    return np.stack([p[:,d==i].sum(axis=1) for i in range(-4,5)],axis=1)


def build_frame(matches):
    if matches.duplicated('match_id').any():raise ValueError('duplicate match IDs')
    frame,audit=build_movement_model_frame(matches)
    quarter=np.isclose(frame.AHh*4,np.round(frame.AHh*4))&np.isclose(frame.AHCh*4,np.round(frame.AHCh*4))
    invalid_quarter=int((~quarter).sum());frame=frame[quarter].copy()
    quotes=[]
    for book in BOOKS:
        cols=[book+k for k in ('H','D','A')]
        if not all(c in frame for c in cols):continue
        raw=frame[cols].apply(pd.to_numeric,errors='coerce').to_numpy();ok=np.isfinite(raw).all(axis=1)&(raw>1).all(axis=1)
        q=np.full_like(raw,np.nan,dtype=float);inv=1/raw[ok];q[ok]=inv/inv.sum(axis=1,keepdims=True);quotes.append(q)
    if not quotes:raise ValueError('no contemporaneous bookmaker triplets')
    cube=np.stack(quotes,axis=1);count=np.isfinite(cube[:,:,0]).sum(axis=1);frame['book_quote_count']=count
    for j,k in enumerate(('home','draw','away')):
        values=cube[:,:,j];mean=np.nansum(values,axis=1)/np.maximum(count,1)
        std=np.sqrt(np.nansum((values-mean[:,None])**2,axis=1)/np.maximum(count,1));std[count<2]=np.nan
        frame['book_'+k+'_probability_std']=std
    # Form contains only earlier calendar-day scores, no current outcome or odds.
    f,x,_,skipped=chronological_features(matches)
    f['form_home_attack']=x[:,0,3];f['form_away_attack']=x[:,1,3]
    f['form_home_defence']=x[:,1,4];f['form_away_defence']=x[:,0,4];f['form_log_league_goals']=x[:,0,2]
    keys=['league','date','home_team','away_team']
    frame['date']=pd.to_datetime(frame.date,utc=True).dt.floor('D')
    before=len(frame);frame=frame.merge(f[keys+list(FORM)],on=keys,how='inner',validate='one_to_one').sort_values(['date','match_id']).reset_index(drop=True)
    audit.update(common_cohort_rows=len(frame),quarter_line_rejections=invalid_quarter,form_unavailable_excluded=before-len(frame),form_history_skipped=len(skipped),bookmakers=BOOKS,dispersion_rows_at_least_two=int((frame.book_quote_count>=2).sum()),same_cohort_for_all_arms=True,excluded_features=['season_progress','observed_speed_without_timestamps','raw_sporttery_minus_asian_line_as_advantage'],live_inner_outer_gap_features_available_in_proxy=False)
    return frame,audit


def make_model(features):
    transform=ColumnTransformer([('numeric',Pipeline([('impute',SimpleImputer(strategy='median',add_indicator=True)),('scale',StandardScaler())]),list(features)),('league',OneHotEncoder(handle_unknown='ignore'),['league'])])
    return Pipeline([('features',transform),('model',LogisticRegression(C=.5,max_iter=1500,tol=1e-6,solver='lbfgs'))])


def team_x(f):
    x=np.zeros((len(f),2,5));x[:,:,0]=1;x[:,0,1]=1;x[:,:,2]=f.form_log_league_goals.to_numpy()[:,None]
    x[:,0,3]=f.form_home_attack;x[:,1,3]=f.form_away_attack;x[:,0,4]=f.form_away_defence;x[:,1,4]=f.form_home_defence
    return x


def fit_fold(train,cal,test):
    assert train.date.max()<cal.date.min() and cal.date.max()<test.date.min()
    ycal=cal.margin_class.to_numpy()+4;predictions={};metadata={};models={}
    with threadpool_limits(limits=1):
        b=fit_coefficients(team_x(train),train[['home_goals','away_goals']].to_numpy())
        cr=expected_goals(team_x(cal),b);tr=expected_goals(team_x(test),b)
        t=float(minimize_scalar(lambda temp:class_metrics(poisson_margin(cr,temp),ycal)[0]['log_loss'],bounds=(.6,1.8),method='bounded').x)
        calp={'team_only':poisson_margin(cr,t)};predictions['team_only']=poisson_margin(tr,t);metadata['team_only']={'temperature':t};models['team_only']={'coefficients':b,'temperature':t}
        for name,features in GROUPS.items():
            model=make_model(features).fit(train,train.margin_class)
            if int(model.named_steps['model'].n_iter_.max())>=1500:raise ValueError('optimizer failed to converge: '+name)
            rawcal=aligned_margin_probabilities(model,cal);temp=calibrate(rawcal,ycal)
            calp[name]=temperature(rawcal,temp);predictions[name]=temperature(aligned_margin_probabilities(model,test),temp)
            metadata[name]={'temperature':temp,'features':features,'iterations':int(model.named_steps['model'].n_iter_.max())};models[name]={'pipeline':model,'temperature':temp}
        # This is a candidate learned blend, separate from the frozen 50% live control.
        trials=[(class_metrics((1-w)*calp['plus_dispersion']+w*calp['team_only'],ycal)[0]['log_loss'],w) for w in (0.,.25,.5,.75,1.)]
        _,weight=min(trials)
        predictions['learned_team_market_blend']=(1-weight)*predictions['plus_dispersion']+weight*predictions['team_only']
        metadata['learned_team_market_blend']={'team_weight':weight,'selected_only_on_prior_calibration':True,'trials':trials}
    return predictions,metadata,models
