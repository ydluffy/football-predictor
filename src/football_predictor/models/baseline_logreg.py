from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


CalibrationMethod = Literal["none", "sigmoid", "isotonic"]


@dataclass(frozen=True, slots=True)
class TrainedModel:
    model: object
    label_order: list[str]
    model_name: str
    calibration: CalibrationMethod


def train_logreg(
    x: np.ndarray,
    y: np.ndarray,
    label_order: list[str],
    calibration: CalibrationMethod = "sigmoid",
) -> TrainedModel:
    if x.ndim != 2:
        raise ValueError("x must be 2D")
    if y.ndim != 1:
        raise ValueError("y must be 1D")
    if x.shape[0] != y.shape[0]:
        raise ValueError("mismatched n_samples")

    base = Pipeline(
        steps=[
            ("scaler", StandardScaler(with_mean=True, with_std=True)),
            (
                "logreg",
                LogisticRegression(
                    solver="lbfgs",
                    max_iter=500,
                    n_jobs=None,
                    random_state=42,
                ),
            ),
        ]
    )

    if calibration == "none":
        fitted = base.fit(x, y)
        return TrainedModel(
            model=fitted,
            label_order=label_order,
            model_name="logreg_multinomial",
            calibration="none",
        )

    calibrated = CalibratedClassifierCV(estimator=base, method=calibration, cv=3)
    fitted = calibrated.fit(x, y)
    return TrainedModel(
        model=fitted,
        label_order=label_order,
        model_name="logreg_multinomial_calibrated",
        calibration=calibration,
    )


def predict_proba(trained: TrainedModel, x: np.ndarray) -> np.ndarray:
    model = trained.model
    proba = getattr(model, "predict_proba")(x)
    proba = np.asarray(proba, dtype=float)
    row_sum = proba.sum(axis=1, keepdims=True)
    row_sum[row_sum == 0.0] = 1.0
    return proba / row_sum
