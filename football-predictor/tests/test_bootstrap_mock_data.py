from __future__ import annotations

import importlib.util
import subprocess

from config.settings import get_settings


def test_bootstrap_mock_data_writes_csv_and_calls_train(monkeypatch, tmp_path):
    root_file = __file__
    from pathlib import Path

    script_path = Path(root_file).resolve().parents[1] / "scripts" / "bootstrap_mock_data.py"
    spec = importlib.util.spec_from_file_location("bootstrap_mock_data_script", str(script_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 scripts/bootstrap_mock_data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    main = module.main

    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    calls: list[tuple[list[str], str]] = []

    def _fake_run(cmd, cwd, check):
        calls.append((list(cmd), str(cwd)))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr("subprocess.run", _fake_run)
    monkeypatch.setattr("sys.argv", ["bootstrap_mock_data.py", "--n-rows", "30", "--run-train", "true"])

    main()
    assert (settings.data_raw_dir / "mock_matches_v1.csv").exists()
    assert (settings.data_raw_dir / "mock_matches_v2.csv").exists()
    assert (settings.data_raw_dir / "mock_matches_v3.csv").exists()
    assert settings.eval_dataset_validation_path.exists()
    assert settings.eval_dataset_missing_report_path.exists()
    assert calls
    assert calls[0][1] == str(settings.project_root)
