import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from expand_football_data_rosters import aggregate


def test_same_provider_id_is_one_player_with_multiple_observations():
    team = {"id": 1, "name": "Club", "squad": [{"id": 2, "name": "Player"}]}
    result = aggregate([{"code": c, "observed_at": "2026-10-22T00:00:00Z", "teams": [team]} for c in ("PL", "CL")])
    assert result["summary"] == {"unique_teams": 1, "unique_players": 1, "player_observations": 2}
    assert result["teams"][0]["competitions"] == ["PL", "CL"]


def test_same_name_different_ids_are_not_merged():
    result = aggregate([{"code": "PL", "observed_at": "2026-10-22T00:00:00Z", "teams": [
        {"id": 1, "name": "Club", "squad": [{"id": i, "name": "Player"} for i in (2, 3)]}]}])
    assert result["summary"]["unique_players"] == 2
