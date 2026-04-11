from __future__ import annotations

import json

from config.settings import get_settings
from research_director.model_registry import get_current_production_model, load_registry, mark_production, register_candidate


def test_model_registry_register_candidate_and_mark_production(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    s = get_settings()

    assert get_current_production_model() is None

    c1 = register_candidate(
        model_type="lightgbm",
        feature_version="v3",
        calibration_method="none",
        artifact_path=str(root / "m1.pkl"),
        metrics_summary={"brier": 0.2},
        status="candidate",
        run_id="r1",
    )
    payload = json.loads(s.research_model_registry_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "model_registry_v2"
    assert payload["current_production_model"] is None
    assert len(payload["candidate_models"]) == 1

    prod = mark_production(model_id=c1.model_id)
    assert prod.status == "production"
    cur = get_current_production_model()
    assert cur is not None
    assert cur.model_id == c1.model_id


def test_model_registry_disallows_multiple_production(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    c1 = register_candidate(
        model_type="logit",
        feature_version="v3",
        calibration_method="none",
        artifact_path=str(root / "m1.pkl"),
        metrics_summary={},
        status="candidate",
        run_id="r1",
    )
    c2 = register_candidate(
        model_type="logit",
        feature_version="v3",
        calibration_method="none",
        artifact_path=str(root / "m2.pkl"),
        metrics_summary={},
        status="candidate",
        run_id="r2",
    )
    _ = mark_production(model_id=c1.model_id)
    _ = mark_production(model_id=c2.model_id)

    reg = load_registry()
    assert reg.current_production_model is not None
    assert reg.current_production_model.model_id == c2.model_id
    prod_in_candidates = [c for c in reg.candidate_models if c.status == "production"]
    assert prod_in_candidates == []
