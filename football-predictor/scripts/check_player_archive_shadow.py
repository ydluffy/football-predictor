"""Replay archived observations against unified dossiers without changing source data."""
import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from data.player_archive_shadow import attach


def main():
    parser = argparse.ArgumentParser(description="Replay archived player signals against unified dossiers.")
    parser.add_argument("--as-of", default="",
                        help="Fixed ISO-8601 cutoff for every row; default truncates each row at its own observed_at.")
    parser.add_argument("--output", default="artifacts/data/player_archive_shadow_latest.json")
    args = parser.parse_args()
    path = ROOT / "artifacts/data/unified_player_archive_latest.json"
    archive = json.loads(path.read_text(encoding="utf-8"))
    profiles = {p["api_id"]: p for p in archive["players"]}
    db = sqlite3.connect((ROOT / "data/processed/entity_archive.sqlite3").as_uri() + "?mode=ro", uri=True)
    try:
        entities = {eid: (provider, pid, kind) for eid, provider, pid, kind in db.execute("SELECT id,provider,provider_id,kind FROM entities")}
        def source_id(eid, kind):
            item = entities.get(eid)
            return item[1] if item and item[0] == "api_football" and item[2] == kind else None
        memberships = set()
        for eid, payload in db.execute("SELECT entity_id,payload FROM observations WHERE kind='membership_observation'"):
            p = json.loads(payload)
            memberships.add((source_id(eid, "player"), source_id(p.get("team_id"), "team"), source_id(p.get("fixture_id"), "fixture")))
        rows = []
        for oid, eid, kind, observed, evidence, payload in db.execute("SELECT id,entity_id,kind,observed_at,evidence,payload FROM observations WHERE kind IN ('absence','lineup')"):
            p = json.loads(payload)
            row = dict(observation_id=oid, signal_kind=kind, observed_at=observed, evidence=evidence,
                       source="api_football", source_player_id=source_id(eid, "player"),
                       source_team_id=source_id(p.get("team_id"), "team"),
                       source_fixture_id=source_id(p.get("fixture_id"), "fixture"))
            rows.append(attach(row, profiles, memberships, as_of=args.as_of or observed))
        withheld = Counter(item["field"] for row in rows for item in row.get("archive_withheld_fields") or [])
        summary = dict(rows=len(rows), signals=dict(Counter(r["signal_kind"] for r in rows)),
                       statuses=dict(Counter(r["archive_status"] for r in rows)),
                       linked_fields=sum(len(r["archive_fields"]) for r in rows if r["archive_status"] == "linked"),
                       withheld_fields=dict(withheld),
                       as_of_basis="fixed_cutoff" if args.as_of else "signal_observed_at")
        output = ROOT / args.output
        output.write_text(json.dumps(dict(summary=summary, production_enabled=False,
            validation_scope="in_sample_plumbing_only", archive_path=str(path), rows=rows), ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary))
    finally:
        db.close()


if __name__ == "__main__":
    main()
