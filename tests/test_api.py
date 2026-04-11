from __future__ import annotations

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from football_predictor.api.main import create_app
from football_predictor.pipeline.phase1 import run_phase1
from football_predictor.settings import Settings


def test_api_predict(tmp_path: Path) -> None:
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
    run_phase1(data_path=dst_csv, settings=settings)

    app = create_app(settings=settings)
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        payload = {
            "match_id": "x1",
            "date": "2025-10-01",
            "league": "EPL",
            "home_team": "A",
            "away_team": "B",
            "odds_home": 2.1,
            "odds_draw": 3.3,
            "odds_away": 3.6,
            "xg_home": 1.4,
            "xg_away": 1.1,
            "injury_flag": 0,
            "line_move": 0.05
        }
        r2 = client.post("/predict", json=payload)
        assert r2.status_code == 200
        body = r2.json()
        assert set(["p_home", "p_draw", "p_away"]).issubset(set(body["proba"].keys()))
