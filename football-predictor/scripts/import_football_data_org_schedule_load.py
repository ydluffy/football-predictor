from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "src"))
from data.api_football_prematch import append_validated_prematch_intelligence
from data.schedule_load_intelligence import build_schedule_load_intelligence
from world_cup.api_football_adapter import api_fixture_rows_to_frame
from world_cup.football_data_org_adapter import FootballDataOrgClient


def p(value: str) -> Path:
    x=Path(value); return x if x.is_absolute() else ROOT/x


def env() -> None:
    f=ROOT/".env"
    if not f.exists(): return
    for raw in f.read_text(encoding="utf-8-sig").splitlines():
        if raw.strip() and not raw.lstrip().startswith("#") and "=" in raw:
            k,v=raw.split("=",1); os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))


def main() -> None:
    ap=argparse.ArgumentParser(description="Import football-data.org seven-day schedule load for mapped Sporttery fixtures.")
    ap.add_argument("--scan-json",required=True); ap.add_argument("--date",required=True); ap.add_argument("--observed-at",default="")
    ap.add_argument("--raw-root",default="data/external/football_data_org_schedule_load/raw")
    ap.add_argument("--manual-output",default="data/manual/prematch_intelligence.csv")
    ap.add_argument("--validated-output",default="data/processed/prematch_intelligence_validated.csv")
    ap.add_argument("--audit-output",default="artifacts/data/football_data_org_schedule_load_latest.json")
    args=ap.parse_args(); env(); observed=args.observed_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    start=(pd.Timestamp(args.date)-timedelta(days=7)).date().isoformat(); end=(pd.Timestamp(args.date)+timedelta(days=2)).date().isoformat()
    client=FootballDataOrgClient(api_token=os.getenv("FOOTBALL_DATA_TOKEN","")); payload=client.get("matches",{"dateFrom":start,"dateTo":end})
    content=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode(); digest=hashlib.sha256(content).hexdigest()
    raw=p(args.raw_root)/args.date/f"matches_{digest[:12]}.json"; raw.parent.mkdir(parents=True,exist_ok=True)
    if not raw.exists(): raw.write_bytes(content)
    rows=[]
    for item in payload.get("matches") or []:
        fixture=item.get("id"); comp=item.get("competition") or {}; home=item.get("homeTeam") or {}; away=item.get("awayTeam") or {}
        rows.append({"source_fixture_id":str(fixture or ""),"kickoff_time":item.get("utcDate",""),
                     "home_team":home.get("name",home.get("shortName","")),"away_team":away.get("name",away.get("shortName","")),
                     "status":item.get("status",""),"competition_code":comp.get("code","")})
    external=pd.DataFrame(rows,columns=["source_fixture_id","kickoff_time","home_team","away_team","status","competition_code"])
    scan=json.loads(p(args.scan_json).read_text(encoding="utf-8-sig")); intelligence,mapping,audit=build_schedule_load_intelligence(
        scan_fixtures=pd.DataFrame(scan.get("fixtures") or []),external_matches=external,observed_at=observed,
        source="football_data_org",source_url="https://api.football-data.org/v4/matches")
    audit.update({"status":"ok","date_from":start,"date_to":end,"raw_file":str(raw.resolve()),
                  "write":append_validated_prematch_intelligence(intelligence,manual_path=p(args.manual_output),validated_path=p(args.validated_output))})
    out=p(args.audit_output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(audit,ensure_ascii=False,indent=2))


if __name__=="__main__":main()
