from __future__ import annotations

import pandas as pd
import pytest

from world_cup.calibration import (
    MultinomialProbabilityCalibrator,
    calibration_features,
    fit_timeline_calibrator,
    predict_calibrated_match,
)
from world_cup.data import load_international_results, parse_world_cup_min_text
from world_cup.data_cache import (
    refresh_international_results,
    validate_international_results_file,
)
from world_cup.evaluation import (
    compare_international_models,
    evaluate_international_timeline_holdouts,
    evaluate_tournament_holdouts,
)
from world_cup.model import WorldCupBaselineModel


def test_parse_world_cup_min_text():
    text = """
= World Cup 2022
▪ First stage
▪▪ Group A
  Qatar v Ecuador                 0-2
  Senegal v Netherlands           0-2
▪ Round of 16
  Japan v Croatia                 1-1 a.e.t., 1-3 pen.
"""
    out = parse_world_cup_min_text(text)

    assert len(out) == 3
    assert out.loc[0, "tournament_year"] == 2022
    assert out.loc[2, "stage"] == "Round of 16"
    assert out.loc[2, "actual_result"] == "D"


def test_world_cup_model_probabilities_and_update():
    model = WorldCupBaselineModel()
    before = model.predict_match("A", "B")
    model.update("A", "B", 3, 0)
    after = model.predict_match("A", "B")

    assert abs(before["p_home"] + before["p_draw"] + before["p_away"] - 1.0) < 1e-12
    assert after["p_home"] > before["p_home"]
    assert model.team_rating("A") > model.team_rating("B")


def test_world_cup_model_applies_home_advantage_only_when_not_neutral():
    model = WorldCupBaselineModel()
    neutral = model.predict_match("A", "B", neutral=True)
    home = model.predict_match("A", "B", neutral=False)

    assert home["p_home"] > neutral["p_home"]
    assert home["expected_home_goals"] > neutral["expected_home_goals"]


def test_dixon_coles_adjustment_increases_draw_probability():
    baseline = WorldCupBaselineModel(draw_correlation=0.0).predict_match("A", "B")
    adjusted = WorldCupBaselineModel(draw_correlation=-0.1).predict_match("A", "B")

    assert adjusted["p_draw"] > baseline["p_draw"]
    assert abs(adjusted["p_home"] + adjusted["p_draw"] + adjusted["p_away"] - 1.0) < 1e-12


def test_multinomial_calibrator_outputs_ordered_probabilities():
    features = []
    targets = []
    model = WorldCupBaselineModel()
    for home_goals, away_goals in ((2, 0), (0, 0), (0, 2)) * 4:
        prediction = model.predict_match("A", "B")
        features.append(
            calibration_features(prediction, neutral=True, importance=1.0)
        )
        targets.append(0 if home_goals > away_goals else 2 if away_goals > home_goals else 1)
        model.update("A", "B", home_goals, away_goals)

    calibrator = MultinomialProbabilityCalibrator().fit(
        pd.DataFrame(features).to_numpy(),
        pd.Series(targets).to_numpy(),
    )
    probability = calibrator.predict_proba(features[-1])

    assert probability.shape == (1, 3)
    assert abs(probability.sum() - 1.0) < 1e-12


def test_timeline_calibrator_returns_frozen_baseline_and_calibrated_prediction():
    rows = []
    outcomes = ((2, 0), (0, 0), (0, 2)) * 4
    for index, (home_goals, away_goals) in enumerate(outcomes):
        rows.append(
            {
                "date": pd.Timestamp("2009-01-01") + pd.Timedelta(days=index),
                "home_team": "A",
                "away_team": "B",
                "home_goals": home_goals,
                "away_goals": away_goals,
                "actual_result": (
                    "H" if home_goals > away_goals else "A" if away_goals > home_goals else "D"
                ),
                "neutral": True,
                "importance": 1.0,
            }
        )

    baseline, calibrator, size = fit_timeline_calibrator(
        pd.DataFrame(rows),
        calibration_start=pd.Timestamp("2009-01-01"),
    )
    prediction = predict_calibrated_match(baseline, calibrator, "A", "B")

    assert size == len(rows)
    assert abs(prediction["p_home"] + prediction["p_draw"] + prediction["p_away"] - 1.0) < 1e-12
    assert {"raw_p_home", "raw_p_draw", "raw_p_away"} <= set(prediction)


