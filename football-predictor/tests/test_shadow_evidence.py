from __future__ import annotations

import json

import pandas as pd

from strategy.shadow_evidence import record_shadow_run, settle_shadow_evidence


def _config(path):
    path.write_text(json.dumps({"portfolio": {
        "budget": 100.0, "unit": 2.0, "min_edge": 0.025, "probability_haircut": 0.02,
        "max_decimal_odds": 4.0, "max_legs": 2, "max_total_stake_fraction": 0.5,
        "max_candidate_stake_fraction": 0.15, "max_match_exposure_fraction": 0.2,
        "max_competition_exposure_fraction": 0.3, "fractional_kelly": 0.15,
    }}), encoding="utf-8")


def test_final_shadow_run_records_all_predictions_and_virtual_plan_then_settles(tmp_path):
    config = tmp_path / "config.json"; _config(config)
    prediction_ledger = tmp_path / "predictions.csv"; portfolio_ledger = tmp_path / "portfolio.csv"
    predictions = pd.DataFrame([
        {
            "date": "2026-08-17", "match_number": "001", "competition": "英超",
            "kickoff_time": "2026-08-17 20:00", "home_team": "曼城", "away_team": "阿森纳",
            "home_handicap": -1, "rqspf_odds_home": 2.0, "rqspf_odds_draw": 3.2,
            "rqspf_odds_away": 3.6, "handicap_model_usage": "shadow_only",
            "handicap_model_probability_home": 0.70, "handicap_model_probability_draw": 0.15,
            "handicap_model_probability_away": 0.15, "handicap_model_pick": "home",
            "handicap_model_edge": 0.20, "handicap_model_expected_value": 0.40,
            "handicap_model_source_captured_at": "2026-08-17T11:00:00+08:00",
        },
        {
            "date": "2026-08-17", "match_number": "002", "competition": "瑞超",
            "kickoff_time": "2026-08-17 21:00", "home_team": "甲", "away_team": "乙",
            "home_handicap": -1, "handicap_model_usage": "blocked",
            "handicap_model_reason": "competition_not_in_training_domain",
        },
    ])
    audit = record_shadow_run(
        predictions, sales_day="2026-08-17", analysis_at="2026-08-17T11:30:00+08:00",
        stage="final", model_id="v2", prediction_ledger_path=prediction_ledger,
        portfolio_ledger_path=portfolio_ledger, config_path=config,
    )
    assert audit["prediction_ledger_rows"] == 2
    assert audit["portfolio_ledger_rows"] == 1
    assert audit["production_ledger_write_performed"] is False
    recorded = pd.read_csv(prediction_ledger)
    assert recorded.loc[0, "match_id"] == "2026-08-17|001"
    assert recorded.loc[1, "result_status"] == "not_evaluable"

    results = pd.DataFrame([{
        "date": "2026-08-17", "match_number": "周日001", "home_team": "曼城", "away_team": "阿森纳",
        "all_home_team": "曼城", "all_away_team": "阿森纳", "full_time_score": "2:0", "rqspf_result": "让胜",
    }])
    settled = settle_shadow_evidence(
        prediction_ledger_path=prediction_ledger, portfolio_ledger_path=portfolio_ledger,
        results=results, settled_at="2026-08-18T13:00:00+08:00",
    )
    assert settled["settled_shadow_plans"] == 1
    assert settled["shadow_roi"] == 1.0
    assert settled["production_ledger_write_performed"] is False


def test_confirm_stage_records_prediction_but_never_creates_plan(tmp_path):
    config = tmp_path / "config.json"; _config(config)
    prediction = pd.DataFrame([{
        "date": "2026-08-17", "match_number": "001", "competition": "英超",
        "home_team": "曼城", "away_team": "阿森纳", "home_handicap": -1,
        "rqspf_odds_home": 2.0, "handicap_model_usage": "shadow_only",
        "handicap_model_probability_home": 0.7, "handicap_model_pick": "home",
    }])
    audit = record_shadow_run(
        prediction, sales_day="2026-08-17", analysis_at="2026-08-17T11:05:00+08:00",
        stage="confirm", model_id="v2", prediction_ledger_path=tmp_path / "pred.csv",
        portfolio_ledger_path=tmp_path / "portfolio.csv", config_path=config,
    )
    assert audit["prediction_ledger_rows"] == 1
    assert audit["portfolio_ledger_rows"] == 0
