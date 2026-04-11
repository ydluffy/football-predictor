from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from football_predictor.pipeline.phase1 import run_phase1
from football_predictor.settings import Settings


def test_phase1_end_to_end(tmp_path: Path) -> None:
    base_dir = tmp_path
    data_dir = base_dir / "data"
    artifacts_dir = base_dir / "artifacts"
    model_path = artifacts_dir / "models" / "baseline_logreg.joblib"
    data_dir.mkdir(parents=True, exist_ok=True)

    src_csv = Path(__file__).resolve().parents[1] / "data" / "sample_matches.csv"
    dst_csv = data_dir / "sample_matches.csv"
    shutil.copyfile(src_csv, dst_csv)

    settings = Settings(
        base_dir=base_dir,
        artifacts_dir=artifacts_dir,
        data_dir=data_dir,
        model_path=model_path,
        log_level="INFO",
    )

    result = run_phase1(data_path=dst_csv, settings=settings)
    assert Path(result["model_path"]).exists()
    assert Path(result["preds_path"]).exists()
    assert Path(result["metrics_path"]).exists()
    assert 0.0 <= float(result["metrics"]["brier"])

    pred_df = pd.read_csv(result["preds_path"])
    for col in ["p_home", "p_draw", "p_away", "brier", "logloss", "risk_flags", "requires_review"]:
        assert col in pred_df.columns
