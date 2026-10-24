import pytest

from data.entity_archive import connect, entity
from data.player_profiles import dossiers, import_profile


def setup(tmp_path):
    db = connect(tmp_path / "players.sqlite3")
    with db:
        entity(db, "player", {"id": 1, "name": "A. Player"})
        entity(db, "player", {"id": 2, "name": "A. Player"})
    evidence = dict(observed_at="2026-10-22T01:00:00+00:00", path="archive.json", sha256="test")
    payload = dict(response=[dict(player=dict(id=1, name="A. Player", birth=dict(date="1995-01-02"), nationality="France"))])
    return db, evidence, payload


def test_profiles_are_id_scoped_and_idempotent(tmp_path):
    db, evidence, payload = setup(tmp_path)
    try:
        import_profile(db, 1, payload, evidence)
        import_profile(db, 1, payload, evidence)
        items = dossiers(db)
        assert items[0]["status"] == "profile_observed"
        assert items[1]["status"] == "profile_missing"
        assert "height" in items[0]["missing_fields"]
        assert len(items[0]["observations"]) == 1
        assert db.execute("SELECT count(*) FROM observations WHERE kind='membership_observation'").fetchone()[0] == 0
    finally:
        db.close()


@pytest.mark.parametrize("change", ["id", "errors", "empty", "birth", "timezone"])
def test_invalid_response_cannot_enrich_another_player(tmp_path, change):
    db, evidence, payload = setup(tmp_path)
    if change == "id":
        payload["response"][0]["player"]["id"] = 2
    elif change == "errors":
        payload["errors"] = {"quota": "exhausted"}
    elif change == "empty":
        payload["response"] = []
    elif change == "birth":
        payload["response"][0]["player"]["birth"]["date"] = "invalid"
    else:
        evidence["observed_at"] = "2026-10-22T01:00:00"
    try:
        with pytest.raises(ValueError):
            import_profile(db, 1, payload, evidence)
        assert db.execute("SELECT count(*) FROM observations").fetchone()[0] == 0
    finally:
        db.close()


def test_birth_conflict_preserves_history_and_opens_review(tmp_path):
    db, evidence, payload = setup(tmp_path)
    try:
        import_profile(db, 1, payload, evidence)
        payload["response"][0]["player"]["birth"]["date"] = "1996-01-02"
        import_profile(db, 1, payload, {**evidence, "observed_at": "2026-10-23T01:00:00+00:00"})
        assert db.execute("SELECT count(*) FROM observations").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM reviews WHERE reason='profile_birth_conflict'").fetchone()[0] == 1
        assert dossiers(db)[0]["review_required"] is True
    finally:
        db.close()
