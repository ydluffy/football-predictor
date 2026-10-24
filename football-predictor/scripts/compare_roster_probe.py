"""Offline candidate comparison; never merge provider IDs or write the catalog."""
import json
import sqlite3
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def normalize(text):
    text = unicodedata.normalize("NFKD", text or "")
    return " ".join("".join(c for c in text.casefold() if not unicodedata.combining(c)).split())


def main():
    data = json.loads((ROOT / "artifacts/data/roster_provider_probe_20261022.json").read_text(encoding="utf-8"))
    teams = data["samples"]["football_data_org"]
    rows = [p for t in teams for p in t["squad"]]
    db_path = ROOT / "data/processed/entity_archive.sqlite3"
    db = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
    try:
        local = db.execute("SELECT e.provider_id,e.name,o.payload FROM entities e JOIN observations o ON o.entity_id=e.id WHERE e.kind='player' AND o.kind='player_profile' ORDER BY o.observed_at DESC").fetchall()
    finally:
        db.close()
    candidates = []
    seen = set()
    for pid, name, value in local:
        if pid in seen:
            continue
        seen.add(pid)
        profile = json.loads(value)
        birth = (profile.get("birth") or {}).get("date")
        surname = normalize(profile.get("lastname"))
        for player in rows:
            if birth and surname and birth == player.get("dateOfBirth") and surname in normalize(player.get("name")).split():
                candidates.append(dict(api_football_id=pid, local_name=name,
                    football_data_org_id=player["id"], source_name=player["name"], birth_date=birth,
                    status="candidate_dob_surname_only_not_approved"))
    report = dict(team_count=len(teams), player_rows=len(rows), unique_player_ids=len({p["id"] for p in rows}),
        present_fields={key:sum(bool(p.get(key)) for p in rows) for key in ("id", "name", "position", "dateOfBirth", "nationality")},
        local_candidates=candidates, candidates_count=len(candidates), catalog_modified=False,
        limitation="One league snapshot is not proof of all-league access, completeness, freshness or sustained availability.")
    path = ROOT / "artifacts/data/roster_provider_comparison_20261022.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    main()
