"""Compare the full source catalog with local entities; optionally retain corroboration."""
import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from data.entity_archive import connect, observe
from data.player_profiles import dossiers
from data.competition_registry import load_team_alias_registry, normalize_alias
from data.roster_identity_comparison import classify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-corroboration", action="store_true")
    args = parser.parse_args()
    run = json.loads((ROOT / "artifacts/data/football_data_expansion_latest.json").read_text(encoding="utf-8"))
    path = Path(run["catalog"])
    content = path.read_bytes()
    source = json.loads(content)
    aliases = load_team_alias_registry()
    def key(name):
        return normalize_alias(aliases.resolve(name) or name)
    db = connect(ROOT / "data/processed/entity_archive.sqlite3")
    try:
        teams = []
        for eid,pid,name in db.execute("SELECT id,provider_id,name FROM entities WHERE kind='team' AND provider='api_football'"):
            matches = [t for t in source["teams"] if key(t["name"]) == key(name)]
            teams.append(dict(entity_id=eid, api_id=pid, name=name, candidates=matches,
                status="unique_alias_candidate" if len(matches)==1 else "ambiguous" if matches else "unresolved"))
        team_links = {t["entity_id"]: t["candidates"][0]["id"] for t in teams if t["status"]=="unique_alias_candidate"}
        players = []
        for local in dossiers(db):
            local_teams = {o["data"].get("team_id") for o in local["observations"] if o["kind"] in ("membership_observation", "squad_observation")}
            expected = {team_links[t] for t in local_teams if t in team_links}
            candidates = []
            for external in source["players"]:
                state = classify(local["name"], local["profile"], external)
                if state:
                    candidates.append(dict(source_id=external["id"], status=state,
                        team_agrees=bool(expected & {o["team_id"] for o in external["observations"]}),
                        source_names=sorted({o["profile"]["name"] for o in external["observations"]})))
            agreed = [c for c in candidates if c["status"]=="name_and_birth_agree" and c["team_agrees"]]
            status = "corroborated_candidate" if len(agreed)==1 and len(candidates)==1 and not local["review_required"] else "review_required" if candidates else "no_candidate"
            players.append(dict(entity_id=local["entity_id"], api_id=local["provider_id"], name=local["name"], status=status, candidates=candidates))
        if args.record_corroboration:
            with db:
                for p in players:
                    if p["status"] != "corroborated_candidate":
                        continue
                    external = next(x for x in source["players"] if x["id"] == p["candidates"][0]["source_id"])
                    observed = max(o["observed_at"] for o in external["observations"])
                    observe(db, p["entity_id"], "cross_provider_corroboration", {
                        "provider": "football_data_org", "source_id": external["id"],
                        "basis": "compatible_name_exact_birth_and_alias_team", "binding_approved": False,
                        "profiles": external["observations"]},
                        dict(observed_at=observed, path=str(path), sha256=hashlib.sha256(content).hexdigest()))
        report = dict(team_status=dict(Counter(t["status"] for t in teams)),
            player_status=dict(Counter(p["status"] for p in players)), teams=teams, players=players,
            identities_merged=0, existing_profiles_overwritten=0, corroboration_recorded=args.record_corroboration)
        out = ROOT / "artifacts/data/football_data_identity_comparison_latest.json"
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({k:v for k,v in report.items() if k not in ("teams", "players")}))
    finally:
        db.close()


if __name__ == "__main__":
    main()
