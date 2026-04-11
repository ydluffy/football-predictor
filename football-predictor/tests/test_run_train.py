from __future__ import annotations

import importlib.util
import pandas as pd
import pytest

from config.settings import get_settings


def _load_run_train_main():
    root = __file__
    from pathlib import Path

    script_path = Path(root).resolve().parents[1] / "scripts" / "run_train.py"
    spec = importlib.util.spec_from_file_location("run_train_script", str(script_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 scripts/run_train.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


def test_run_train_cv_true_stacking_oof_explicitly_raises(monkeypatch):
    main = _load_run_train_main()
    monkeypatch.setattr("sys.argv", ["run_train.py", "--model-type", "stacking_oof", "--cv", "true"])
    with pytest.raises(ValueError) as e:
        main()
    assert "cv=true 暂不支持 stacking/stacking_oof" in str(e.value)


def test_run_train_use_verifier_true_writes_results(monkeypatch, tmp_path):
    main = _load_run_train_main()
    root = tmp_path / "football-predictor"
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(
        {
            "match_id": ["m1", "m2", "m3", "m4", "m5"],
            "date": pd.date_range("2025-01-01", periods=5, freq="D").astype(str),
            "league": ["EPL", "EPL", "EPL", "LaLiga", "LaLiga"],
            "odds_home": [1.9, 2.1, 1.8, 2.5, 3.2],
            "odds_draw": [3.2, 3.0, 3.4, 3.1, 3.0],
            "odds_away": [4.1, 3.7, 4.5, 2.9, 2.3],
            "injury_flag": [0, 1, 0, 0, 1],
            "line_move": [0.0, 0.25, -0.05, 0.0, -0.3],
            "actual_result": ["H", "D", "A", "H", "A"],
        }
    )
    df.to_csv(raw / "sample_matches.csv", index=False)

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    monkeypatch.setattr("sys.argv", ["run_train.py", "--model-type", "logit", "--cv", "false", "--use-verifier", "true"])
    main()
    assert settings.eval_verifier_results_path.exists()


def test_run_train_uses_specified_data_path(monkeypatch, tmp_path):
    main = _load_run_train_main()
    root = tmp_path / "football-predictor"
    raw = root / "data" / "custom"
    raw.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(
        {
            "match_id": ["m1", "m2", "m3", "m4"],
            "date": pd.date_range("2025-01-01", periods=4, freq="D").astype(str),
            "league": ["EPL", "EPL", "LaLiga", "LaLiga"],
            "odds_home": [1.9, 2.1, 1.8, 2.5],
            "odds_draw": [3.2, 3.0, 3.4, 3.1],
            "odds_away": [4.1, 3.7, 4.5, 2.9],
            "actual_result": ["H", "D", "A", "H"],
        }
    )
    p = raw / "train.csv"
    df.to_csv(p, index=False)

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    monkeypatch.setattr("sys.argv", ["run_train.py", "--model-type", "logit", "--cv", "false", "--data-path", str(p)])
    main()
    import json
    from pathlib import Path
    payload = json.loads(settings.eval_metrics_path.read_text(encoding="utf-8"))
    assert payload.get("input_dataset_path")
    assert Path(payload["input_dataset_path"]).resolve() == p.resolve()


def test_run_train_missing_data_path_raises(monkeypatch, tmp_path):
    main = _load_run_train_main()
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    with pytest.raises(FileNotFoundError):
        monkeypatch.setattr("sys.argv", ["run_train.py", "--model-type", "logit", "--cv", "false", "--data-path", str(root / "missing.csv")])
        main()
