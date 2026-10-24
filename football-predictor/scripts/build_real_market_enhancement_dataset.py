"""Identity/timestamp/official-label audit of real paired local snapshots."""
import argparse,json,hashlib,re,sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
import numpy as np
import pandas as pd
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from data.inner_outer_market_alignment import load_sporttery_market_snapshots
from data.competition_registry import load_team_alias_registry,normalize_alias
from import_sporttery_results import parse_results


def no_vig(values):
    try:a=np.asarray(values,dtype=float)
    except (ValueError,TypeError):return None
    if a.ndim!=1 or len(a) not in (2,3) or not np.isfinite(a).all() or not (a>1).all():return None
    a=1/a;return a/a.sum()


def parse_total(value):
    try:
        parts=[float(x) for x in str(value).split('/')]
        if len(parts) not in (1,2):return np.nan
        v=sum(parts)/len(parts)
        return v if np.isfinite(v) and 0<v<10 and abs(v*4-round(v*4))<1e-6 else np.nan
    except ValueError:return np.nan


def verify_capture_window(inner,quotes,kickoff,cutoff,as_of):
    captured=pd.to_datetime(quotes,utc=True,errors='coerce',format='ISO8601')
    if captured.isna().any() or not len(captured):raise ValueError('missing quote time')
    at=max(captured.max(),pd.Timestamp(inner))
    if at>=pd.Timestamp(kickoff) or at>=pd.Timestamp(cutoff) or at>pd.Timestamp(as_of):raise ValueError('late or future quote')
    if abs((captured.max()-pd.Timestamp(inner)).total_seconds())>1800:raise ValueError('time alignment exceeds thirty minutes')
    return at


def representative_line(quotes,reference):
    counts=defaultdict(int)
    for line,_ in quotes:counts[line]+=1
    line=min(counts,key=lambda v:(-counts[v],abs(v-reference),v))
    values=[p for l,p in quotes if l==line]
    return float(line),float(np.mean(values)),len(values)


def finalize_snapshot_frame(frame):
    f=frame.copy();f['at']=pd.to_datetime(f.prediction_at,utc=True,format='ISO8601')
    f=f.sort_values(['at','time_delta_minutes'],ascending=[True,False])
    f['observed_line_strength_per_hour']=np.nan;f['observed_common_books']=0
    for _,g in f.groupby('match_id'):
        for ix in g.index:
            current=f.loc[ix];prior=g[g['at']<current['at']-pd.Timedelta(minutes=5)]
            if prior.empty:continue
            previous=prior.iloc[-1];common=set(current.book_quotes)&set(previous.book_quotes)
            if len(common)<2:continue
            hours=(current['at']-previous['at']).total_seconds()/3600
            f.loc[ix,'observed_line_strength_per_hour']=float(np.median([previous.book_quotes[k][0]-current.book_quotes[k][0] for k in common]))/hours
            f.loc[ix,'observed_common_books']=len(common)
    f=f.drop_duplicates('match_id',keep='last').drop(columns='at');f['book_quotes']=f.book_quotes.map(json.dumps)
    return f


