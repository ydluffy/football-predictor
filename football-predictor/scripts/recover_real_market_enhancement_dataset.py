"""Finalize our own safe snapshot checkpoint; reverify archives and labels."""
import argparse,json,hashlib,re,sys
from collections import defaultdict
from pathlib import Path
import pandas as pd
import numpy as np
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from data.competition_registry import load_team_alias_registry,normalize_alias
from build_real_market_enhancement_dataset import finalize_snapshot_frame,verify_capture_window
from import_sporttery_results import parse_results


def main():
    p=argparse.ArgumentParser();p.add_argument('--checkpoint-directory',required=True);p.add_argument('--pairs',required=True);p.add_argument('--output-directory',required=True);a=p.parse_args()
    previous=R/a.checkpoint_directory;out=R/a.output_directory;out.mkdir(parents=True,exist_ok=False)
    checkpoint=previous/'safe_snapshots_checkpoint.csv';f=pd.read_csv(checkpoint)
    reg=load_team_alias_registry()
    def key(v):return normalize_alias(reg.resolve(v) or v)
    labels=defaultdict(set);voids=set();sources=[]
    candidates=list((R/'artifacts/data').glob('*result*raw*.json'))+list((R/'data/external/sporttery_results').glob('*.json'))+list((R/'data/raw').glob('sporttery_results*.json'))
    for source in sorted(set(candidates)):
        try:
            value=json.loads(source.read_text(encoding='utf-8-sig'))
            if not isinstance(value,dict) or not isinstance(value.get('value'),dict) or 'matchResult' not in value['value']:continue
            results=parse_results(value)
        except (ValueError,RuntimeError):continue
        sources.append({'path':str(source.relative_to(R)),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'rows':len(results)})
        for r in results:
            score=re.fullmatch(r'(\d+)[:：](\d+)',r.full_time_score)
            if r.status=='已完成' and r.full_time_score.strip()=='无效场次':voids.add((r.date,r.match_number[-3:],key(r.home_team),key(r.away_team)))
            if r.status=='已完成' and score:labels[(r.date,r.match_number[-3:],key(r.home_team),key(r.away_team))].add((int(score[1]),int(score[2]),r.source_match_id))
    index=pd.read_csv(previous/'scoped_official_index.csv',dtype=str).fillna('');integrity={}
    for item in index.itertuples():
        path=Path(item.archive_path)
        if str(path) not in integrity:integrity[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        if integrity[str(path)]!=item.sha256:raise ValueError('immutable official archive changed')
    now=pd.Timestamp.now(tz='UTC');verified=[]
    for _,row in f.iterrows():
        kick=pd.Timestamp(row.kickoff);at=pd.Timestamp(row.prediction_at)
        cutoff=pd.Timestamp(row.sales_day,tz='Asia/Shanghai')+pd.Timedelta(hours=23 if pd.Timestamp(row.sales_day).weekday()>=5 else 22)
        if at>=kick or at>=cutoff or at>now:raise ValueError('checkpoint contains late/future observation')
        identity=(kick.tz_convert('Asia/Shanghai').date().isoformat(),row.match_id[-3:],key(row.home_team),key(row.away_team));records=labels.get(identity,set());scores={r[:2] for r in records}
        d=row.to_dict();d['book_quotes']=json.loads(d['book_quotes'])
        if identity in voids and not scores:d.update(home_goals=np.nan,away_goals=np.nan,actual_margin=np.nan,label_status='official_void_excluded')
        elif identity in voids:d.update(home_goals=np.nan,away_goals=np.nan,actual_margin=np.nan,label_status='conflicting_void_and_score')
        elif len(scores)==1:
            h,away=next(iter(scores));d.update(home_goals=h,away_goals=away,actual_margin=h-away,label_status='official_completed_unique',official_result_ids=';'.join(sorted({r[2] for r in records})))
        else:d.update(home_goals=np.nan,away_goals=np.nan,actual_margin=np.nan,label_status='not_finished_at_asof' if kick>now else 'missing_or_conflicting_official_result')
        verified.append(d)
    events=finalize_snapshot_frame(pd.DataFrame(verified));events=events.rename(columns={'outer_line_median':'outer_primary_line'});events.to_csv(out/'events.csv',index=False)
    pairs=pd.read_csv(R/a.pairs);paired=pairs[pairs.time_aligned.astype(str).str.lower().eq('true')].match_id.nunique()
    quotes=[{'path':str(q.relative_to(R)),'sha256':hashlib.sha256(q.read_bytes()).hexdigest()} for q in sorted((R/'data/external/nowscore/snapshots').glob('*/quotes.csv'))]
    labelled=int(events.label_status.eq('official_completed_unique').sum())
    audit={'paired_input_events':int(paired),'same_market_feature_events':len(events),'official_labelled_events':labelled,'unlabelled_events':len(events)-labelled,'minimum_training_events':300,'min_training_events':300,'missing_labelled_feature_events_to_threshold':max(0,300-labelled),'development_training_ready':labelled>=300,'sample_unit':'unique_match_latest_safe_aligned_snapshot','events_with_observed_same_book_speed':int(events.observed_line_strength_per_hour.notna().sum()),'provider_reported_opening_timestamp_known':False,'provider_quote_update_age_known':False,'checkpoint_source':str(checkpoint.relative_to(R)),'checkpoint_sha256':hashlib.sha256(checkpoint.read_bytes()).hexdigest(),'recovered_from_own_failed_checkpoint':True,'official_archives_verified':len(integrity),'label_sources':sources,'nowscore_archive_sources':quotes,'skipped_events_without_complete_safe_checkpoint':int(paired)-len(events),'skip_detail_note':'Intermediate failure preceded final reject audit; events without a complete safe checkpoint excluded, never reconstructed as valid.','production_promotion_allowed':False,'historical_proxy_substituted_for_real_gap':False}
    audit['label_status_counts']={k:int(v) for k,v in events.label_status.value_counts().items()}
    audit['line_quote_aggregation']='modal primary line; probability prices pooled only on that same line'
    (out/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in audit.items() if k not in ['label_sources','nowscore_archive_sources']},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
