"""Export all dossiers; optionally fetch bounded, resumable source-ID profiles."""
import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from data.entity_archive import connect
from data.player_profiles import dossiers, import_profile
from data.api_football_daily_intelligence import _archive
from import_api_football_daily_intelligence import load_env
from world_cup.api_football_adapter import ApiFootballClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--max-requests", type=int, default=1)
    parser.add_argument("--reserve", type=int, default=30)
    args = parser.parse_args()
    if args.max_requests < 0 or args.reserve < 0:
        parser.error("limits must be nonnegative")
    db = connect(ROOT / "data/processed/entity_archive.sqlite3")
    failures = []
    requested = 0
    try:
        if args.fetch:
            load_env()
            client = ApiFootballClient(api_key=os.getenv("API_FOOTBALL_KEY", ""), timeout=25)
            status = client.get("status")
            quota = status.get("response", {}).get("requests", {})
            if status.get("errors") or "limit_day" not in quota or "current" not in quota:
                raise ValueError("Cannot establish quota; no profile requests sent")
            budget = min(args.max_requests, max(0, int(quota["limit_day"]) - int(quota["current"]) - args.reserve))
            for item in dossiers(db):
                if item["status"] != "profile_missing" or requested >= budget:
                    continue
                pid = item["provider_id"]
                time.sleep(6.3)
                now = datetime.now(timezone.utc)
                requested += 1
                try:
                    payload = client.get("players/profiles", {"player": pid})
                    path = Path(_archive(payload, ROOT / "data/player_level/profiles" / f"{now.strftime('%Y%m%dT%H%M%SZ')}_{pid}.json"))
                    import_profile(db, pid, payload, dict(observed_at=now.isoformat(), path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
                    headers = {k.lower(): v for k, v in client.last_headers.items()}
                    remaining = headers.get("x-ratelimit-requests-remaining")
                    if remaining is not None and int(remaining) <= args.reserve:
                        break
                except (RuntimeError, ValueError) as exc:
                    failures.append(dict(provider_id=pid, error=str(exc)))
                    break
        items = dossiers(db)
        output = ROOT / "artifacts/data/player_dossiers_latest.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        covered = sum(x["status"] == "profile_observed" for x in items)
        summary = dict(players=len(items), profiles=covered, pending_profiles=len(items)-covered,
            complete_core_fields=sum(not x["missing_fields"] for x in items),
            missing_fields=dict(Counter(key for x in items for key in x["missing_fields"])),
            requests=requested, failures=failures)
        output.write_text(json.dumps(dict(generated_at=datetime.now(timezone.utc).isoformat(), summary=summary, players=items), ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=True))
    finally:
        db.close()


if __name__ == "__main__":
    main()
