"""Record batch-scoped identity checks without approving global identity merges."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from data.api_football_prematch import build_api_football_match_mapping
from data.competition_registry import load_competition_registry, load_team_alias_registry
from data.entity_archive import connect, identity, observe
from world_cup.api_football_adapter import api_fixture_rows_to_frame


def verify(scan, rows):
    teams = load_team_alias_registry()
    competitions = load_competition_registry()
    mapping, audit = build_api_football_match_mapping(pd.DataFrame(scan["fixtures"]), api_fixture_rows_to_frame(rows))
    matches = {r["match_id"]: r for r in scan["fixtures"]}
    sources = {str(r["fixture"]["id"]): r for r in rows}
    if len(sources) != len(rows):
        raise ValueError("duplicate provider fixture IDs")
    bindings = {}
    reverse = {}
    for item in mapping.to_dict("records"):
        local = matches[item["match_id"]]
        source = sources[item["source_fixture_id"]]
        local_comp = competitions.resolve(local.get("competition"))
        provider_comp = competitions.resolve(source["league"]["name"])
        if local_comp is None or provider_comp is None or local_comp.competition_id != provider_comp.competition_id:
            raise ValueError("competition identity mismatch")
        pairs = [("competition", source["league"], local_comp.competition_id)]
        for side in ("home", "away"):
            canonical = teams.resolve(local[side + "_team"])
            if canonical is None or canonical != teams.resolve(source["teams"][side]["name"]):
                raise ValueError("team identity mismatch")
            pairs.append(("team", source["teams"][side], canonical))
        for kind, provider, canonical in pairs:
            key = (kind, str(provider["id"]))
            target = (kind, canonical)
            if key in bindings and bindings[key]["canonical"] != canonical:
                raise ValueError("provider identity collision")
            if target in reverse and reverse[target] != key:
                raise ValueError("canonical identity collision")
            reverse[target] = key
            bindings.setdefault(key, {"kind": kind, "provider_id": str(provider["id"]),
                "provider_name": provider["name"], "canonical": canonical, "match_ids": []})
            bindings[key]["match_ids"].append(item["match_id"])
    return {"scope": "archived_batch_name_id_competition_kickoff_consistency",
            "not_verified": ["gender", "age_group", "nationality", "cross_provider_merge"],
            "mapping_audit": audit, "bindings": list(bindings.values())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan-json", required=True)
    parser.add_argument("--audit-json", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    scan = json.loads(Path(args.scan_json).read_text(encoding="utf-8-sig"))
    audit = json.loads(Path(args.audit_json).read_text(encoding="utf-8-sig"))
    files = [Path(p) for p in audit["raw_files"] if "_fixtures_" in Path(p).name]
    rows = []
    evidence = []
    for path in files:
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest[:12] != path.stem.rsplit("_", 1)[1]:
            raise ValueError("archive digest mismatch")
        payload = json.loads(raw)
        if payload.get("errors"):
            raise ValueError("provider returned errors")
        rows.extend(payload["response"])
        evidence.append({"path": str(path.resolve()), "sha256": digest})
    result = verify(scan, rows)
    result["evidence"] = evidence
    result["scan_sha256"] = hashlib.sha256(Path(args.scan_json).read_bytes()).hexdigest()
    output = Path(args.output)
    if output.exists():
        raise ValueError("output must be new")
    db = connect(args.database)
    try:
        with db:
            for binding in result["bindings"]:
                eid = identity(binding["kind"], binding["provider_id"])
                observe(db, eid, "identity_batch_check", {**binding, "scope": result["scope"],
                    "not_verified": result["not_verified"], "evidence": evidence,
                    "scan_sha256": result["scan_sha256"]},
                    {"observed_at": audit["observed_at"], "path": str(Path(args.audit_json).resolve()),
                     "sha256": hashlib.sha256(Path(args.audit_json).read_bytes()).hexdigest()})
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"bindings": len(result["bindings"]), "mapped": result["mapping_audit"]["mapped_rows"],
                          "report": str(output)}, ensure_ascii=True))
    finally:
        db.close()


if __name__ == "__main__":
    main()
