from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "review_prediction_vs_ticket_expression.py"
SPEC = importlib.util.spec_from_file_location("review_prediction_vs_ticket_expression", MODULE_PATH)
reviewer = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(reviewer)


def test_review_finds_parlay_structure_drag():
    ledger = pd.DataFrame(
        [
            {
                "date": "2026-07-19",
                "time_window": "19:00",
                "plan_id": "P1",
                "plan_type": "稳健",
                "selections": "203 away + 204 away + 206 away",
                "stake": 100,
                "payout": 0,
                "net_profit": -100,
                "roi": -1,
                "result": "未中",
                "review_note": "203 away hit; 204 away hit; 206 away missed. One leg broke.",
            }
        ]
    )

    frame = reviewer.review_ledger(ledger, "2026-07-19")

    assert frame.loc[0, "diagnosis"] == "组合结构拖累"
    assert frame.loc[0, "prediction_signal_grade"] == "B"
    assert "拆票" in frame.loc[0, "optimization_suggestion"]


def test_review_low_score_package_suggests_zero_zero_coverage():
    ledger = pd.DataFrame(
        [
            {
                "date": "2026-07-19",
                "time_window": "19:00-worldcup",
                "plan_id": "WC",
                "plan_type": "同场剧本包",
                "selections": "Spain win; Spain(-1) let loss; total goals 1/2; correct score 1:1/1:0/2:1",
                "stake": 100,
                "payout": 57,
                "net_profit": -43,
                "roi": -0.43,
                "result": "部分命中",
                "review_note": "Spain 0:0 Argentina: let loss hit; score 0:0 not selected; HTFT D-D hit; total0 missed",
            }
        ]
    )

    frame = reviewer.review_ledger(ledger, "2026-07-19")

    assert frame.loc[0, "diagnosis"] == "覆盖不足"
    assert "0:0" in frame.loc[0, "optimization_suggestion"]
    assert "总进球0" in frame.loc[0, "optimization_suggestion"]


def test_summary_calculates_roi():
    frame = pd.DataFrame(
        [
            {"stake": 100, "payout": 210, "net_profit": 110, "diagnosis": "兑现成功"},
            {"stake": 100, "payout": 0, "net_profit": -100, "diagnosis": "组合结构拖累"},
        ]
    )

    summary = reviewer.summarize_review(frame)

    assert summary["stake"] == 200
    assert summary["net_profit"] == 10
    assert summary["roi"] == 0.05
