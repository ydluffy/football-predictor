from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from world_cup.prediction_review import (
    attach_handicap_line_movement,
    build_chinese_review_report,
    build_review_group_stats,
    load_espn_completed_results,
    settle_enhanced_predictions,
    summarize_enhanced_review,
)


def test_load_espn_completed_results_extracts_scores(tmp_path: Path):
    payload = {
        "events": [
            {
                "id": "1",
                "date": "2026-06-16T00:00Z",
                "status": {"type": {"completed": True}},
                "competitions": [
                    {
                        "competitors": [
                            {
                                "homeAway": "home",
                                "score": "2",
                                "team": {"displayName": "Iran"},
                            },
                            {
                                "homeAway": "away",
                                "score": "0",
                                "team": {"displayName": "New Zealand"},
                            },
                        ]
                    }
                ],
            }
        ]
    }
    path = tmp_path / "scoreboard.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    out = load_espn_completed_results(path)

    assert len(out) == 1
    assert out.loc[0, "actual_result"] == "H"
    assert out.loc[0, "home_goals"] == 2


def test_settle_enhanced_predictions_scores_result_score_and_totals():
    predictions = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-06-16"),
                "match_id": "1",
                "home_team": "Iran",
                "away_team": "New Zealand",
                "adjusted_p_home": 0.76,
                "adjusted_p_draw": 0.16,
                "adjusted_p_away": 0.08,
                "expected_home_goals": 2.4,
                "expected_away_goals": 0.6,
                "top_score_1": "2:0",
                "top_score_2": "1:0",
                "over_2_5_probability": 0.58,
                "under_2_5_probability": 0.42,
                "handicap_line": -1.0,
                "handicap_label": "ä¸»é˜Ÿè®©1çƒ",
                "handicap_recommended_key": "handicap_home_win",
                "handicap_recommended_result": "è®©èƒœ",
                "leisu_public_match_linked": 1,
                "leisu_intelligence_count": 27,
                "handicap_line": -1.0,
                "handicap_line_source": "sporttery",
                "handicap_recommended_key": "handicap_home_win",
                "handicap_recommended_result": "è®©èƒœ",
            }
        ]
    )
    results = pd.DataFrame(
        [
            {
                "match_id": "1",
                "home_goals": 2,
                "away_goals": 0,
                "actual_result": "H",
                "result_source": "test",
                "source_url": "",
            }
        ]
    )

    settled = settle_enhanced_predictions(predictions, results)
    summary = summarize_enhanced_review(settled)

    assert settled.loc[0, "result_hit"]
    assert settled.loc[0, "top_score_1_hit"]
    assert settled.loc[0, "top2_score_hit"]
    assert not settled.loc[0, "over_2_5_hit"]
    assert settled.loc[0, "actual_handicap_result_key"] == "handicap_home_win"
    assert settled.loc[0, "handicap_hit"]
    assert summary["result_accuracy"] == 1.0
    assert summary["settled_with_leisu"] == 1


