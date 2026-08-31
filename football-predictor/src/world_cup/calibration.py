from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from world_cup.model import WorldCupBaselineModel


RESULT_INDEX = {"H": 0, "D": 1, "A": 2}


def calibration_features(
    prediction: dict[str, object],
    *,
    neutral: bool,
    importance: float,
) -> np.ndarray:
    probabilities = np.clip(
        np.array(
            [
                prediction["p_home"],
                prediction["p_draw"],
                prediction["p_away"],
            ],
            dtype=float,
        ),
        1e-8,
        1.0,
    )
    expected_home = float(prediction["expected_home_goals"])
    expected_away = float(prediction["expected_away_goals"])
    return np.array(
        [
            np.log(probabilities[0] / probabilities[1]),
            np.log(probabilities[2] / probabilities[1]),
            expected_home - expected_away,
            expected_home + expected_away,
            abs(expected_home - expected_away),
            float(neutral),
            float(importance),
        ],
        dtype=float,
    )


class MultinomialProbabilityCalibrator:
    def __init__(self, *, c: float = 0.3) -> None:
        self.c = float(c)
        self.scaler = StandardScaler()
        self.classifier = LogisticRegression(
            C=self.c,
            max_iter=2_000,
            solver="lbfgs",
        )

    def fit(self, features: np.ndarray, targets: np.ndarray) -> "MultinomialProbabilityCalibrator":
        x = np.asarray(features, dtype=float)
        y = np.asarray(targets, dtype=int)
        if x.ndim != 2 or x.shape[1] != 7:
            raise ValueError("calibration features must have shape (n_samples, 7)")
        if set(np.unique(y)) != {0, 1, 2}:
            raise ValueError("calibration targets must contain home, draw, and away classes")
        self.classifier.fit(self.scaler.fit_transform(x), y)
        return self

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        x = np.asarray(features, dtype=float)
        if x.ndim == 1:
            x = x.reshape(1, -1)
        raw = self.classifier.predict_proba(self.scaler.transform(x))
        ordered = np.zeros((len(x), 3), dtype=float)
        for source_index, class_index in enumerate(self.classifier.classes_):
            ordered[:, int(class_index)] = raw[:, source_index]
        return ordered


def fit_timeline_calibrator(
    matches: pd.DataFrame,
    *,
    calibration_start: pd.Timestamp,
    c: float = 0.3,
) -> tuple[WorldCupBaselineModel, MultinomialProbabilityCalibrator, int]:
    baseline = WorldCupBaselineModel()
    features: list[np.ndarray] = []
    targets: list[int] = []

    for row in matches.sort_values("date", kind="mergesort").itertuples(index=False):
        neutral = bool(getattr(row, "neutral", True))
        importance = float(getattr(row, "importance", 1.0))
        prediction = baseline.predict_match(
            str(row.home_team),
            str(row.away_team),
            neutral=neutral,
        )
        if pd.Timestamp(row.date) >= calibration_start:
            features.append(
                calibration_features(
                    prediction,
                    neutral=neutral,
                    importance=importance,
                )
            )
            targets.append(RESULT_INDEX[str(row.actual_result)])
        baseline.update(
            str(row.home_team),
            str(row.away_team),
            int(row.home_goals),
            int(row.away_goals),
            neutral=neutral,
            importance=importance,
        )

    calibrator = MultinomialProbabilityCalibrator(c=c).fit(
        np.vstack(features),
        np.asarray(targets),
    )
    return baseline, calibrator, len(targets)


def predict_calibrated_match(
    baseline: WorldCupBaselineModel,
    calibrator: MultinomialProbabilityCalibrator,
    home_team: str,
    away_team: str,
    *,
    neutral: bool = True,
    importance: float = 1.5,
) -> dict[str, object]:
    prediction = baseline.predict_match(home_team, away_team, neutral=neutral)
    feature = calibration_features(
        prediction,
        neutral=neutral,
        importance=importance,
    )
    probability = calibrator.predict_proba(feature)[0]
    prediction["raw_p_home"] = prediction["p_home"]
    prediction["raw_p_draw"] = prediction["p_draw"]
    prediction["raw_p_away"] = prediction["p_away"]
    prediction["p_home"] = float(probability[0])
    prediction["p_draw"] = float(probability[1])
    prediction["p_away"] = float(probability[2])
    return prediction
