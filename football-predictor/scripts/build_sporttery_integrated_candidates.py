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


TOTAL_GOAL_SELECTIONS = ["0", "1", "2", "3", "4", "5", "6", "7_plus"]


def _float(value: object, default: float = 0.0) -> float:
    try:
        if value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _nonempty(value: object) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"nan", "none"} else text


def _risk_count(flags: object) -> int:
    text = _nonempty(flags)
    return len([part for part in text.split("|") if part])


def _base_tier(probability: float, expected_value: float | None) -> str:
    if expected_value is not None and expected_value <= 0:
        return "watch"
    if probability >= 0.55:
        return "main_candidate"
    if probability >= 0.30:
        return "single_candidate"
    if probability >= 0.16:
        return "small_stake_candidate"
    return "longshot_only"


def _downgrade(tier: str, steps: int) -> str:
    order = [
        "main_candidate",
        "single_candidate",
        "small_stake_candidate",
        "longshot_only",
        "watch",
    ]
    if tier not in order:
        return tier
    return order[min(order.index(tier) + max(0, steps), len(order) - 1)]


def _final_tier(
    *,
    play_type: str,
    probability: float,
    expected_value: float | None,
    risk_flags: object,
    calibrated_conflict: bool = False,
) -> str:
    tier = _base_tier(probability, expected_value)
    steps = 0
    risks = _risk_count(risk_flags)
    if risks >= 3:
        steps += 1
    if calibrated_conflict:
        steps += 1
    if play_type == "correct_score" and probability < 0.12:
        steps += 1
    if expected_value is not None and expected_value > 0 and probability < 0.08:
        steps += 1
    return _downgrade(tier, steps)


def _match_base(match: pd.Series) -> dict[str, object]:
    return {
        "date": match.get("date", ""),
        "match_id": match.get("match_id", ""),
        "stage": match.get("stage", ""),
        "home_team": match.get("home_team", ""),
        "away_team": match.get("away_team", ""),
        "is_knockout": int(_float(match.get("is_knockout", 0), 0)),
        "risk_flags": match.get("knockout_calibration_risk_flags", ""),
    }


def _add_row(
    rows: list[dict[str, object]],
    match: pd.Series,
    *,
    play_type: str,
    selection: str,
    probability: float,
    odds: object = "",
    market_probability: object = "",
    edge: object = "",
    expected_value: object = "",
    calibrated_selection: object = "",
    notes: str = "",
) -> None:
    ev = None if expected_value == "" else _float(expected_value)
    calibrated = _nonempty(calibrated_selection)
    calibrated_conflict = bool(calibrated and calibrated != selection)
    if play_type == "total_goals" and calibrated:
        if calibrated == "小2.5" and selection in {"0", "1", "2"}:
            calibrated_conflict = False
        elif calibrated == "大2.5" and selection in {"3", "4", "5", "6", "7_plus"}:
            calibrated_conflict = False
    tier = _final_tier(
        play_type=play_type,
        probability=probability,
        expected_value=ev,
        risk_flags=match.get("knockout_calibration_risk_flags", ""),
        calibrated_conflict=calibrated_conflict,
    )
    rows.append(
        {
            **_match_base(match),
            "play_type": play_type,
            "selection": selection,
            "model_probability": probability,
            "odds": odds,
            "market_probability": market_probability,
            "edge": edge,
            "expected_value": expected_value,
            "calibrated_selection": calibrated,
            "calibrated_conflict": int(calibrated_conflict),
            "final_tier": tier,
            "notes": notes,
        }
    )


