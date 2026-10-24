"""Quota-aware team roster collection. No network unless --fetch is supplied."""
import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from data.entity_archive import connect, identity
from data.team_squads import import_squad
from data.api_football_daily_intelligence import _archive
from import_api_football_daily_intelligence import load_env
from world_cup.api_football_adapter import ApiFootballClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--reserve", type=int, default=30)
    parser.add_argument("--max-requests", type=int, default=20)
    args = parser.parse_args()
    if min(args.reserve, args.max_requests) < 0:
        parser.error("limits must be nonnegative")
    teams = json.loads((ROOT / "config/api_football_identities.json").read_text(encoding="utf-8"))["teams"]
    db = connect(ROOT / "data/processed/entity_archive.sqlite3")
    failures, completed = [], []
    requested = 0
    quota = None
    try:
        pending = [t for t in teams if not db.execute("SELECT 1 FROM observations WHERE entity_id=? AND kind='squad_snapshot'", (identity("team",t["id"]),)).fetchone()]
        if args.fetch:
            load_env()
            client = ApiFootballClient(timeout=25)
            status = client.get("status")
            quota = status.get("response", {}).get("requests", {})
            if status.get("errors") or not {"limit_day", "current"} <= quota.keys():
                raise ValueError("quota unavailable")
            budget = min(args.max_requests, max(0, int(quota["limit_day"])-int(quota["current"])-args.reserve))
            for team in pending[:budget]:
                time.sleep(6.3)
                requested += 1
                now = datetime.now(timezone.utc)
                try:
                    payload = client.get("players/squads", {"team": team["id"]})
                    path = Path(_archive(payload, ROOT / "data/player_level/squads" / f"{now.strftime('%Y%m%dT%H%M%SZ')}_{team['id']}.json"))
                    count = import_squad(db, team["id"], payload, dict(path=str(path), observed_at=now.isoformat(), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
                    completed.append(dict(team_id=team["id"], players=count))
                    headers = {k.lower():v for k,v in client.last_headers.items()}
                    if int(headers.get("x-ratelimit-requests-remaining", args.reserve+1)) <= args.reserve:
                        break
                except (RuntimeError, ValueError) as exc:
                    failures.append(dict(team_id=team["id"], error=str(exc)))
                    break
        report = dict(generated_at=datetime.now(timezone.utc).isoformat(), quota=quota,
            requested=requested, completed=completed, failures=failures,
            pending_team_ids=[t["id"] for t in pending if t["id"] not in {c["team_id"] for c in completed}], reserve=args.reserve)
        path = ROOT / "artifacts/data/team_squads_latest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report))
    finally:
        db.close()


if __name__ == "__main__":
    main()
