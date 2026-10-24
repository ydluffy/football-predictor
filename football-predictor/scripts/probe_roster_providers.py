"""Bounded read-only access checks; never export credentials or account details."""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from import_api_football_daily_intelligence import load_env

ROOT = Path(__file__).resolve().parents[1]


def get(url, headers=None):
    try:
        response = requests.get(url, headers=headers or {}, timeout=25, allow_redirects=False)
        meta = {"http_status": response.status_code, "limits": {
            k: v for k, v in response.headers.items()
            if k.lower() in {"x-requests-available-minute", "x-requestcounter-reset", "x-authenticated-client", "retry-after"}
            and k.lower() != "x-authenticated-client"}}
        if response.status_code != 200:
            return meta, {}
        return meta, response.json()
    except (requests.RequestException, ValueError):
        return {"http_status": None, "error": "transport_or_json_failure"}, {}


def main():
    load_env()
    token = next((os.getenv(k) for k in ("FOOTBALL_DATA_TOKEN", "FOOTBALL_DATA_API_KEY", "FOOTBALLDATA_API_KEY") if os.getenv(k)), None)
    audit = {"checked_at": datetime.now(timezone.utc).isoformat(), "credentials_persisted": False,
             "football_data_org": {"configured": bool(token)}, "thesportsdb": {"credential": "public_demo_key"}}
    sample = {"football_data_org": [], "thesportsdb": []}
    fd = audit["football_data_org"]
    if token:
        headers = {"X-Auth-Token": token}
        meta, payload = get("https://api.football-data.org/v4/competitions", headers)
        fd["competitions"] = {**meta, "rows": len(payload.get("competitions") or []),
            "available": [{k: x.get(k) for k in ("code", "name", "plan")} for x in payload.get("competitions") or []]}
        if meta["http_status"] == 200:
            time.sleep(6.5)
            meta, payload = get("https://api.football-data.org/v4/competitions/BL1/teams", headers)
            teams = payload.get("teams") or []
            fd["bundesliga_teams"] = {**meta, "teams": len(teams), "season": payload.get("season"),
                "squad_players": sum(len(t.get("squad") or []) for t in teams),
                "teams_with_squads": sum(bool(t.get("squad")) for t in teams)}
            for team in teams:
                sample["football_data_org"].append({"id": team.get("id"), "name": team.get("name"),
                    "lastUpdated": team.get("lastUpdated"), "squad": [{k:p.get(k) for k in ("id", "name", "position", "dateOfBirth", "nationality")} for p in team.get("squad") or []]})
            if meta["http_status"] == 200:
                time.sleep(6.5)
                meta, payload = get("https://api.football-data.org/v4/competitions/BL1/standings", headers)
                fd["bundesliga_standings"] = {**meta, "tables": len(payload.get("standings") or [])}
    ts = audit["thesportsdb"]
    meta, payload = get("https://www.thesportsdb.com/api/v1/json/123/searchteams.php?t=Arsenal")
    teams = payload.get("teams") or []
    ts["team_search"] = {**meta, "teams": len(teams)}
    if teams and meta["http_status"] == 200:
        team = teams[0]
        tid = str(team.get("idTeam", ""))
        if tid.isdigit():
            time.sleep(1)
            meta, payload = get(f"https://www.thesportsdb.com/api/v1/json/123/lookup_all_players.php?id={tid}")
            players = payload.get("player") or payload.get("players") or []
            ts["squad"] = {**meta, "team_id": tid, "team_name": team.get("strTeam"),
                "returned_players": len(players), "documented_free_limit": 10,
                "complete_roster_verified": False}
            sample["thesportsdb"] = [{k:p.get(k) for k in ("idPlayer", "strPlayer", "idTeam", "strPosition", "dateBorn", "strNationality", "strHeight")} for p in players]
    output = ROOT / "artifacts/data/roster_provider_probe_20261022.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"audit": audit, "samples": sample}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=True))


if __name__ == "__main__":
    main()
