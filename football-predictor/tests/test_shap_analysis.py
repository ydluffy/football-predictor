from __future__ import annotations

import pandas as pd

from config.settings import get_settings
import evaluate.shap_analysis as shap_analysis


def test_try_build_shap_summary_fallback_when_shap_missing(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    def _raise():
        raise ImportError("shap 不可用：跳过 SHAP 分析")

    monkeypatch.setattr(shap_analysis, "build_shap_summary", lambda model, X: _raise())

    X = pd.DataFrame({"a": [1.0, 2.0], "b": [0.5, 0.25]})
    out = shap_analysis.try_build_shap_summary(object(), X)
    assert out is None
    assert not settings.eval_lightgbm_shap_summary_path.exists()