def main():
    p=argparse.ArgumentParser();p.add_argument('--pairs',required=True);p.add_argument('--output-directory',required=True);a=p.parse_args();out=R/a.output_directory;out.mkdir(parents=True,exist_ok=False)
    print(json.dumps({'stage':'started','at':pd.Timestamp.now(tz='UTC').isoformat()}),flush=True)
    aliases=load_team_alias_registry()
    def key(v):return normalize_alias(aliases.resolve(v) or v)
    # Parse only archived official API envelopes; do not trust arbitrary results CSVs.
    labels=defaultdict(set);voids=set();sources=[]
    candidates=list((R/'artifacts/data').glob('*result*raw*.json'))+list((R/'data/external/sporttery_results').glob('*.json'))+list((R/'data/raw').glob('sporttery_results*.json'))
    for source in sorted(set(candidates)):
        try:
            payload=json.loads(source.read_text(encoding='utf-8-sig'))
            if not isinstance(payload,dict) or not isinstance(payload.get('value'),dict) or 'matchResult' not in payload['value']:continue
            results=parse_results(payload)
        except (ValueError,RuntimeError):continue
        sources.append({'path':str(source.relative_to(R)),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'rows':len(results)})
        for r in results:
            score=re.fullmatch(r'(\d+)[:：](\d+)',r.full_time_score)
            if r.status=='已完成' and r.full_time_score.strip()=='无效场次':voids.add((r.date,r.match_number[-3:],key(r.home_team),key(r.away_team)))
            if r.status!='已完成' or not score:continue
            identity=(r.date,r.match_number[-3:],key(r.home_team),key(r.away_team))
            labels[identity].add((int(score[1]),int(score[2]),r.source_match_id))
    print(json.dumps({'stage':'official_labels_loaded','unique_identities':len(labels)}),flush=True)
    pairs=pd.read_csv(R/a.pairs,dtype={'match_id':str,'bookmaker_id':str,'match_number':str});pairs=pairs[pairs.time_aligned.astype(str).str.lower().eq('true')]
    index=pd.read_csv(R/'data/manual/sporttery_snapshot_index.csv',dtype=str).fillna('')
    index=index[index.source_type.eq('official_markets')&index.snapshot_id.isin(set(pairs.sporttery_snapshot_id))].copy()
    integrity={};integrity_failures=[];valid=[]
    for item in index.itertuples():
        path=Path(item.archive_path)
        if str(path) not in integrity:integrity[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        okay=integrity[str(path)]==item.sha256
        valid.append(okay)
        if not okay:integrity_failures.append({'snapshot_id':item.snapshot_id,'path':str(path),'reason':'archive_hash_mismatch'})
    index=index[valid];index.to_csv(out/'scoped_official_index.csv',index=False)
    inner=load_sporttery_market_snapshots(out/'scoped_official_index.csv')
    print(json.dumps({'stage':'official_snapshots_loaded','rows':len(inner)}),flush=True)
    inner_map={}
    for (snap,mid),g in inner.groupby(['snapshot_id','match_id']):
        distinct=g.drop_duplicates(subset=['home_team','away_team','kickoff_time','home_handicap','spf_odds_home','spf_odds_draw','spf_odds_away','rqspf_odds_home','rqspf_odds_draw','rqspf_odds_away'])
        if len(distinct)==1:inner_map[(snap,mid)]=distinct.iloc[0]
    quote_map={};identity_map={};archive_manifest=[]
    for directory in sorted((R/'data/external/nowscore/snapshots').iterdir()):
        qp=directory/'quotes.csv';ap=directory/'alignment.csv'
        if not qp.exists() or not ap.exists():continue
        q=pd.read_csv(qp,dtype={'bookmaker_id':str,'match_id':str});align=pd.read_csv(ap,dtype=str).fillna('')
        for _,record in align.iterrows():
            if record.get('mapping_status')=='mapped' and key(record['home_team'])==key(record.get('nowscore_home_team')) and key(record['away_team'])==key(record.get('nowscore_away_team')):
                identity_map[(str(directory),record['match_id'])]=record
        for mid,g in q.groupby('match_id'):
            current=g[(g.market=='asian_handicap')&(g.stage=='current')]
            for when in current.captured_at.unique():quote_map[(mid,pd.Timestamp(when).isoformat())]=(str(directory),g)
        archive_manifest.append({'path':str(qp.relative_to(R)),'sha256':hashlib.sha256(qp.read_bytes()).hexdigest()})
    print(json.dumps({'stage':'quotes_loaded','archives':len(archive_manifest),'lookup_entries':len(quote_map)}),flush=True)
    groups=pairs.groupby(['match_id','outer_snapshot_id','sporttery_snapshot_id']);data=[];skips=[]
    for (mid,outerid,innerid),group in groups:
        base=group.iloc[0];official=inner_map.get((innerid,mid))
        def skip(reason):skips.append({'match_id':mid,'outer_snapshot_id':outerid,'reason':reason})
        if official is None:skip('official_snapshot_identity_missing_or_ambiguous');continue
        # Nowscore is the only locally archived source with same-capture all-play quotes.
        when=pd.Timestamp(base.outer_captured_at);lookup=None
        for value in group.outer_captured_at.unique():
            lookup=quote_map.get((mid,pd.Timestamp(value).isoformat()))
            if lookup:break
        if not lookup:skip('same_capture_h2h_totals_archive_unavailable');continue
        directory,q=lookup;identity=identity_map.get((directory,mid))
        if identity is None:skip('source_home_away_identity_unverified');continue
        kickoff=pd.Timestamp(base.kickoff_at);source_kick=pd.Timestamp(identity['kickoff'])
        if source_kick.tzinfo is None:source_kick=source_kick.tz_localize('Asia/Shanghai')
        if kickoff!=source_kick:skip('kickoff_identity_changed');continue
        sales_day=mid.split('|')[0];cutoff=pd.Timestamp(sales_day,tz='Asia/Shanghai')+pd.Timedelta(hours=23 if pd.Timestamp(sales_day).weekday()>=5 else 22)
        captured=pd.to_datetime(q.captured_at,utc=True,errors='coerce',format='ISO8601')
        try:at=verify_capture_window(base.sporttery_captured_at,q.captured_at,kickoff,cutoff,pd.Timestamp.now(tz='UTC'))
        except ValueError:skip('quote_time_not_aligned_or_after_cutoff');continue
        spf=no_vig([official['spf_odds_'+k] for k in ('home','draw','away')]);rq=no_vig([official['rqspf_odds_'+k] for k in ('home','draw','away')])
        if spf is None or rq is None:skip('official_play_quotes_missing');continue
        if float(official.home_handicap)%1 or abs(float(official.home_handicap))>=4:skip('integer_handicap_outside_resolvable_nine_bin_tails');continue
        ids=set(group.bookmaker_id.astype(str));current=q[(q.stage=='current')&q.bookmaker_id.astype(str).isin(ids)]
        h2h=[];totals=[]
        for record in current[current.market=='h2h'].itertuples():
            p3=no_vig([record.home_odds,record.draw_odds,record.away_odds])
            if p3 is not None:h2h.append(p3)
        for record in current[current.market=='totals'].itertuples():
            p2=no_vig([record.over_odds,record.under_odds]);line=parse_total(record.total_line_raw)
            if p2 is not None and np.isfinite(line):totals.append((line,p2[0]))
        if not h2h or not totals:skip('same_bookmaker_common_markets_missing');continue
        matrix=np.array(h2h);ext=matrix.mean(axis=0)
        ah=[];deltas=[];book_quotes={}
        for book,g in current[current.market=='asian_handicap'].groupby('bookmaker_id'):
            if len(g)!=1:continue
            row=g.iloc[0];p2=no_vig([row.home_odds,row.away_odds]);line=pd.to_numeric(row.home_handicap,errors='coerce')
            if p2 is None or not np.isfinite(line):continue
            ah.append((line,p2[0]))
            book_quotes[str(book)]=(float(line),float(p2[0]))
            opening=q[(q.stage=='opening')&(q.market=='asian_handicap')&(q.bookmaker_id==book)]
            if len(opening)==1:
                old=opening.iloc[0];oldp=no_vig([old.home_odds,old.away_odds]);oldline=pd.to_numeric(old.home_handicap,errors='coerce')
                if oldp is not None and np.isfinite(oldline):deltas.append((oldline-line,p2[0]-oldp[0]))
        if not ah:skip('main_asian_quotes_missing');continue
        ahline,ahshare,ahn=representative_line(ah,0.)
        total_line,total_share,total_n=representative_line(totals,2.5)
        row={'match_id':mid,'sales_day':sales_day,'league':official.get('competition',''),'home_team':official.home_team,'away_team':official.away_team,'kickoff':kickoff.isoformat(),'prediction_at':at.isoformat(),'sporttery_snapshot_id':innerid,'outer_snapshot_id':outerid,'official_handicap':float(official.home_handicap),'outer_line_median':float(np.median([v[0] for v in ah])),'outer_home_price_share':float(np.mean([v[1] for v in ah])),'quote_count':len(matrix),'h2h_dispersion':float(matrix.std(axis=0).mean()) if len(matrix)>=2 else np.nan,'time_delta_minutes':abs((captured.max()-pd.Timestamp(base.sporttery_captured_at)).total_seconds())/60,'minutes_to_kickoff':(kickoff-at).total_seconds()/60,'outer_total_line':float(np.median([v[0] for v in totals])),'outer_over_price_share':float(np.mean([v[1] for v in totals])),'provider_reported_line_delta':float(np.mean([v[0] for v in deltas])) if deltas else np.nan,'provider_reported_price_delta':float(np.mean([v[1] for v in deltas])) if deltas else np.nan,'opening_timestamp_known':False,'provider_quote_update_age_known':False,'book_quotes':book_quotes}
        for j,k in enumerate(('home','draw','away')):row['official_spf_'+k]=float(spf[j]);row['official_rq_'+k]=float(rq[j]);row['external_spf_'+k]=float(ext[j]);row['probability_gap_'+k]=float(ext[j]-spf[j])
        row.update(outer_line_median=ahline,outer_home_price_share=ahshare,outer_total_line=total_line,outer_over_price_share=total_share,outer_asian_same_line_quotes=ahn,outer_total_same_line_quotes=total_n,outer_asian_line_dispersion=float(np.std([v[0] for v in ah])))
        identity_key=(kickoff.tz_convert('Asia/Shanghai').date().isoformat(),mid[-3:],key(official.home_team),key(official.away_team))
        candidates=labels.get(identity_key,set());scores={x[:2] for x in candidates}
        if identity_key in voids and not scores:row.update(label_status='official_void_excluded')
        elif identity_key in voids:row.update(label_status='conflicting_void_and_score')
        elif len(scores)==1:
            h,a=next(iter(scores));row.update(home_goals=h,away_goals=a,actual_margin=h-a,label_status='official_completed_unique',official_result_ids=';'.join(sorted({x[2] for x in candidates})))
        else:row.update(label_status='not_finished_at_asof' if kickoff>pd.Timestamp.now(tz='UTC') else 'missing_or_conflicting_official_result')
        data.append(row)
    f=pd.DataFrame(data)
    if not f.empty:
        checkpoint=f.copy();checkpoint['book_quotes']=checkpoint.book_quotes.map(json.dumps);checkpoint.to_csv(out/'safe_snapshots_checkpoint.csv',index=False)
        # A match, not each bookmaker/snapshot, is one statistical observation.
        f=finalize_snapshot_frame(f);f=f.rename(columns={'outer_line_median':'outer_primary_line'})
        f.to_csv(out/'events.csv',index=False)
    audit={'paired_input_events':pairs.match_id.nunique(),'same_market_feature_events':len(f),'official_labelled_events':int(f.label_status.eq('official_completed_unique').sum()) if len(f) else 0,'sample_unit':'unique_match_latest_safe_aligned_snapshot','opening_to_current_speed_available':False,'label_sources':sources,'nowscore_archive_sources':archive_manifest,'skipped_snapshots':skips,'min_training_events':300,'production_promotion_allowed':False,'feature_source_note':'probability gap is same-event SPF vs SPF; Asian share is not an integer-handicap three-way probability'}
    audit['development_training_ready']=audit['official_labelled_events']>=300
    audit['events_with_observed_same_book_speed']=int(f.observed_line_strength_per_hour.notna().sum()) if len(f) else 0
    audit['official_archive_integrity_failures']=integrity_failures
    (out/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in audit.items() if k not in ['label_sources','nowscore_archive_sources','skipped_snapshots']},ensure_ascii=False))


if __name__=='__main__':main()
