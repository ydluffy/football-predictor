from __future__ import annotations

import pandas as pd
import pytest

from strategy.fixed_odds_shadow import record_fixed_odds_shadow


def _plans() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "plan_type": "固定赔率观察",
                "selections": "003 A vs B 让球胜平负:让负 + 008 C vs D 胜平负:主胜",
                "estimated_odds_min": 1.904,
                "estimated_odds_max": 1.904,
            }
        ]
    )


def test_record_fixed_odds_shadow_is_separate_and_idempotent(tmp_path) -> None:
    ledger = tmp_path / "fixed.csv"
    first = record_fixed_odds_shadow(
        _plans(), sales_day="2026-08-28", time_window="00:30-03:30",
        analysis_at="2026-08-28T21:10:00+08:00", stage="final", ledger_path=ledger,
    )
    second = record_fixed_odds_shadow(
        _plans(), sales_day="2026-08-28", time_window="00:30-03:30",
        analysis_at="2026-08-28T21:12:00+08:00", stage="final", ledger_path=ledger,
    )
    saved = pd.read_csv(ledger, dtype=str, keep_default_na=False)
    assert first["status"] == "recorded"
    assert second["status"] == "duplicate_ignored"
    assert len(saved) == 1
    assert saved.iloc[0]["stake"] == "2.00"
    assert saved.iloc[0]["result"] == "pending"
    assert first["production_ledger_write_performed"] is False


def test_record_fixed_odds_shadow_rejects_non_final_stage(tmp_path) -> None:
    with pytest.raises(ValueError, match="final stage"):
        record_fixed_odds_shadow(
            _plans(), sales_day="2026-08-28", time_window="00:30-03:30",
            analysis_at="2026-08-28T15:00:00+08:00", stage="confirm",
            ledger_path=tmp_path / "fixed.csv",
        )
