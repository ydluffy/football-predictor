from __future__ import annotations

from pathlib import Path

import pandas as pd

from strategy.backtest import BacktestConfig, run_backtest
from strategy.reporting import write_backtest_outputs


def test_strategy_backtest_v1_outputs_are_sane(tmp_path):
    matches = pd.DataFrame(
        {
            "match_id": ["m1", "m2", "m3"],
            "date": ["2025-01-01", "2025-01-02", "2025-01-03"],
            "league": ["E1", "E1", "E2"],
            "odds_home": [2.0, 2.2, 2.5],
            "odds_draw": [3.2, 3.1, 3.0],
            "odds_away": [4.0, 3.5, 2.9],
            "actual_result": ["H", "A", "D"],
        }
    )
    preds = pd.DataFrame(
        {
            "match_id": ["m1", "m2", "m3"],
            "date": ["2025-01-01", "2025-01-02", "2025-01-03"],
            "league": ["E1", "E1", "E2"],
            "p_home": [0.60, 0.40, 0.20],
            "p_draw": [0.20, 0.25, 0.40],
            "p_away": [0.20, 0.35, 0.40],
        }
    )

    cfg = BacktestConfig(initial_bankroll=1000.0)
    out = run_backtest(pred_df=preds, matches_df=matches, cfg=cfg)
    summary = out["summary"]
    assert isinstance(summary["n_bets"], int)
    assert isinstance(summary["final_bankroll"], float)
    assert summary["roi"] == summary["roi"]
    assert summary["max_drawdown"] == summary["max_drawdown"]

    out_dir = Path(tmp_path) / "bt"
    paths = write_backtest_outputs(out_dir=out_dir, bets=out["bets"], summary=out["summary"], by_league=out["by_league"], equity_curve=out["equity_curve"])
    for k in ("bets_path", "summary_path", "by_league_path", "equity_curve_path"):
        assert Path(paths[k]).exists()

