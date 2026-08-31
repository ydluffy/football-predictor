from __future__ import annotations

import asyncio
from types import SimpleNamespace

from api import main as api_main


def test_lifespan_initializes_database_and_model(monkeypatch, tmp_path) -> None:
    calls: list[str] = []
    connection = SimpleNamespace(close=lambda: calls.append("close"))
    model = object()
    model_path = tmp_path / "baseline.pkl"
    logger = SimpleNamespace(
        info=lambda *args: None,
        warning=lambda *args: None,
    )

    monkeypatch.setattr(api_main, "ensure_project_dirs", lambda: calls.append("dirs"))
    monkeypatch.setattr(api_main, "configure_logger", lambda: calls.append("logger"))
    monkeypatch.setattr(api_main, "get_logger", lambda: logger)
    monkeypatch.setattr(api_main, "p0_db_connect", lambda: connection)
    monkeypatch.setattr(api_main, "p0_init_db", lambda conn: calls.append("db"))
    monkeypatch.setattr(api_main, "p0_get_db_path", lambda: tmp_path / "p0.sqlite")
    monkeypatch.setattr(api_main, "_load_or_train_model", lambda: (model, model_path))

    async def exercise_lifespan() -> None:
        async with api_main.lifespan(api_main.app):
            assert api_main._MODEL is model
            assert api_main._MODEL_PATH == model_path

    asyncio.run(exercise_lifespan())

    assert calls == ["dirs", "logger", "db", "close"]
