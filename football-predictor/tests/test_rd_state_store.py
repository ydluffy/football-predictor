from __future__ import annotations

from config.settings import get_settings
from research_director.state_store import ResearchStateStore


def test_research_state_store_creates_db(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    store = ResearchStateStore()
    assert store.db_path.exists()
