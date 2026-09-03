from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_external_ticket_samples.py"
SPEC = importlib.util.spec_from_file_location("audit_external_ticket_samples", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _frame(results: list[str]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "ticket_id": f"T{i}", "sales_date": "2026-09-01", "source": "manual",
            "plan_type": "double", "selections": "001胜+002平/负", "total_stake": 4,
            "payout": 10 if result == "win" else 0, "result": result,
            "settlement_status": "settled",
        }
        for i, result in enumerate(results)
    ])


def test_winner_only_external_sample_is_not_promotion_eligible() -> None:
    result = MODULE.audit(_frame(["win", "win"]))
    assert result["one_sided_sample"] is True
    assert result["promotion_eligible"] is False


def test_complete_external_sample_can_be_evaluated() -> None:
    result = MODULE.audit(_frame(["win", "loss"]))
    assert result["one_sided_sample"] is False
    assert result["promotion_eligible"] is True
