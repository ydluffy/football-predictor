"""Export every gap and source candidate without promoting any identity binding."""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from data.entity_archive import connect
from data.player_profiles import dossiers


def main():
    comparison = json.loads((ROOT / "artifacts/data/football_data_identity_comparison_latest.json").read_text(encoding="utf-8"))
    matches = {p["api_id"]: p for p in comparison["players"]}
    run = json.loads((ROOT / "artifacts/data/football_data_expansion_latest.json").read_text(encoding="utf-8"))
    catalog = json.loads(Path(run["catalog"]).read_text(encoding="utf-8"))
    external = {p["id"]: p for p in catalog["players"]}
    db = connect(ROOT / "data/processed/entity_archive.sqlite3")
    try:
        rows = []
        for p in dossiers(db):
            match = matches.get(p["provider_id"], {})
            official = [o for o in p["observations"] if o["kind"] == "official_profile_candidate"]
            rows.append({"api_id": p["provider_id"], "name": p["name"],
                "missing_fields": p["missing_fields"], "local_conflicts": p["conflicts"],
                "matching_status": match.get("status", "not_compared"),
                "official_evidence": official,
                "source_candidates": [dict(c, observations=external[c["source_id"]]["observations"])
                                      for c in match.get("candidates", [])],
                "binding_approved": False,
                "next_action": "review_official_association" if official else
                    "fetch_source_id_profile_when_quota_allows" if p["status"] == "profile_missing" else
                    "resolve_conflict" if p["review_required"] else
                    "verify_name_or_source_coverage" if match.get("status") == "no_candidate" else
                    "review_cross_provider_candidate"})
        summary = {"players": len(rows), "missing_birth": sum("birth.date" in r["missing_fields"] for r in rows),
                   "with_official_evidence": sum(bool(r["official_evidence"]) for r in rows),
                   "actions": dict(Counter(r["next_action"] for r in rows))}
        out = ROOT / "artifacts/data/player_enrichment_queue_latest.json"
        out.write_text(json.dumps({"summary": summary, "catalog_evidence": run["catalog"], "players": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary))
    finally:
        db.close()


if __name__ == "__main__":
    main()
