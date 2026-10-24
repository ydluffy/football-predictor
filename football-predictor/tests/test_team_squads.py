import pytest

from data.entity_archive import connect, entity
from data.team_squads import import_squad


def test_roster_is_snapshot_not_transfer_history(tmp_path):
    db = connect(tmp_path / "db.sqlite")
    with db:
        entity(db, "team", {"id": 1, "name": "Team"})
    evidence = dict(observed_at="2026-10-22T00:00:00+00:00", path="raw.json", sha256="hash")
    payload = {"response": [{"team": {"id": 1}, "players": [{"id": 2, "name": "Player", "number": 9}]}]}
    try:
        assert import_squad(db, 1, payload, evidence) == 1
        import_squad(db, 1, payload, evidence)
        assert db.execute("SELECT count(*) FROM observations").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM observations WHERE kind='membership_observation'").fetchone()[0] == 0
        for invalid in [{"errors": ["quota"]}, {"response": []}, {"response": [{"team": {"id": 99}, "players": payload["response"][0]["players"]}]}]:
            with pytest.raises(ValueError):
                import_squad(db, 1, invalid, evidence)
        assert db.execute("SELECT count(*) FROM observations").fetchone()[0] == 2
        payload["response"][0]["players"].append({"id": 3, "name": ""})
        with pytest.raises(ValueError):
            import_squad(db, 1, payload, evidence)
        assert db.execute("SELECT count(*) FROM entities WHERE kind='player'").fetchone()[0] == 1
    finally:
        db.close()
