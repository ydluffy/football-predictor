from __future__ import annotations

from typing import Any

import pandas as pd

from data.competition_registry import CompetitionRegistry, load_competition_registry
from evaluate.season_holdout import run_season_holdout


def run_competition_season_holdouts(
    matches: pd.DataFrame,
    *,
    competition_col: str = "league",
    feature_version: str = "v1",
    model_type: str = "logit",
    min_train_seasons: int = 2,
    registry: CompetitionRegistry | None = None,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    required = {competition_col, "season"}
    missing = required - set(matches.columns)
    if missing:
        raise ValueError(f"missing competition holdout columns: {sorted(missing)}")
    registry = registry or load_competition_registry()
    frames: list[pd.DataFrame] = []
    skipped: list[dict[str, Any]] = []
    for label, group in matches.groupby(competition_col, dropna=False, sort=True):
        seasons = sorted(group["season"].dropna().astype(str).unique().tolist())
        if len(seasons) <= int(min_train_seasons):
            skipped.append(
                {
                    "source_label": str(label),
                    "rows": int(len(group)),
                    "season_count": len(seasons),
                    "reason": "insufficient_seasons",
                }
            )
            continue
        result = run_season_holdout(
            group.reset_index(drop=True),
            feature_version=feature_version,
            model_type=model_type,
            min_train_seasons=min_train_seasons,
        )
        metadata = registry.annotate(label)
        result.insert(0, "source_label", str(label))
        result.insert(0, "competition_id", str(metadata["competition_id"]))
        result["model_group"] = str(metadata["model_group"])
        frames.append(result)
    if not frames:
        return pd.DataFrame(), skipped
    return pd.concat(frames, ignore_index=True), skipped


def summarize_competition_holdouts(results: pd.DataFrame) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    if results.empty:
        return summaries
    for (competition_id, source_label), group in results.groupby(
        ["competition_id", "source_label"], sort=True
    ):
        mean_delta = float(group["logloss_vs_market"].mean())
        brier_delta = float(group["brier_vs_market"].mean())
        better = int((group["logloss_vs_market"] < 0.0).sum())
        holdouts = int(len(group))
        eligible = bool(mean_delta <= 0.0 and better >= 2)
        summaries.append(
            {
                "competition_id": str(competition_id),
                "source_label": str(source_label),
                "holdouts": holdouts,
                "test_matches": int(group["test_size"].sum()),
                "mean_logloss": float(group["logloss"].mean()),
                "mean_market_logloss": float(group["market_logloss"].mean()),
                "mean_logloss_vs_market": mean_delta,
                "mean_brier_vs_market": brier_delta,
                "holdouts_better_than_market": better,
                "calibration_research_eligible": eligible,
                "decision": "calibration_research_eligible" if eligible else "not_promoted",
            }
        )
    return summaries
