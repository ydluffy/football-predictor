from __future__ import annotations

import numpy as np
import pandas as pd

from models.market_residual import MarketResidualModel, normalize_probabilities, select_context_features


def test_context_selection_excludes_all_market_features() -> None:
    features = pd.DataFrame(
        {
            "norm_home": [0.5, 0.4],
            "implied_home": [0.55, 0.44],
            "odds_diff_home_away": [-1.0, 1.0],
            "rest_days_diff": [2.0, -1.0],
            "season_progress": [0.2, 0.8],
        }
    )
    context = select_context_features(features)
    assert list(context.columns) == ["rest_days_diff", "season_progress"]


def test_zero_strength_exactly_reproduces_market() -> None:
    X = pd.DataFrame({"rest_days_diff": [1.0, -1.0, 0.0, 2.0, -2.0, 0.5]})
    y = pd.Series(["H", "A", "D", "H", "A", "D"])
    market = np.tile([0.45, 0.27, 0.28], (6, 1))
    model = MarketResidualModel(alpha=10.0).train(X, y, market)
    predicted = model.predict_proba(X, market, strength=0.0)
    assert np.allclose(predicted.to_numpy(), normalize_probabilities(market))
    assert np.allclose(predicted.sum(axis=1), 1.0)
