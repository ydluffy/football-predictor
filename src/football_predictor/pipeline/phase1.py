from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from football_predictor.agents.verifier import compute_risk_flags
from football_predictor.artifacts import write_dataframe_csv, write_json, write_model
from football_predictor.data.io import read_matches_csv
from football_predictor.decision.orchestrator import apply_risk_adjustment
from football_predictor.features.baseline import build_baseline_features, extract_labels
from football_predictor.metrics import multiclass_brier_score, multiclass_logloss
from football_predictor.models.baseline_logreg import predict_proba, train_logreg
from football_predictor.schemas import EvaluationReport, MatchResult
from football_predictor.settings import Settings


LABEL_ORDER: list[str] = ["H", "D", "A"]


def run_phase1(data_path: Path, settings: Settings) -> dict[str, Any]:
    logger.remove()
    logger.add(lambda msg: print(msg, end=""), level=settings.log_level)

    logger.info("phase1:start data_path={}\n", str(data_path))
    df = read_matches_csv(data_path)
    x_df = build_baseline_features(df)
    y_raw = extract_labels(df)

    label_to_idx = {lbl: i for i, lbl in enumerate(LABEL_ORDER)}
    y_idx = y_raw.map(label_to_idx).to_numpy(dtype=int)
    x = x_df.to_numpy(dtype=float)

    trained = train_logreg(x=x, y=y_idx, label_order=LABEL_ORDER, calibration="sigmoid")
    proba = predict_proba(trained, x)

    brier = multiclass_brier_score(y_true=y_idx, proba=proba)
    ll = multiclass_logloss(y_true=y_idx, proba=proba)
    report = EvaluationReport(
        model_name=trained.model_name,
        n_samples=int(df.shape[0]),
        brier=brier,
        logloss=ll,
        label_order=[MatchResult.home, MatchResult.draw, MatchResult.away],
    )

    pred_rows: list[dict[str, Any]] = []
    for i, row in df.iterrows():
        risk_flags = compute_risk_flags(row)
        decision = apply_risk_adjustment(
            model_proba=np.array([proba[i, 0], proba[i, 1], proba[i, 2]], dtype=float),
            risk_flags=risk_flags,
        )
        pred_rows.append(
            {
                "match_id": row["match_id"],
                "date": row["date"],
                "league": row["league"],
                "home_team": row["home_team"],
                "away_team": row["away_team"],
                "p_home": float(decision.proba[0]),
                "p_draw": float(decision.proba[1]),
                "p_away": float(decision.proba[2]),
                "brier": brier,
                "logloss": ll,
                "risk_flags": [asdict(f) for f in decision.risk_flags],
                "requires_review": decision.requires_review,
                "actual_result": row["actual_result"],
            }
        )

    pred_df = pd.DataFrame(pred_rows)

    artifacts_dir = settings.artifacts_dir
    model_path = settings.model_path
    preds_path = artifacts_dir / "predictions" / "phase1_predictions.csv"
    metrics_path = artifacts_dir / "metrics" / "phase1_metrics.json"

    write_model(model_path, trained)
    write_dataframe_csv(preds_path, pred_df)
    write_json(metrics_path, report.model_dump())

    logger.info(
        "phase1:done model_path={} preds_path={} metrics_path={}\n",
        str(model_path),
        str(preds_path),
        str(metrics_path),
    )

    return {
        "model_path": str(model_path),
        "preds_path": str(preds_path),
        "metrics_path": str(metrics_path),
        "metrics": report.model_dump(),
    }
