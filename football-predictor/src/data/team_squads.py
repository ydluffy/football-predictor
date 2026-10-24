"""Archive provider roster snapshots without inferring transfer intervals."""
from datetime import datetime

from data.entity_archive import entity, identity, observe


def import_squad(db, team_id, payload, evidence):
    if datetime.fromisoformat(evidence["observed_at"]).tzinfo is None:
        raise ValueError("timezone required")
    rows = payload.get("response") or []
    if payload.get("errors") or len(rows) != 1:
        raise ValueError("missing or rejected squad")
    row = rows[0]
    if str(row.get("team", {}).get("id")) != str(team_id):
        raise ValueError("team identity mismatch")
    tid = identity("team", team_id)
    if not db.execute("SELECT 1 FROM entities WHERE id=?", (tid,)).fetchone():
        raise ValueError("team not in reviewed catalog")
    players = row.get("players") or []
    if not players:
        raise ValueError("empty squad is not evidence of departures")
    ids = [identity("player", p.get("id")) for p in players]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate player IDs")
    with db:
        for player in players:
            pid = entity(db, "player", player)
            observe(db, pid, "squad_observation", dict(team_id=tid,
                position=player.get("position"), number=player.get("number"),
                age_at_observation=player.get("age"), valid_from=None, valid_to=None), evidence)
        observe(db, tid, "squad_snapshot", {"player_ids": ids, "source_team_id": str(team_id)}, evidence)
    return len(ids)