def test_build_review_group_stats_segments_completed_predictions():
    predictions = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-06-16"),
                "match_id": "1",
                "home_team": "Iran",
                "away_team": "New Zealand",
                "adjusted_p_home": 0.76,
                "adjusted_p_draw": 0.16,
                "adjusted_p_away": 0.08,
                "expected_home_goals": 2.4,
                "expected_away_goals": 0.6,
                "top_score_1": "2:0",
                "top_score_2": "1:0",
                "over_2_5_probability": 0.58,
                "under_2_5_probability": 0.42,
                "lineup_adjustment_active": 1,
                "home_lineup_confirmed": 1,
                "away_lineup_confirmed": 1,
                "leisu_public_match_linked": 1,
                "leisu_intelligence_count": 27,
                "handicap_line": -1.0,
                "handicap_line_source": "sporttery",
                "handicap_recommended_key": "handicap_home_win",
                "handicap_recommended_result": "è®©èƒœ",
            },
            {
                "date": pd.Timestamp("2026-06-16"),
                "match_id": "2",
                "home_team": "A",
                "away_team": "B",
                "adjusted_p_home": 0.40,
                "adjusted_p_draw": 0.32,
                "adjusted_p_away": 0.28,
                "expected_home_goals": 1.1,
                "expected_away_goals": 1.0,
                "top_score_1": "1:1",
                "top_score_2": "1:0",
                "over_2_5_probability": 0.42,
                "under_2_5_probability": 0.58,
                "lineup_adjustment_active": 0,
                "home_lineup_confirmed": 0,
                "away_lineup_confirmed": 0,
                "leisu_public_match_linked": 0,
                "leisu_intelligence_count": 0,
                "handicap_line": 0.0,
                "handicap_line_source": "model_inferred",
                "handicap_recommended_key": "handicap_away_win",
                "handicap_recommended_result": "è®©è´Ÿ",
            },
        ]
    )
    results = pd.DataFrame(
        [
            {
                "match_id": "1",
                "home_goals": 2,
                "away_goals": 0,
                "actual_result": "H",
                "result_source": "test",
                "source_url": "",
            },
            {
                "match_id": "2",
                "home_goals": 0,
                "away_goals": 1,
                "actual_result": "A",
                "result_source": "test",
                "source_url": "",
            },
        ]
    )
    settled = settle_enhanced_predictions(predictions, results)

    stats = build_review_group_stats(settled)

    assert {
        "confidence",
        "leisu_coverage",
        "lineup_status",
        "handicap_line_source",
        "handicap_depth_bucket",
    } <= set(stats["group_type"])
    confidence = stats[stats["group_type"] == "confidence"]
    assert confidence["matches"].sum() == 2
    assert confidence["result_accuracy"].max() == 1.0
    leisu = stats[(stats["group_type"] == "leisu_coverage") & (stats["group"] == "é›·é€Ÿæƒ…æŠ¥è¾ƒå¤š")]
    assert leisu.iloc[0]["matches"] == 1
    source = stats[(stats["group_type"] == "handicap_line_source") & (stats["group"] == "sporttery")]
    assert source.iloc[0]["matches"] == 1
    depth = stats[(stats["group_type"] == "handicap_depth_bucket") & (stats["group"] == "home_gives_1")]
    assert depth.iloc[0]["matches"] == 1


def test_attach_handicap_line_movement_adds_review_groups():
    settled = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-06-25"),
                "home_team": "Japan",
                "away_team": "Sweden",
                "settled": True,
                "predicted_result_zh": "ä¸»èƒœ",
                "actual_score": "2:1",
                "result_hit": True,
                "top_score_1_hit": False,
                "top2_score_hit": False,
                "over_2_5_hit": True,
                "handicap_hit": True,
                "handicap_label": "ä¸»é˜Ÿè®©1çƒ",
                "handicap_recommended_result": "è®©èƒœ",
                "leisu_intelligence_count": 0,
                "logloss": 0.5,
                "brier": 0.2,
                "actual_probability": 0.6,
                "top_probability": 0.7,
                "actual_total_goals": 3,
                "expected_total_goals": 2.8,
            }
        ]
    )
    movement = pd.DataFrame(
        [
            {
                "date": "2026-06-25",
                "home_team": "Japan",
                "away_team": "Sweden",
                "opening_home_handicap": -1.0,
                "latest_home_handicap": -2.0,
                "handicap_movement_direction": "toward_home",
                "favorite_movement": "deeper",
            }
        ]
    )

    out = attach_handicap_line_movement(settled, movement)
    stats = build_review_group_stats(out)

    assert out.loc[0, "handicap_movement_direction"] == "toward_home"
    movement_group = stats[
        (stats["group_type"] == "handicap_movement_direction")
        & (stats["group"] == "toward_home")
    ]
    assert movement_group.iloc[0]["matches"] == 1

    report = build_chinese_review_report(
        out,
        {
            "predictions": 1,
            "settled_matches": 1,
            "pending_matches": 0,
            "result_accuracy": 1.0,
            "top_score_1_accuracy": 0.0,
            "top2_score_accuracy": 0.0,
            "over_2_5_accuracy": 1.0,
            "high_confidence_matches": 0,
            "high_confidence_accuracy": None,
            "mean_logloss": 0.5,
            "uniform_logloss": 1.0986,
            "goal_ratio_actual_to_expected": 1.0,
        },
    )
    assert "-1.0->-2.0" in report
    assert "toward_home" in report
