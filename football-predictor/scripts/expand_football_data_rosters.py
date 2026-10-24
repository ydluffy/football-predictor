"""Bounded multi-competition roster snapshots, deduplicated within the provider."""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from import_api_football_daily_intelligence import load_env
from probe_roster_providers import get

ROOT = Path(__file__).resolve().parents[1]
CODES = ("PL", "PD", "CL", "SA", "FL1", "DED", "PPL", "BSA", "CLI")


def aggregate(snapshots):
    teams, players = {}, {}
    for snapshot in snapshots:
        for team in snapshot.get("teams") or []:
            tid = str(team["id"])
            teams.setdefault(tid, {"id": tid, "name": team["name"], "competitions": []})
            if snapshot["code"] not in teams[tid]["competitions"]:
                teams[tid]["competitions"].append(snapshot["code"])
            for person in team.get("squad") or []:
                pid = str(person["id"])
                item = players.setdefault(pid, {"id": pid, "observations": []})
                item["observations"].append({"team_id": tid, "competition": snapshot["code"],
                    "observed_at": snapshot["observed_at"], "profile": person})
    return {"provider": "football_data_org", "teams": list(teams.values()), "players": list(players.values()),
            "summary": {"unique_teams": len(teams), "unique_players": len(players),
                        "player_observations": sum(len(p["observations"]) for p in players.values())}}


def main():
    load_env()
    token = next((os.getenv(k) for k in ("FOOTBALL_DATA_TOKEN", "FOOTBALL_DATA_API_KEY", "FOOTBALLDATA_API_KEY") if os.getenv(k)), None)
    if not token:
        raise SystemExit("football-data.org credential missing")
    root = ROOT / "data/player_level/football_data_org"
    root.mkdir(parents=True, exist_ok=True)
    run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshots, checks = [], []
    # Retain the already checked Bundesliga sample without spending another call.
    prior = ROOT / "artifacts/data/roster_provider_probe_20261022.json"
    if prior.exists():
        data = json.loads(prior.read_text(encoding="utf-8"))
        snapshots.append({"code": "BL1", "observed_at": data["audit"]["checked_at"], "teams": data["samples"]["football_data_org"]})
    for code in CODES:
        time.sleep(6.5)
        meta, payload = get(f"https://api.football-data.org/v4/competitions/{code}/teams", {"X-Auth-Token": token})
        observed = datetime.now(timezone.utc).isoformat()
        check = {"code": code, **meta, "observed_at": observed}
        checks.append(check)
        if meta["http_status"] in (401, 429) or meta["http_status"] is None:
            break
        if meta["http_status"] != 200:
            continue
        teams = [{"id": t["id"], "name": t["name"], "lastUpdated": t.get("lastUpdated"),
                  "squad": [{k:p.get(k) for k in ("id", "name", "position", "dateOfBirth", "nationality")} for p in t.get("squad") or []]}
                 for t in payload.get("teams") or []]
        snapshot = {"code": code, "observed_at": observed, "season": payload.get("season"), "teams": teams}
        path = root / f"{run}_{code}.json"
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        snapshots.append(snapshot)
        check.update(teams=len(teams), player_rows=sum(len(t["squad"]) for t in teams), snapshot=str(path))
        print(json.dumps(check), flush=True)
    catalog = aggregate(snapshots)
    (root / f"{run}_catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {"checks": checks, "summary": catalog["summary"], "catalog": str(root / f"{run}_catalog.json"),
              "production_identity_merges": 0, "billing_plan_verified": False}
    (ROOT / "artifacts/data/football_data_expansion_latest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
