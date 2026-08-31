from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from data.competition_registry import load_competition_registry, load_team_alias_registry, normalize_alias
from evaluate.sporttery_handicap_model import (
    aligned_margin_probabilities,
    margin_to_rqspf_probabilities,
)


COMPETITION_SOURCE_LABELS = {
    "ENG_PREMIER_LEAGUE": "E0",
    "ESP_LA_LIGA": "SP1",
    "GER_BUNDESLIGA": "D1",
    "FRA_LIGUE_1": "F1",
    "ITA_SERIE_A": "I1",
    "NED_EREDIVISIE": "N1",
    "POR_PRIMEIRA_LIGA": "P1",
}
LEGACY_TEAM_ALIASES = {
    "法国": "france", "英格兰": "england", "西班牙": "spain", "阿根廷": "argentina",
    "瑞士": "switzerland", "哥伦比亚": "colombia", "挪威": "norway", "美国": "usa",
    "比利时": "belgium", "葡萄牙": "portugal", "巴西": "brazil", "摩洛哥": "morocco", "埃及": "egypt",
}
PROBABILITY_LABELS = ("home", "draw", "away")


def _float(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if np.isfinite(parsed) else None


def _no_vig(values: list[float]) -> np.ndarray:
    inverse = 1.0 / np.asarray(values, dtype=float)
    return inverse / inverse.sum()


def _team_key(value: object) -> str:
    raw = str(value or "").strip()
    legacy = LEGACY_TEAM_ALIASES.get(raw)
    if legacy:
        return normalize_alias(legacy)
    canonical = load_team_alias_registry().resolve(raw)
    return normalize_alias(canonical or raw)


def _external_key(row: pd.Series, side: str) -> str:
    stored = str(row.get(f"{side}_key", "") or "").strip()
    return normalize_alias(stored) if stored else _team_key(row.get(f"{side}_team", ""))


def _competition_source(value: object) -> tuple[str, str]:
    definition = load_competition_registry().resolve(value)
    if definition is None:
        return "UNKNOWN", "competition_not_in_training_domain"
    source = COMPETITION_SOURCE_LABELS.get(definition.competition_id)
    return (source, "") if source else ("UNKNOWN", "competition_not_in_training_domain")


def _timestamp(value: object, *, local_if_naive: bool = False) -> pd.Timestamp | None:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    stamp = pd.Timestamp(parsed)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("Asia/Shanghai" if local_if_naive else "UTC")
    return stamp.tz_convert("UTC")


def _base_output(row: pd.Series) -> dict[str, Any]:
    return {
        "date": row.get("date", ""),
        "match_id": row.get("match_id", ""),
        "match_number": row.get("match_number", ""),
        "competition": row.get("competition", ""),
        "kickoff_time": row.get("kickoff_time", ""),
        "home_team": row.get("home_team", ""),
        "away_team": row.get("away_team", ""),
        "home_handicap": row.get("home_handicap", ""),
        "rqspf_odds_home": row.get("rqspf_odds_home", ""),
        "rqspf_odds_draw": row.get("rqspf_odds_draw", ""),
        "rqspf_odds_away": row.get("rqspf_odds_away", ""),
    }


def predict_current_handicaps(
    markets: pd.DataFrame,
    external_history: pd.DataFrame,
    *,
    model: Any,
    metadata: dict[str, Any],
    analysis_at: object | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    analysis_time = _timestamp(analysis_at, local_if_naive=True) if analysis_at is not None else pd.Timestamp.now(tz="UTC")
    external = external_history.copy().fillna("")
    if not external.empty:
        external["_home_key"] = external.apply(lambda row: _external_key(row, "home"), axis=1)
        external["_away_key"] = external.apply(lambda row: _external_key(row, "away"), axis=1)
        external["_date"] = pd.to_datetime(external["date"], errors="coerce").dt.date.astype(str)
        external["_captured"] = pd.to_datetime(external["captured_at"], errors="coerce", utc=True)
    rows: list[dict[str, Any]] = []
    for _, market in markets.fillna("").iterrows():
        output = _base_output(market)
        handicap_value = _float(market.get("home_handicap"))
        handicap = int(handicap_value) if handicap_value is not None and handicap_value.is_integer() else None
        competition_source, domain_reason = _competition_source(market.get("competition"))
        reason = domain_reason
        if handicap not in {-2, -1, 1, 2}:
            reason = "unsupported_sporttery_handicap"
        date = str(pd.to_datetime(market.get("date"), errors="coerce").date())
        home_key = _team_key(market.get("home_team"))
        away_key = _team_key(market.get("away_team"))
        candidates = external.loc[
            external.get("_date", pd.Series(dtype=str)).eq(date)
            & external.get("_home_key", pd.Series(dtype=str)).eq(home_key)
            & external.get("_away_key", pd.Series(dtype=str)).eq(away_key)
        ].copy() if not external.empty else pd.DataFrame()
        kickoff = _timestamp(market.get("kickoff_time"), local_if_naive=True)
        if not candidates.empty:
            candidates = candidates.loc[candidates["_captured"].notna()]
            candidates = candidates.loc[candidates["_captured"].le(analysis_time)]
            if kickoff is not None:
                candidates = candidates.loc[candidates["_captured"].lt(kickoff)]
            candidates = candidates.sort_values("_captured")
        if candidates.empty:
            reason = reason or "no_safe_external_snapshot"
        latest = candidates.iloc[-1] if not candidates.empty else pd.Series(dtype=object)
        external_odds = [
            _float(latest.get("external_h2h_home_avg_odds")),
            _float(latest.get("external_h2h_draw_avg_odds")),
            _float(latest.get("external_h2h_away_avg_odds")),
            _float(latest.get("external_home_spread_avg_odds")),
            _float(latest.get("external_away_spread_avg_odds")),
            _float(latest.get("external_over_avg_odds")),
            _float(latest.get("external_under_avg_odds")),
            _float(latest.get("external_home_spread_point")),
        ]
        if not candidates.empty and (any(value is None for value in external_odds[:7]) or external_odds[7] is None):
            reason = reason or "external_snapshot_incomplete"
        rq_odds = [
            _float(market.get("rqspf_odds_home")),
            _float(market.get("rqspf_odds_draw")),
            _float(market.get("rqspf_odds_away")),
        ]
        if any(value is None or value <= 1.0 for value in rq_odds):
            reason = reason or "sporttery_rqspf_odds_incomplete"
        if reason:
            output.update({"handicap_model_usage": "blocked", "handicap_model_reason": reason})
            rows.append(output)
            continue

        h2h_probability = _no_vig([float(value) for value in external_odds[:3]])
        ah_probability = _no_vig([float(value) for value in external_odds[3:5]])
        total_probability = _no_vig([float(value) for value in external_odds[5:7]])
        date_stamp = pd.Timestamp(date)
        feature = pd.DataFrame(
            [
                {
                    "opening_ah_line": float(external_odds[7]),
                    "opening_ah_line_key": f"{float(external_odds[7]):+.2f}",
                    "ah_home_probability": ah_probability[0],
                    "ah_away_probability": ah_probability[1],
                    "market_home_probability": h2h_probability[0],
                    "market_draw_probability": h2h_probability[1],
                    "market_away_probability": h2h_probability[2],
                    "over_25_probability": total_probability[0],
                    "under_25_probability": total_probability[1],
                    "season_progress": np.nan,
                    "month_sin": np.sin(2.0 * np.pi * date_stamp.month / 12.0),
                    "month_cos": np.cos(2.0 * np.pi * date_stamp.month / 12.0),
                    "league": competition_source,
                }
            ]
        )
        margin_probability = aligned_margin_probabilities(model, feature)
        model_probability = margin_to_rqspf_probabilities(margin_probability, int(handicap))[0]
        sporttery_probability = _no_vig([float(value) for value in rq_odds])
        stable = int(handicap) in set(metadata.get("stable_handicaps", [-2, -1]))
        weight = float(metadata.get("stable_weight", 0.25) if stable else metadata.get("limited_weight", 0.10))
        usage = "production_auxiliary" if stable else "limited_auxiliary"
        blended = (1.0 - weight) * sporttery_probability + weight * model_probability
        pick_index = int(np.argmax(blended))
        edge = float(model_probability[pick_index] - sporttery_probability[pick_index])
        expected_value = float(model_probability[pick_index] * float(rq_odds[pick_index]) - 1.0)
        output.update(
            {
                "handicap_model_usage": usage,
                "handicap_model_reason": "controlled_user_override",
                "handicap_model_weight": weight,
                "handicap_model_probability_home": model_probability[0],
                "handicap_model_probability_draw": model_probability[1],
                "handicap_model_probability_away": model_probability[2],
                "handicap_blended_probability_home": blended[0],
                "handicap_blended_probability_draw": blended[1],
                "handicap_blended_probability_away": blended[2],
                "handicap_model_pick": PROBABILITY_LABELS[pick_index],
                "handicap_model_edge": edge,
                "handicap_model_expected_value": expected_value,
                "handicap_model_external_line": float(external_odds[7]),
                "handicap_model_source_captured_at": latest.get("captured_at", ""),
                "handicap_model_id": metadata.get("model_id", "sporttery_handicap_margin_v1"),
            }
        )
        rows.append(output)
    result = pd.DataFrame(rows)
    audit = {
        "rows": int(len(result)),
        "production_auxiliary": int(result.get("handicap_model_usage", pd.Series(dtype=str)).eq("production_auxiliary").sum()),
        "limited_auxiliary": int(result.get("handicap_model_usage", pd.Series(dtype=str)).eq("limited_auxiliary").sum()),
        "blocked": int(result.get("handicap_model_usage", pd.Series(dtype=str)).eq("blocked").sum()),
        "analysis_at": analysis_time.isoformat() if analysis_time is not None else "",
        "model_id": metadata.get("model_id", ""),
        "can_trigger_bet_alone": False,
    }
    return result, audit


def load_controlled_model(model_path: str | Path, metadata_path: str | Path) -> tuple[Any, dict[str, Any]]:
    metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    if metadata.get("deployment_mode") != "controlled_auxiliary_user_override":
        raise ValueError("model metadata is not approved for controlled auxiliary deployment")
    return joblib.load(model_path), metadata
