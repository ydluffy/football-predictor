"""Build usable, provenance-bearing dossiers from existing data, without network calls."""
import json
import sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from data.entity_archive import connect
from data.player_profiles import dossiers
from data.unified_player_archive import assemble


def main():
    run = json.loads((ROOT / "artifacts/data/football_data_expansion_latest.json").read_text(encoding="utf-8"))
    catalog = json.loads(Path(run["catalog"]).read_text(encoding="utf-8"))
    comparison = json.loads((ROOT / "artifacts/data/football_data_identity_comparison_latest.json").read_text(encoding="utf-8"))
    teams = {t["entity_id"]: t["candidates"][0]["id"] for t in comparison["teams"] if t["status"] == "unique_alias_candidate"}
    db = connect(ROOT / "data/processed/entity_archive.sqlite3")
    try:
        players = []
        for p in dossiers(db):
            expected = {teams[o["data"]["team_id"]] for o in p["observations"]
                        if o["kind"] in ("membership_observation", "squad_observation") and o["data"].get("team_id") in teams}
            players.append(assemble(p, catalog["players"], expected))
        summary = dict(players=len(players), with_birth=sum("birth_date" in p["fields"] for p in players),
            with_position=sum("position" in p["fields"] for p in players),
            bindings=dict(Counter(p["binding"]["basis"] if p["binding"] else "not_bound" for p in players)),
            missing_fields=dict(Counter(f for p in players for f in p["missing_fields"])))
        output = ROOT / "artifacts/data/unified_player_archive_latest.json"
        output.write_text(json.dumps(dict(summary=summary, source_catalog=run["catalog"],
            production_enabled=False, players=players), ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary))
    finally:
        db.close()


if __name__ == "__main__":
    main()
