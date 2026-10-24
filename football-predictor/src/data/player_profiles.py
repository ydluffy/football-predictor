"""Source-ID profile enrichment; current observations never rewrite match history."""
import json
from datetime import datetime

from data.entity_archive import observe, review


def import_profile(db, provider_id, payload, evidence):
    if datetime.fromisoformat(evidence["observed_at"]).tzinfo is None:
        raise ValueError("timezone required")
    if payload.get("errors"):
        raise ValueError("provider rejected request")
    rows = payload.get("response") or []
    if len(rows) != 1:
        raise ValueError("expected exactly one player profile")
    player = rows[0].get("player") or {}
    if str(player.get("id")) != str(provider_id):
        raise ValueError("player ID mismatch")
    entity = db.execute("SELECT id,name FROM entities WHERE kind='player' AND provider='api_football' AND provider_id=?", (str(provider_id),)).fetchone()
    if entity is None:
        raise ValueError("unknown player ID")
    fields = {key: player.get(key) for key in ("name", "firstname", "lastname", "birth", "nationality", "height", "weight", "photo")}
    birth = (fields.get("birth") or {}).get("date")
    if birth:
        datetime.strptime(birth, "%Y-%m-%d")
    with db:
        for (old,) in db.execute("SELECT payload FROM observations WHERE entity_id=? AND kind='player_profile'", (entity[0],)):
            previous = json.loads(old)
            if previous.get("birth") and fields.get("birth") and previous["birth"] != fields["birth"]:
                review(db, entity[0], "profile_birth_conflict", {"previous": previous["birth"], "incoming": fields["birth"]})
        observe(db, entity[0], "player_profile", fields, evidence)
    return fields


def dossiers(db):
    result = []
    references = {eid: dict(provider_id=pid, name=name, kind=kind) for eid,pid,name,kind in db.execute("SELECT id,provider_id,name,kind FROM entities")}
    for eid, pid, name in db.execute("SELECT id,provider_id,name FROM entities WHERE kind='player' ORDER BY CAST(provider_id AS INTEGER)"):
        observations = [dict(kind=k, observed_at=t, evidence=e, sha256=h, data=json.loads(p)) for k,t,e,h,p in db.execute(
            "SELECT kind,observed_at,evidence,sha256,payload FROM observations WHERE entity_id=? ORDER BY observed_at,id", (eid,))]
        profiles = [o for o in observations if o["kind"] == "player_profile"]
        for observation in observations:
            data = observation["data"]
            observation["references"] = {key: references.get(data[key]) for key in ("team_id", "fixture_id") if data.get(key)}
        latest = profiles[-1]["data"] if profiles else {}
        missing = [key for key in ("firstname", "lastname", "nationality", "height", "weight") if not latest.get(key)]
        if not (latest.get("birth") or {}).get("date"):
            missing.append("birth.date")
        conflicts = db.execute("SELECT reason FROM reviews WHERE entity_id=? AND status='pending' AND reason IN ('profile_birth_conflict', 'profile_field_conflict')", (eid,)).fetchall()
        result.append(dict(entity_id=eid, provider_id=pid, name=name, profile=latest,
            missing_fields=missing, observations=observations,
            review_required=bool(conflicts), conflicts=[r[0] for r in conflicts],
            status="profile_observed" if profiles else "profile_missing"))
    return result
