from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from evaluate.metrics import compute_metrics
from features.basic_features import build_basic_features
from features.schedule_features import build_schedule_features
from features.team_history_features import build_team_history_features
from models.model_factory import predict_model_proba, train_model


FEATURE_SETS = {
    "base": [],
    "net_sot": ["net_shots_on_target_diff_5"],
    "net_shots": ["net_shots_diff_5"],
    "net_corners": ["net_corners_diff_5"],
    "net_sot_shots": ["net_shots_on_target_diff_5", "net_shots_diff_5"],
    "net_all": [
        "net_shots_on_target_diff_5",
        "net_shots_diff_5",
        "net_corners_diff_5",
    ],
    "v4_net_sot": [
        "goals_for_diff_5",
        "goals_against_diff_5",
        "net_shots_on_target_diff_5",
    ],
    "cards": ["cards_diff_5"],
    "rest_diff": ["rest_days_diff"],
    "rest_days": ["home_rest_days", "away_rest_days", "rest_days_diff"],
    "congestion_7d": ["matches_7d_diff"],
    "congestion_14d": ["matches_14d_diff"],
    "short_rest": ["short_rest_diff"],
    "schedule_compact": [
        "rest_days_diff",
        "matches_7d_diff",
        "matches_14d_diff",
        "short_rest_diff",
    ],
    "v4_schedule": [
        "goals_for_diff_5",
        "goals_against_diff_5",
        "rest_days_diff",
        "matches_7d_diff",
        "matches_14d_diff",
        "short_rest_diff",
    ],
}


def _evaluate(data: pd.DataFrame, feature_columns: list[str], min_train_seasons: int) -> tuple[float, int]:
    base, y, _ = build_basic_features(data, feature_version="v1")
    history = build_team_history_features(data)
    schedule = build_schedule_features(data)
    available = pd.concat([history, schedule], axis=1)
    X = pd.concat([base, available[feature_columns]], axis=1)
    seasons = sorted(data["season"].astype(str).unique())
    losses: list[float] = []
    sizes: list[int] = []

    for holdout_index in range(min_train_seasons, len(seasons)):
        holdout = seasons[holdout_index]
        train_mask = data["season"].astype(str).isin(seasons[:holdout_index])
        test_mask = data["season"].astype(str).eq(holdout)
        model = train_model("logit", X.loc[train_mask], y.loc[train_mask])
        proba = predict_model_proba("logit", model, X.loc[test_mask])
        losses.append(float(compute_metrics(y.loc[test_mask], proba)["logloss"]))
        sizes.append(int(test_mask.sum()))

    return float(np.average(losses, weights=sizes)), int(sum(sizes))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-path", default="data/processed/historical_matches_trainable.csv")
    parser.add_argument("--min-train-seasons", type=int, default=2)
    parser.add_argument("--output-path", default="artifacts/eval/feature_ablation_v5.csv")
    parser.add_argument("--feature-sets", default="")
    args = parser.parse_args()

    data = pd.read_csv(_ROOT / args.data_path, low_memory=False)
    data = data.sort_values(["date", "match_id"], kind="mergesort").reset_index(drop=True)
    scopes = {
        "all": data,
        "E0-E3": data[data["league"].isin(["E0", "E1", "E2", "E3"])].reset_index(drop=True),
    }
    selected = FEATURE_SETS
    if args.feature_sets:
        names = [name.strip() for name in args.feature_sets.split(",") if name.strip()]
        unknown = [name for name in names if name not in FEATURE_SETS]
        if unknown:
            raise ValueError(f"unknown feature sets: {unknown}")
        selected = {name: FEATURE_SETS[name] for name in names}
        if "base" not in selected:
            selected = {"base": FEATURE_SETS["base"], **selected}

    rows = []
    for scope, scoped_data in scopes.items():
        for name, columns in selected.items():
            logloss, test_size = _evaluate(scoped_data, columns, args.min_train_seasons)
            rows.append(
                {
                    "scope": scope,
                    "feature_set": name,
                    "features": ",".join(columns),
                    "weighted_logloss": logloss,
                    "test_size": test_size,
                }
            )

    out = pd.DataFrame(rows)
    base_by_scope = out[out["feature_set"] == "base"].set_index("scope")["weighted_logloss"]
    out["logloss_vs_base"] = out.apply(
        lambda row: float(row["weighted_logloss"] - base_by_scope.loc[row["scope"]]),
        axis=1,
    )
    output = _ROOT / args.output_path
    output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output, index=False)
    print(str(output))
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
