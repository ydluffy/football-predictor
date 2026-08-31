from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from world_cup.data import load_international_results
from world_cup.goal_environment import compare_dynamic_goal_parameters


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--international-results",
        default="data/external/international-results/results.csv",
    )
    args = parser.parse_args()

    matches = load_international_results(_ROOT / args.international_results)
    result = compare_dynamic_goal_parameters(matches)
    output = _ROOT / "artifacts" / "eval" / "world_cup_goal_environment_compare.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)

    development = result[result["holdout_year"].isin([2010, 2014])]
    ranking = (
        development.groupby(
            ["prior_matches", "responsiveness", "min_observed_matches"],
            as_index=False,
        )
        .agg(
            logloss=("logloss", "mean"),
            goal_mae=("goal_mae", "mean"),
            total_goal_nll=("total_goal_nll", "mean"),
            over_2_5_brier=("over_2_5_brier", "mean"),
        )
        .sort_values(["total_goal_nll", "logloss"], kind="mergesort")
    )
    selected_result = ranking.iloc[0]
    selected_totals = ranking.sort_values(
        ["over_2_5_brier", "total_goal_nll"],
        kind="mergesort",
    ).iloc[0]
    validation_result = result[
        result["holdout_year"].isin([2018, 2022])
        & result["prior_matches"].eq(selected_result["prior_matches"])
        & result["responsiveness"].eq(selected_result["responsiveness"])
        & result["min_observed_matches"].eq(selected_result["min_observed_matches"])
    ]
    validation_totals = result[
        result["holdout_year"].isin([2018, 2022])
        & result["prior_matches"].eq(selected_totals["prior_matches"])
        & result["responsiveness"].eq(selected_totals["responsiveness"])
        & result["min_observed_matches"].eq(
            selected_totals["min_observed_matches"]
        )
    ]
    baseline = result[
        result["holdout_year"].isin([2018, 2022])
        & result["responsiveness"].eq(0.0)
        & result["prior_matches"].eq(16.0)
        & result["min_observed_matches"].eq(0)
    ]
    decision = {
        "selection_years": [2010, 2014],
        "validation_years": [2018, 2022],
        "result_probability_candidate": {
            "prior_matches": float(selected_result["prior_matches"]),
            "responsiveness": float(selected_result["responsiveness"]),
            "min_observed_matches": int(selected_result["min_observed_matches"]),
            "development_metrics": {
                key: float(selected_result[key])
                for key in ("logloss", "goal_mae", "total_goal_nll", "over_2_5_brier")
            },
            "validation_metrics": {
                key: float(validation_result[key].mean())
                for key in ("logloss", "goal_mae", "total_goal_nll", "over_2_5_brier")
            },
        },
        "total_goals_candidate": {
            "prior_matches": float(selected_totals["prior_matches"]),
            "responsiveness": float(selected_totals["responsiveness"]),
            "min_observed_matches": int(selected_totals["min_observed_matches"]),
            "development_metrics": {
                key: float(selected_totals[key])
                for key in ("logloss", "goal_mae", "total_goal_nll", "over_2_5_brier")
            },
            "validation_metrics": {
                key: float(validation_totals[key].mean())
                for key in ("logloss", "goal_mae", "total_goal_nll", "over_2_5_brier")
            },
        },
        "validation_baseline": {
            key: float(baseline[key].mean())
            for key in ("logloss", "goal_mae", "total_goal_nll", "over_2_5_brier")
        },
    }
    decision["result_probability_decision"] = (
        "promote"
        if decision["result_probability_candidate"]["validation_metrics"]["logloss"]
        < decision["validation_baseline"]["logloss"]
        else "reject_keep_static"
    )
    totals_validation = decision["total_goals_candidate"]["validation_metrics"]
    decision["total_goals_decision"] = (
        "promote_research_candidate"
        if totals_validation["over_2_5_brier"]
        < decision["validation_baseline"]["over_2_5_brier"]
        and totals_validation["total_goal_nll"]
        < decision["validation_baseline"]["total_goal_nll"]
        else "reject_keep_monitor_only"
    )
    decision_path = (
        _ROOT / "artifacts" / "eval" / "world_cup_goal_environment_decision.json"
    )
    decision_path.write_text(
        json.dumps(decision, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(ranking.to_string(index=False))
    print(json.dumps(decision, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
