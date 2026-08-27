from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


FIELD_GROUPS = {
    "confirmed_lineups": {"lineup_confirmed", "confirmed_starters", "starter_count"},
    "absences": {"absence_impact", "injury_flag", "suspension_count"},
    "prematch_xg": {"prematch_xg_home", "prematch_xg_away", "xg_home", "xg_away"},
    "travel": {"home_travel_km", "away_travel_km", "travel_km_diff"},
    "timezone": {"home_timezone_shift_hours", "away_timezone_shift_hours"},
    "cross_comp_schedule": {"home_cross_comp_matches_7d", "away_cross_comp_matches_7d"},
    "observation_timestamps": {"observed_at", "captured_at", "snapshot_at"},
}
GENERIC_SIGNALS = {
    "confirmed_lineups": {"confirmed_starter"},
    "absences": {"absence"},
    "prematch_xg": {"prematch_xg"},
    "travel": {"travel_km"},
    "timezone": {"timezone_shift_hours"},
    "cross_comp_schedule": {"cross_comp_matches_7d"},
}


def audit_prematch_coverage(
    historical: pd.DataFrame,
    *,
    market_snapshot_history: pd.DataFrame | None = None,
    sporttery_snapshot_index: pd.DataFrame | None = None,
    prematch_intelligence: pd.DataFrame | None = None,
    world_cup_only_asset_count: int = 0,
) -> dict[str, Any]:
    columns = set(historical.columns)
    groups: dict[str, Any] = {}
    for group, aliases in FIELD_GROUPS.items():
        present = sorted(columns & aliases)
        completeness = {
            column: float(pd.to_numeric(historical[column], errors="coerce").notna().mean())
            if column in historical.columns and pd.api.types.is_numeric_dtype(historical[column])
            else float(historical[column].notna().mean())
            for column in present
        }
        groups[group] = {
            "present_columns": present,
            "available": bool(present),
            "column_completeness": completeness,
        }

    stats_columns = {
        "home_shots",
        "away_shots",
        "home_shots_on_target",
        "away_shots_on_target",
        "home_corners",
        "away_corners",
        "home_yellow_cards",
        "away_yellow_cards",
    }
    present_stats = sorted(columns & stats_columns)
    snapshot_audit: dict[str, Any] = {
        "rows": 0,
        "unique_events": 0,
        "kickoff_safe_rows": 0,
        "post_kickoff_or_invalid_rows": 0,
        "date_min": None,
        "date_max": None,
        "usable_for_historical_training": False,
    }
    if market_snapshot_history is not None and not market_snapshot_history.empty:
        snapshots = market_snapshot_history.copy()
        captured = pd.to_datetime(snapshots.get("captured_at"), errors="coerce", utc=True)
        kickoff = pd.to_datetime(
            snapshots.get("commence_time", snapshots.get("utc_date")), errors="coerce", utc=True
        )
        safe = captured.notna() & kickoff.notna() & captured.lt(kickoff)
        snapshot_audit = {
            "rows": int(len(snapshots)),
            "unique_events": int(snapshots.get("event_id", pd.Series(dtype=str)).nunique()),
            "kickoff_safe_rows": int(safe.sum()),
            "post_kickoff_or_invalid_rows": int((~safe).sum()),
            "date_min": captured.min().isoformat() if captured.notna().any() else None,
            "date_max": captured.max().isoformat() if captured.notna().any() else None,
            "usable_for_historical_training": bool(safe.sum() > 0),
        }

    missing_priorities = [group for group, audit in groups.items() if not audit["available"]]
    generic_groups: dict[str, Any] = {}
    if prematch_intelligence is not None and not prematch_intelligence.empty:
        signal = prematch_intelligence.get("signal_type", pd.Series(dtype=str)).astype(str).str.lower()
        for group, allowed in GENERIC_SIGNALS.items():
            mask = signal.isin(allowed)
            generic_groups[group] = {
                "available": bool(mask.any()), "rows": int(mask.sum()),
                "matches": int(prematch_intelligence.loc[mask, "match_id"].nunique()) if "match_id" in prematch_intelligence else 0,
            }
        observed = pd.to_datetime(prematch_intelligence.get("observed_at"), errors="coerce", utc=True)
        generic_groups["observation_timestamps"] = {
            "available": bool(observed.notna().any()), "rows": int(observed.notna().sum()),
            "matches": int(prematch_intelligence.loc[observed.notna(), "match_id"].nunique()) if "match_id" in prematch_intelligence else 0,
        }
    else:
        generic_groups = {group: {"available": False, "rows": 0, "matches": 0}
                          for group in [*GENERIC_SIGNALS, "observation_timestamps"]}
    sporttery_snapshot_audit: dict[str, Any] = {
        "index_rows": 0,
        "unique_snapshots": 0,
        "safe_fixture_observations": 0,
        "unsafe_fixture_observations": 0,
    }
    if sporttery_snapshot_index is not None and not sporttery_snapshot_index.empty:
        index = sporttery_snapshot_index.copy()
        unique = index.drop_duplicates("snapshot_id")
        safe = pd.to_numeric(unique.get("fixtures_before_kickoff_count"), errors="coerce").fillna(0)
        total = pd.to_numeric(unique.get("fixture_count"), errors="coerce").fillna(0)
        sporttery_snapshot_audit = {
            "index_rows": int(len(index)),
            "unique_snapshots": int(unique["snapshot_id"].nunique()),
            "safe_fixture_observations": int(safe.sum()),
            "unsafe_fixture_observations": int((total - safe).clip(lower=0).sum()),
        }
    return {
        "historical_rows": int(len(historical)),
        "historical_columns": int(len(historical.columns)),
        "field_groups": groups,
        "historical_match_stats": {
            "present_columns": present_stats,
            "available": bool(present_stats),
            "usage_gate": "rolling_history_only_post_match_fields_must_be_shifted",
        },
        "market_snapshot_history": snapshot_audit,
        "sporttery_snapshot_archive": sporttery_snapshot_audit,
        "world_cup_only_asset_count": int(world_cup_only_asset_count),
        "generic_prematch_dataset": {
            "exists": prematch_intelligence is not None,
            "rows": int(len(prematch_intelligence)) if prematch_intelligence is not None else 0,
            "has_observation_timestamps": bool(
                prematch_intelligence is not None and "observed_at" in prematch_intelligence.columns
            ),
            "groups": generic_groups,
        },
        "historical_missing_priorities": missing_priorities,
        "generic_missing_priorities": [group for group, item in generic_groups.items() if not item["available"]],
        "missing_priorities": [group for group, item in generic_groups.items() if not item["available"]],
        "model_gate": "blocked_until_timestamped_prematch_coverage_is_sufficient",
    }


def count_world_cup_only_assets(root: str | Path) -> int:
    path = Path(root)
    if not path.exists():
        return 0
    return sum(1 for item in path.rglob("*") if item.is_file() and "world_cup" in item.name.lower())