def test_load_international_results_keeps_unplayed_fixtures_without_result(tmp_path):
    path = tmp_path / "results.csv"
    pd.DataFrame(
        [
            {
                "date": "2026-06-13",
                "home_team": "United States",
                "away_team": "Mexico",
                "home_score": 2,
                "away_score": 1,
                "tournament": "FIFA World Cup",
                "neutral": True,
            },
            {
                "date": "2026-06-14",
                "home_team": "Germany",
                "away_team": "Japan",
                "home_score": None,
                "away_score": None,
                "tournament": "FIFA World Cup",
                "neutral": True,
            },
        ]
    ).to_csv(path, index=False)

    completed = load_international_results(path)
    all_matches = load_international_results(path, completed_only=False)

    assert completed["home_team"].tolist() == ["USA"]
    assert len(all_matches) == 2
    assert pd.isna(all_matches.loc[1, "actual_result"])
    assert all_matches.loc[0, "importance"] == 1.5


def test_validate_international_results_rejects_truncated_file(tmp_path):
    path = tmp_path / "results.csv"
    pd.DataFrame(
        [
            {
                "date": "1961-01-01",
                "home_team": "A",
                "away_team": "B",
                "home_score": 1,
                "away_score": 0,
                "tournament": "Friendly",
                "neutral": False,
            }
        ]
    ).to_csv(path, index=False)

    with pytest.raises(ValueError, match="only 1 rows"):
        validate_international_results_file(path)


def test_refresh_international_results_preserves_existing_file_on_invalid_download(
    tmp_path,
    monkeypatch,
):
    destination = tmp_path / "results.csv"
    destination.write_text("trusted-old-data", encoding="utf-8")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size):
            del chunk_size
            yield b"date,home_team\n2026-01-01,A\n"

    monkeypatch.setattr(
        "world_cup.data_cache.requests.get",
        lambda *args, **kwargs: FakeResponse(),
    )

    with pytest.raises(ValueError):
        refresh_international_results(destination)

    assert destination.read_text(encoding="utf-8") == "trusted-old-data"
    assert not destination.with_suffix(".csv.part").exists()


def test_world_cup_holdout_evaluation():
    rows = []
    for year in (2010, 2014, 2018):
        for order, result in enumerate((("A", "B", 1, 0), ("B", "A", 0, 0), ("A", "C", 0, 1))):
            home, away, hg, ag = result
            rows.append(
                {
                    "tournament_year": year,
                    "match_order": order,
                    "home_team": home,
                    "away_team": away,
                    "home_goals": hg,
                    "away_goals": ag,
                    "actual_result": "H" if hg > ag else "A" if ag > hg else "D",
                }
            )
    out = evaluate_tournament_holdouts(pd.DataFrame(rows), min_train_tournaments=2)

    assert out["holdout_year"].tolist() == [2018]
    assert out.loc[0, "test_size"] == 3
    assert out.loc[0, "logloss"] > 0.0
    assert "logloss_vs_uniform" in out.columns


def test_international_timeline_holdout_uses_only_pre_tournament_matches():
    rows = [
        {
            "date": pd.Timestamp("2009-01-01"),
            "home_team": "A",
            "away_team": "B",
            "home_goals": 2,
            "away_goals": 0,
            "actual_result": "H",
            "tournament": "Friendly",
            "neutral": True,
            "importance": 0.55,
        },
        {
            "date": pd.Timestamp("2010-06-11"),
            "home_team": "A",
            "away_team": "B",
            "home_goals": 1,
            "away_goals": 0,
            "actual_result": "H",
            "tournament": "FIFA World Cup",
            "neutral": True,
            "importance": 1.5,
        },
        {
            "date": pd.Timestamp("2010-06-12"),
            "home_team": "B",
            "away_team": "A",
            "home_goals": 0,
            "away_goals": 0,
            "actual_result": "D",
            "tournament": "FIFA World Cup",
            "neutral": True,
            "importance": 1.5,
        },
    ]

    out = evaluate_international_timeline_holdouts(
        pd.DataFrame(rows),
        holdout_years=(2010,),
    )

    assert out.loc[0, "train_size"] == 1
    assert out.loc[0, "test_size"] == 2
    assert out.loc[0, "train_end"] == "2010-06-10"
    assert {"accuracy", "draw_recall", "ece"} <= set(out.columns)


def test_compare_international_models_labels_candidates():
    rows = [
        {
            "date": pd.Timestamp("2009-01-01"),
            "home_team": "A",
            "away_team": "B",
            "home_goals": 0,
            "away_goals": 0,
            "actual_result": "D",
            "tournament": "Friendly",
            "neutral": True,
            "importance": 0.55,
        },
        {
            "date": pd.Timestamp("2010-06-11"),
            "home_team": "A",
            "away_team": "B",
            "home_goals": 0,
            "away_goals": 0,
            "actual_result": "D",
            "tournament": "FIFA World Cup",
            "neutral": True,
            "importance": 1.5,
        },
    ]

    out = compare_international_models(
        pd.DataFrame(rows),
        holdout_years=(2010,),
        draw_correlations=(0.0, -0.1),
    )

    assert out["model"].tolist() == ["elo_poisson", "elo_dixon_coles"]
    assert out["draw_correlation"].tolist() == [0.0, -0.1]
