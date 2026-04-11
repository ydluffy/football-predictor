from __future__ import annotations

import json

import pytest

from config.settings import get_settings
from models.artifact_manifest import ModelArtifactLoadError, build_manifest
from models.model_factory import load_model


def test_model_manifest_env_mismatch_blocks_load(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    s = get_settings()

    model_path = s.lightgbm_model_path
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text("x", encoding="utf-8")

    manifest = build_manifest(model_type="lightgbm", feature_version="v3", calibration_method="none", artifact_path=model_path)
    payload = json.loads(manifest.model_dump_json())
    payload["python_version"] = "0.0.0"
    s.lightgbm_model_manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with pytest.raises(ModelArtifactLoadError) as ei:
        _ = load_model("lightgbm", model_path)
    assert ei.value.code == "env_mismatch"


def test_model_load_error_is_structured_for_numpy_core(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    s = get_settings()

    model_path = s.lightgbm_model_path
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text("x", encoding="utf-8")

    monkeypatch.setattr("models.model_factory.load_lightgbm_model", lambda p: (_ for _ in ()).throw(ModuleNotFoundError("No module named 'numpy._core'")))

    with pytest.raises(ModelArtifactLoadError) as ei:
        _ = load_model("lightgbm", model_path)
    assert ei.value.code == "numpy_pickle_incompatible"
    assert "artifact_path" in ei.value.details
