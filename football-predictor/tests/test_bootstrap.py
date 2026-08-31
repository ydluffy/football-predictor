from __future__ import annotations

import numpy as np

from evaluate.bootstrap import paired_bootstrap_logloss_difference


def test_paired_bootstrap_detects_clearly_better_model():
    y = np.array(["H", "D", "A"] * 100)
    model = np.tile(np.array([[0.8, 0.1, 0.1], [0.1, 0.8, 0.1], [0.1, 0.1, 0.8]]), (100, 1))
    reference = np.full((300, 3), 1.0 / 3.0)

    out = paired_bootstrap_logloss_difference(
        y,
        model,
        reference,
        n_bootstrap=200,
        random_state=1,
    )

    assert out["mean_logloss_difference"] < 0.0
    assert out["ci95_high"] < 0.0
    assert out["probability_model_better"] == 1.0
