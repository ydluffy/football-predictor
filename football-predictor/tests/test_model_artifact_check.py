from __future__ import annotations

import json

from config.settings import get_settings
from models.artifact_check import check_model_artifact
from models.artifact_manifest import build_manifest


def test_check_model_artifact_warns_when_manifest_missing(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    s = get_settings()

    model_path = s.logit_model_path
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text("x", encoding="utf-8")

    res = check_model_artifact(artifact_path=model_path)
    assert res.status == "warning"
    assert "manifest_missing" in res.warnings


def test_check_model_artifact_incompatible_when_python_mismatch(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    s = get_settings()

    model_path = s.logit_model_path
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text("x", encoding="utf-8")

    manifest = build_manifest(model_type="logit", feature_version="v3", calibration_method="none", artifact_path=model_path)
    payload = json.loads(manifest.model_dump_json())
    payload["python_version"] = "0.0.0"
    s.logit_model_manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    res = check_model_artifact(artifact_path=model_path, manifest_path=s.logit_model_manifest_path)
    assert res.status == "incompatible"
