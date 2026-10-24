"""Retain manually checked official facts without replacing provider profiles."""
from datetime import date
from urllib.parse import urlparse

from data.entity_archive import observe, review
from data.player_profiles import dossiers


def import_official_evidence(db, rows, evidence):
    local = {p["provider_id"]: p for p in dossiers(db)}
    prepared = []
    for row in rows:
        player = local.get(row["api_id"])
        if player is None or player["name"] != row["local_name"]:
            raise ValueError("local identity mismatch")
        teams = {o["references"]["team_id"]["name"] for o in player["observations"]
                 if o["references"].get("team_id")}
        if row["team"] not in teams:
            raise ValueError("observed team mismatch")
        if urlparse(row["url"]).scheme != "https" or not urlparse(row["url"]).hostname:
            raise ValueError("HTTPS evidence URL required")
        date.fromisoformat(row["birth_date"])
        if not row["name"] or not row["association_basis"]:
            raise ValueError("name and association basis required")
        prepared.append((player["entity_id"], dict(row, binding_approved=False)))
    with db:
        for eid, payload in prepared:
            observe(db, eid, "official_profile_candidate", payload, evidence)
            review(db, eid, "official_profile_association", payload)
    return len(prepared)
