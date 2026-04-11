from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd

from config.settings import get_settings


def test_import_real_csv_script_writes_outputs(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    ext = root / "ext"
    ext.mkdir(parents=True, exist_ok=True)

    raw = pd.DataFrame(
        {
            "MatchID": ["m1", "m2", "m3"],
            "Date": ["2025-01-01", "2025-01-02", "2025-01-03"],
            "LeagueName": ["EPL", "EPL", "LaLiga"],
            "HomeTeam": ["A", "B", "C"],
            "AwayTeam": ["D", "E", "F"],
            "HomeOdds": [2.1, 1.9, 2.5],
            "DrawOdds": [3.2, 3.4, 3.1],
            "AwayOdds": [3.5, 4.2, 2.9],
            "Result": ["H", "D", "A"],
            "HomeXG": [1.4, 1.1, 1.6],
            "AwayXG": [0.9, 1.0, 1.2],
            "InjuryFlag": [0, 1, 0],
            "LineMove": [-0.05, 0.12, 0.01],
        }
    )
    inp = ext / "raw.csv"
    raw.to_csv(inp, index=False)

    mapping_path = (Path(__file__).resolve().parents[1] / "data" / "mappings" / "example_mapping_v2.json").resolve()

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    script_path = Path(__file__).resolve().parents[1] / "scripts" / "import_real_csv.py"
    spec = importlib.util.spec_from_file_location("import_real_csv_script", str(script_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 scripts/import_real_csv.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    monkeypatch.setattr(
        "sys.argv",
        [
            "import_real_csv.py",
            "--input-path",
            str(inp),
            "--mapping-path",
            str(mapping_path),
            "--feature-version",
            "v2",
        ],
    )
    module.main()

    assert (settings.data_interim_dir / "imported_preview.csv").exists()
    assert (settings.data_processed_dir / "real_matches_standardized.csv").exists()
    assert settings.eval_dataset_validation_path.exists()
    assert settings.eval_dataset_missing_report_path.exists()
    assert settings.eval_import_summary_path.exists()
    assert settings.eval_field_mapping_report_path.exists()


def test_import_real_csv_script_autogenerates_match_id_for_football_data(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    ext = root / "ext"
    ext.mkdir(parents=True, exist_ok=True)

    raw = pd.DataFrame(
        {
            "Div": ["E0", "E0"],
            "Date": ["15/08/2025", "16/08/2025"],
            "HomeTeam": ["Man United", "Arsenal"],
            "AwayTeam": ["Fulham", "Chelsea"],
            "FTR": ["H", "D"],
            "B365H": [1.6, 1.8],
            "B365D": [4.2, 3.9],
            "B365A": [5.2, 4.1],
        }
    )
    inp = ext / "football_data.csv"
    raw.to_csv(inp, index=False)

    mapping_path = (Path(__file__).resolve().parents[1] / "data" / "mappings" / "football_data_mapping.json").resolve()

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    script_path = Path(__file__).resolve().parents[1] / "scripts" / "import_real_csv.py"
    spec = importlib.util.spec_from_file_location("import_real_csv_script2", str(script_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 scripts/import_real_csv.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    monkeypatch.setattr(
        "sys.argv",
        [
            "import_real_csv.py",
            "--input-path",
            str(inp),
            "--mapping-path",
            str(mapping_path),
            "--feature-version",
            "v3",
        ],
    )
    module.main()

    out_csv = settings.data_processed_dir / "real_matches_standardized.csv"
    df_out = pd.read_csv(out_csv)
    assert "match_id" in df_out.columns
    assert df_out["match_id"].notna().all()

    v = json.loads(settings.eval_dataset_validation_path.read_text(encoding="utf-8"))
    assert v.get("match_id_generated") is True

    s = json.loads(settings.eval_import_summary_path.read_text(encoding="utf-8"))
    assert s.get("match_id_generated") is True
    assert isinstance(s.get("match_id_preview"), list)