def build_integrated_candidates(predictions: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    frame = predictions.fillna("")
    for _, match in frame.iterrows():
        # 1X2 model direction, with Sporttery SPF market value if present.
        spf_options = [
            ("主胜", "home", _float(match.get("adjusted_p_home")), "spf_market_home_probability"),
            ("平", "draw", _float(match.get("adjusted_p_draw")), "spf_market_draw_probability"),
            ("客胜", "away", _float(match.get("adjusted_p_away")), "spf_market_away_probability"),
        ]
        label, key, probability, market_col = max(spf_options, key=lambda item: item[2])
        _add_row(
            rows,
            match,
            play_type="spf",
            selection=label,
            probability=probability,
            market_probability=match.get(market_col, ""),
            edge=match.get("spf_value_best_edge", "") if match.get("spf_value_best_key", "") == f"{key}_win" else "",
            expected_value=match.get("spf_value_best_expected_value", "") if match.get("spf_value_best_key", "") == f"{key}_win" else "",
            notes="90分钟胜平负方向",
        )

        # Handicap: include raw model and calibrated recommendation if available.
        handicap_selection = _nonempty(match.get("handicap_recommended_result", ""))
        if handicap_selection:
            probability_map = {
                "让胜": _float(match.get("handicap_home_win_probability")),
                "让平": _float(match.get("handicap_draw_probability")),
                "让负": _float(match.get("handicap_away_win_probability")),
            }
            _add_row(
                rows,
                match,
                play_type="handicap_spf",
                selection=handicap_selection,
                probability=probability_map.get(handicap_selection, 0.0),
                expected_value=match.get("handicap_value_best_expected_value", ""),
                calibrated_selection=match.get("knockout_calibrated_handicap_result", ""),
                notes=str(match.get("handicap_label", "")),
            )

        # Total goals exact selections.
        for selection in TOTAL_GOAL_SELECTIONS:
            probability = _float(
                match.get(f"sporttery_total_goals_{selection}_probability", "")
            )
            odds = match.get(f"sporttery_total_goals_{selection}_odds", "")
            ev = match.get(f"sporttery_total_goals_{selection}_expected_value", "")
            if probability <= 0 or odds == "":
                continue
            _add_row(
                rows,
                match,
                play_type="total_goals",
                selection=selection,
                probability=probability,
                odds=odds,
                market_probability=match.get(
                    f"sporttery_total_goals_{selection}_market_probability",
                    "",
                ),
                edge=match.get(f"sporttery_total_goals_{selection}_edge", ""),
                expected_value=ev,
                calibrated_selection=match.get(
                    "knockout_calibrated_total_goals_pick",
                    "",
                ),
                notes=f"model_double_pick={match.get('sporttery_total_goals_double_pick', '')}",
            )

        # Correct score: current prediction output exposes only best EV selection.
        score_selection = _nonempty(match.get("sporttery_correct_score_best_selection", ""))
        if score_selection:
            # If best EV matches one of top2 scores, use that probability; otherwise leave conservative low default.
            probability = 0.08
            if score_selection == _nonempty(match.get("top_score_1", "")):
                probability = _float(match.get("top_score_1_probability"), 0.08)
            elif score_selection == _nonempty(match.get("top_score_2", "")):
                probability = _float(match.get("top_score_2_probability"), 0.08)
            _add_row(
                rows,
                match,
                play_type="correct_score",
                selection=score_selection,
                probability=probability,
                expected_value=match.get("sporttery_correct_score_best_expected_value", ""),
                edge=match.get("sporttery_correct_score_best_edge", ""),
                notes=f"top_score_1={match.get('top_score_1', '')}; top_score_2={match.get('top_score_2', '')}",
            )

    candidates = pd.DataFrame(rows)
    if candidates.empty:
        return candidates
    tier_rank = {
        "main_candidate": 0,
        "single_candidate": 1,
        "small_stake_candidate": 2,
        "longshot_only": 3,
        "watch": 4,
    }
    candidates["tier_rank"] = candidates["final_tier"].map(tier_rank).fillna(9)
    candidates["expected_value_sort"] = pd.to_numeric(
        candidates["expected_value"],
        errors="coerce",
    ).fillna(-999)
    candidates["probability_sort"] = pd.to_numeric(
        candidates["model_probability"],
        errors="coerce",
    ).fillna(0)
    return candidates.sort_values(
        ["tier_rank", "expected_value_sort", "probability_sort"],
        ascending=[True, False, False],
    ).drop(columns=["tier_rank", "expected_value_sort", "probability_sort"]).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", required=True)
    parser.add_argument(
        "--output",
        default="artifacts/predictions/sporttery_integrated_candidates.csv",
    )
    parser.add_argument(
        "--audit-output",
        default="artifacts/predictions/sporttery_integrated_candidates.json",
    )
    args = parser.parse_args()

    predictions_path = _ROOT / args.predictions
    predictions = pd.read_csv(predictions_path)
    candidates = build_integrated_candidates(predictions)

    output_path = _ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(output_path, index=False, encoding="utf-8-sig")
    audit = {
        "predictions": str(predictions_path),
        "prediction_matches": int(len(predictions)),
        "candidate_rows": int(len(candidates)),
        "tier_counts": {
            str(key): int(value)
            for key, value in candidates.get("final_tier", pd.Series(dtype=str))
            .value_counts()
            .sort_index()
            .items()
        },
        "play_type_counts": {
            str(key): int(value)
            for key, value in candidates.get("play_type", pd.Series(dtype=str))
            .value_counts()
            .sort_index()
            .items()
        },
        "output": str(output_path),
    }
    audit_path = _ROOT / args.audit_output
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
