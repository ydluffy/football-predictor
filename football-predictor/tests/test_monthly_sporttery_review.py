from __future__ import annotations

import pandas as pd

from scripts.build_sporttery_monthly_review import maximum_drawdown, parse_plan_odds, summarize


def test_parse_plan_odds_supports_formula() -> None:
    assert parse_plan_odds("1.20*1.50=1.8000") == 1.8


def test_monthly_summary_calculates_roi_hit_rate_and_drawdown() -> None:
    frame = pd.DataFrame([
        {"date": "2026-09-01", "time_window": "18:00", "plan_id": "A", "stake": 100, "payout": 0, "result": "未中"},
        {"date": "2026-09-02", "time_window": "18:00", "plan_id": "B", "stake": 100, "payout": 180, "result": "命中"},
        {"date": "2026-09-03", "time_window": "18:00", "plan_id": "C", "stake": 100, "payout": 0, "result": "未中"},
    ])

    result = summarize(frame)

    assert result["plans"] == 3
    assert result["hit_rate"] == 0.3333
    assert result["roi"] == -0.4
    assert maximum_drawdown(frame) == (120.0, 0.4)
