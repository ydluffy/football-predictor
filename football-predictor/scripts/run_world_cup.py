from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from world_cup.data import load_international_results, load_world_cup_min_directory
from world_cup.calibration import fit_timeline_calibrator, predict_calibrated_match
from world_cup.evaluation import (
    bootstrap_calibrator_vs_baseline,
    compare_calibration_windows,
    compare_international_models,
    evaluate_international_timeline_holdouts,
    evaluate_tournament_holdouts,
)
from world_cup.model import WorldCupBaselineModel


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data/external/openfootball-worldcup/min")
    parser.add_argument(
        "--international-results",
        default="data/external/international-results/results.csv",
    )
    parser.add_argument("--training-source", choices=["world-cups", "internationals"], default="internationals")
    parser.add_argument("--evaluate", choices=["true", "false"], default="false")
    parser.add_argument("--compare-models", choices=["true", "false"], default="false")
    parser.add_argument("--compare-calibration", choices=["true", "false"], default="false")
    parser.add_argument("--bootstrap-calibration", choices=["true", "false"], default="false")
    parser.add_argument("--calibrated", choices=["true", "false"], default="false")
    parser.add_argument("--calibration-years", type=int, default=4)
    parser.add_argument("--draw-correlation", type=float, default=0.0)
    parser.add_argument("--home-team", default="")
    parser.add_argument("--away-team", default="")
    parser.add_argument("--predict-date", default="")
    args = parser.parse_args()

    if args.training_source == "internationals":
        matches = load_international_results(_ROOT / args.international_results)
    else:
        matches = load_world_cup_min_directory(_ROOT / args.data_dir)
    if args.evaluate == "true":
        if args.training_source == "internationals" and args.bootstrap_calibration == "true":
            result = bootstrap_calibrator_vs_baseline(
                matches,
                calibration_years=args.calibration_years,
            )
            output = _ROOT / "artifacts" / "eval" / "world_cup_calibration_bootstrap.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(result, indent=2))
            print(str(output))
            return
        if args.training_source == "internationals" and args.compare_calibration == "true":
            result = compare_calibration_windows(matches)
            output = _ROOT / "artifacts" / "eval" / "world_cup_calibration_compare.csv"
        elif args.training_source == "internationals" and args.compare_models == "true":
            result = compare_international_models(matches)
            output = _ROOT / "artifacts" / "eval" / "world_cup_model_compare.csv"
        else:
            result = (
                evaluate_international_timeline_holdouts(
                    matches,
                    model_kwargs={"draw_correlation": args.draw_correlation},
                )
                if args.training_source == "internationals"
                else evaluate_tournament_holdouts(matches)
            )
            output = _ROOT / "artifacts" / "eval" / "world_cup_holdout.csv"
        output.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output, index=False)
        print(result.to_string(index=False))
        print(str(output))
        return

    if args.predict_date:
        if args.training_source != "internationals":
            raise SystemExit("--predict-date requires --training-source internationals")
        prediction_date = pd.Timestamp(args.predict_date).normalize()
        all_matches = load_international_results(
            _ROOT / args.international_results,
            completed_only=False,
        )
        fixtures = all_matches[
            all_matches["date"].eq(prediction_date)
            & all_matches["tournament"].astype(str).eq("FIFA World Cup")
            & all_matches["home_goals"].isna()
            & all_matches["away_goals"].isna()
        ].copy()
        if fixtures.empty:
            raise SystemExit(f"no unplayed FIFA World Cup fixtures found for {prediction_date.date()}")
        training = matches[matches["date"] < prediction_date]
        if args.calibrated == "true":
            model, calibrator, _ = fit_timeline_calibrator(
                training,
                calibration_start=prediction_date - pd.DateOffset(years=args.calibration_years),
            )
        else:
            model = WorldCupBaselineModel(draw_correlation=args.draw_correlation).fit(training)
            calibrator = None
        rows = []
        for fixture in fixtures.itertuples(index=False):
            if calibrator is None:
                prediction = model.predict_match(
                    fixture.home_team,
                    fixture.away_team,
                    neutral=bool(fixture.neutral),
                )
            else:
                prediction = predict_calibrated_match(
                    model,
                    calibrator,
                    fixture.home_team,
                    fixture.away_team,
                    neutral=bool(fixture.neutral),
                    importance=float(fixture.importance),
                )
            prediction.pop("score_matrix")
            prediction["date"] = str(prediction_date.date())
            rows.append(prediction)
        result = pd.DataFrame(rows)
        suffix = "_calibrated" if calibrator is not None else ""
        output = (
            _ROOT
            / "artifacts"
            / "predictions"
            / f"world_cup_{prediction_date.date()}{suffix}.csv"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output, index=False)
        print(result.to_string(index=False))
        print(str(output))
        return

    if not args.home_team or not args.away_team:
        raise SystemExit("prediction requires --home-team and --away-team")
    completed = matches
    if "date" in matches.columns:
        completed = matches[matches["date"] <= pd.Timestamp.today().normalize()]
    if args.calibrated == "true":
        cutoff = pd.Timestamp.today().normalize()
        model, calibrator, _ = fit_timeline_calibrator(
            completed,
            calibration_start=cutoff - pd.DateOffset(years=args.calibration_years),
        )
        prediction = predict_calibrated_match(
            model,
            calibrator,
            args.home_team,
            args.away_team,
            neutral=True,
        )
    else:
        model = WorldCupBaselineModel(draw_correlation=args.draw_correlation).fit(completed)
        prediction = model.predict_match(args.home_team, args.away_team, neutral=True)
    prediction.pop("score_matrix")
    print(json.dumps(prediction, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
