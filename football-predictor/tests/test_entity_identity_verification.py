import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("identity_check", Path(__file__).resolve().parents[1] / "scripts/verify_entity_identities.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def inputs():
    scan = {"fixtures": [{"match_id": "test", "competition_id": "UNKNOWN", "competition": "解放者杯",
        "kickoff": "2026-10-22T08:30:00+08:00", "home_team": "帕梅拉斯", "away_team": "弗鲁米嫩"}]}
    rows = [{"fixture": {"id": 1640021, "date": "2026-10-22T08:30:00+08:00", "status": {"short": "NS"}},
        "league": {"id": 13, "name": "CONMEBOL Libertadores", "season": 2026},
        "teams": {"home": {"id": 121, "name": "Palmeiras"}, "away": {"id": 124, "name": "Fluminense"}}}]
    return scan, rows


def test_scoped_identity_check():
    scan, rows = inputs()
    result = module.verify(scan, rows)
    assert len(result["bindings"]) == 3
    assert result["bindings"][0]["canonical"] == "CONMEBOL_LIBERTADORES"
    assert "gender" in result["not_verified"]


def test_wrong_competition_not_approved():
    scan, rows = inputs()
    rows[0]["league"]["name"] = "La Liga"
    with pytest.raises(ValueError, match="competition identity mismatch"):
        module.verify(scan, rows)


def test_duplicate_provider_fixture_rejected():
    scan, rows = inputs()
    with pytest.raises(ValueError, match="duplicate provider"):
        module.verify(scan, rows + rows)
