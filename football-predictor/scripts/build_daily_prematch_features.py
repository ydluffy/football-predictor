from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"src"))
from data.prematch_intelligence import build_prematch_intelligence_features


def p(value:str)->Path:
    x=Path(value);return x if x.is_absolute() else ROOT/x


def main()->None:
    ap=argparse.ArgumentParser(description="Build time-safe per-fixture prematch features for a Sporttery scan.")
    ap.add_argument("--scan-json",required=True);ap.add_argument("--analysis-at",default="")
    ap.add_argument("--intelligence",default="data/processed/prematch_intelligence_validated.csv")
    ap.add_argument("--output",default="artifacts/data/daily_prematch_features_latest.csv")
    ap.add_argument("--audit-output",default="artifacts/data/daily_prematch_features_latest.json")
    args=ap.parse_args();analysis=pd.Timestamp(args.analysis_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat())
    if analysis.tzinfo is None:raise SystemExit("--analysis-at must be timezone-aware")
    payload=json.loads(p(args.scan_json).read_text(encoding="utf-8-sig"));fixtures=pd.DataFrame(payload.get("fixtures") or [])
    fixtures=fixtures.rename(columns={"kickoff":"kickoff_at"});fixtures["kickoff_at"]=pd.to_datetime(fixtures["kickoff_at"],errors="coerce",utc=True)
    fixtures=fixtures[fixtures["kickoff_at"].gt(analysis.tz_convert("UTC"))].copy();fixtures["analysis_at"]=analysis.isoformat()
    intelligence=pd.read_csv(p(args.intelligence),low_memory=False)
    if fixtures.empty:
        features=pd.DataFrame(index=fixtures.index);audit={"fixture_rows":0,"fixtures_with_intelligence":0}
    else:
        features,audit=build_prematch_intelligence_features(fixtures,intelligence)
    identity=fixtures[[column for column in ["match_id","match_number","competition_id","kickoff_at","home_team","away_team"] if column in fixtures]].reset_index(drop=True)
    result=pd.concat([identity,features.reset_index(drop=True)],axis=1)
    out=p(args.output);out.parent.mkdir(parents=True,exist_ok=True);result.to_csv(out,index=False,encoding="utf-8-sig")
    audit.update({"analysis_at":analysis.isoformat(),"output":str(out.resolve()),
                  "absence_available_matches":int(result.get("absence_data_available",pd.Series(dtype=float)).sum()),
                  "both_lineups_confirmed_matches":int(result.get("both_lineups_confirmed",pd.Series(dtype=float)).sum()),
                  "schedule_available_matches":int(result.get("cross_comp_schedule_available",pd.Series(dtype=float)).sum()),
                  "production_probability_change_allowed":False,"stake_increase_allowed":False})
    audit_out=p(args.audit_output);audit_out.parent.mkdir(parents=True,exist_ok=True);audit_out.write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(audit,ensure_ascii=False,indent=2))


if __name__=="__main__":main()
