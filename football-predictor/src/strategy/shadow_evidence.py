from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from strategy.shadow_portfolio_v2 import ShadowPortfolioPolicy, build_shadow_portfolio


PREDICTION_COLUMNS = [
    "prediction_id", "sales_day", "match_date", "analysis_at", "stage", "model_id",
    "match_id", "match_number", "competition", "kickoff_time", "home_team", "away_team",
    "home_handicap", "prob_home", "prob_draw", "prob_away", "pick", "pick_label", "pick_odds",
    "model_edge", "model_expected_value", "model_usage", "block_reason", "source_captured_at",
    "result_status", "actual_rqspf", "full_time_score", "prediction_correct", "settled_at",
]

PORTFOLIO_COLUMNS = [
    "sales_day", "analysis_at", "candidate_id", "competition", "match_keys", "leg_count",
    "selection", "odds", "model_prob", "conservative_prob", "shadow_stake", "result",
    "payout", "net_profit", "settled_at", "model_id", "config_path", "notes",
    "prediction_id", "pick", "stage", "source_captured_at",
]

PICK_LABEL = {"home": "让胜", "draw": "让平", "away": "让负"}


def _text(value: object) -> str:
    return "" if value is None or pd.isna(value) else str(value).strip()


def _number(value: object, default: float | None = None) -> float | None:
    try:
        parsed = float(value)
        return parsed if pd.notna(parsed) else default
    except (TypeError, ValueError):
        return default


def _stable_match_id(row: pd.Series, sales_day: str) -> str:
    existing = _text(row.get("match_id"))
    if existing:
        return existing
    number = _text(row.get("match_number")).zfill(3)
    return f"{sales_day}|{number}" if sales_day and number else ""


def _prediction_id(model_id: str, analysis_at: str, match_id: str) -> str:
    digest = hashlib.sha256(f"{model_id}|{analysis_at}|{match_id}".encode("utf-8")).hexdigest()[:16]
    return f"SPV2-{digest}"


def _load(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists() or not path.stat().st_size:
        return pd.DataFrame(columns=columns)
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    return frame.reindex(columns=columns)


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    frame.to_csv(part, index=False, encoding="utf-8-sig")
    part.replace(path)


def record_shadow_run(
    predictions: pd.DataFrame,
    *,
    sales_day: str,
    analysis_at: str,
    stage: str,
    model_id: str,
    prediction_ledger_path: str | Path,
    portfolio_ledger_path: str | Path,
    config_path: str | Path,
) -> dict[str, Any]:
    """Persist every pre-match shadow observation and final-stage virtual selections.

    This never writes the production betting ledger.  Blocked rows remain useful
    coverage evidence, while only final-stage model probabilities may create a
    virtual-stake portfolio row.
    """
    prediction_path = Path(prediction_ledger_path)
    portfolio_path = Path(portfolio_ledger_path)
    config_file = Path(config_path)
    config = json.loads(config_file.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for _, item in predictions.fillna("").iterrows():
        match_id = _stable_match_id(item, sales_day)
        prediction_id = _prediction_id(model_id, analysis_at, match_id)
        pick = _text(item.get("handicap_model_pick"))
        pick_label = PICK_LABEL.get(pick, "")
        odds_column = {"home": "rqspf_odds_home", "draw": "rqspf_odds_draw", "away": "rqspf_odds_away"}.get(pick, "")
        probability_column = {
            "home": "handicap_model_probability_home", "draw": "handicap_model_probability_draw",
            "away": "handicap_model_probability_away",
        }.get(pick, "")
        pick_odds = _number(item.get(odds_column)) if odds_column else None
        model_prob = _number(item.get(probability_column)) if probability_column else None
        usage = _text(item.get("handicap_model_usage"))
        row = {
            "prediction_id": prediction_id, "sales_day": sales_day,
            "match_date": _text(item.get("date")), "analysis_at": analysis_at, "stage": stage,
            "model_id": model_id, "match_id": match_id,
            "match_number": _text(item.get("match_number")).zfill(3),
            "competition": _text(item.get("competition")), "kickoff_time": _text(item.get("kickoff_time")),
            "home_team": _text(item.get("home_team")), "away_team": _text(item.get("away_team")),
            "home_handicap": item.get("home_handicap", ""),
            "prob_home": item.get("handicap_model_probability_home", ""),
            "prob_draw": item.get("handicap_model_probability_draw", ""),
            "prob_away": item.get("handicap_model_probability_away", ""),
            "pick": pick, "pick_label": pick_label, "pick_odds": pick_odds if pick_odds is not None else "",
            "model_edge": item.get("handicap_model_edge", ""),
            "model_expected_value": item.get("handicap_model_expected_value", ""),
            "model_usage": usage, "block_reason": _text(item.get("handicap_model_reason")),
            "source_captured_at": _text(item.get("handicap_model_source_captured_at")),
            "result_status": "pending" if usage == "shadow_only" else "not_evaluable",
            "actual_rqspf": "", "full_time_score": "", "prediction_correct": "", "settled_at": "",
        }
        rows.append(row)
        if stage == "final" and usage == "shadow_only" and pick_label and pick_odds and model_prob:
            handicap = int(float(item.get("home_handicap")))
            selection = (
                f"{row['match_number']} {row['home_team']}vs{row['away_team']} "
                f"让球胜平负({handicap:+d}):{pick_label}"
            )
            candidates.append({
                "candidate_id": f"SHADOW-{model_id}-{match_id}", "competition": row["competition"],
                "match_keys": match_id, "leg_count": 1, "selection": selection,
                "odds": pick_odds, "model_prob": model_prob,
                "uncertainty": config["portfolio"].get("probability_haircut", 0.02),
                "probability_source": "shadow_v2", "gate_status": "shadow_eligible",
                "prediction_id": prediction_id, "pick": pick,
                "source_captured_at": row["source_captured_at"],
            })

    new_predictions = pd.DataFrame(rows, columns=PREDICTION_COLUMNS)
    existing_predictions = _load(prediction_path, PREDICTION_COLUMNS)
    combined_predictions = pd.concat([existing_predictions, new_predictions], ignore_index=True)
    combined_predictions = combined_predictions.drop_duplicates("prediction_id", keep="last")
    _atomic_csv(combined_predictions, prediction_path)

    candidate_frame = pd.DataFrame(candidates)
    portfolio, portfolio_audit = build_shadow_portfolio(
        candidate_frame, ShadowPortfolioPolicy(**config["portfolio"])
    ) if not candidate_frame.empty else (pd.DataFrame(), {
        "mode": "shadow_only", "input_rows": 0, "eligible_rows": 0, "selected_rows": 0,
        "rejection_counts": {}, "total_stake": 0.0, "production_change_performed": False,
    })
    existing_portfolio = _load(portfolio_path, PORTFOLIO_COLUMNS)
    new_portfolio_rows: list[dict[str, Any]] = []
    candidate_lookup = {row["candidate_id"]: row for row in candidates}
    for selected in portfolio.to_dict(orient="records"):
        source = candidate_lookup[selected["candidate_id"]]
        new_portfolio_rows.append({
            "sales_day": sales_day, "analysis_at": analysis_at, "candidate_id": selected["candidate_id"],
            "competition": selected["competition"], "match_keys": selected["match_keys"], "leg_count": 1,
            "selection": selected["selection"], "odds": selected["odds"], "model_prob": selected["model_prob"],
            "conservative_prob": selected["conservative_prob"], "shadow_stake": selected["shadow_stake"],
            "result": "pending", "payout": "", "net_profit": "", "settled_at": "",
            "model_id": model_id, "config_path": str(config_file),
            "notes": "virtual stake only; never authorized for production ledger",
            "prediction_id": source["prediction_id"], "pick": source["pick"], "stage": stage,
            "source_captured_at": source["source_captured_at"],
        })
    new_portfolio = pd.DataFrame(new_portfolio_rows, columns=PORTFOLIO_COLUMNS)
    combined_portfolio = pd.concat([existing_portfolio, new_portfolio], ignore_index=True)
    combined_portfolio = combined_portfolio.drop_duplicates("candidate_id", keep="first")
    _atomic_csv(combined_portfolio, portfolio_path)
    portfolio_audit.update({
        "prediction_rows_recorded": int(len(new_predictions)),
        "prediction_ledger_rows": int(len(combined_predictions)),
        "portfolio_rows_appended": int(len(combined_portfolio) - len(existing_portfolio)),
        "portfolio_ledger_rows": int(len(combined_portfolio)),
        "stage": stage, "production_ledger_write_performed": False,
        "prediction_ledger": str(prediction_path), "portfolio_ledger": str(portfolio_path),
    })
    return portfolio_audit


def _normalize(value: object) -> str:
    return re.sub(r"[\s·\-/（）()]", "", _text(value)).lower()


def settle_shadow_evidence(
    *, prediction_ledger_path: str | Path, portfolio_ledger_path: str | Path,
    results: pd.DataFrame, settled_at: str,
) -> dict[str, Any]:
    prediction_path = Path(prediction_ledger_path); portfolio_path = Path(portfolio_ledger_path)
    predictions = _load(prediction_path, PREDICTION_COLUMNS)
    newly_settled = 0
    for index, row in predictions.iterrows():
        if _text(row.get("result_status")) != "pending":
            continue
        candidates = results.copy()
        date = _text(row.get("match_date"))
        if date and "date" in candidates:
            candidates = candidates[candidates["date"].astype(str).eq(date)]
        number = _text(row.get("match_number")).zfill(3)
        candidates = candidates[candidates["match_number"].astype(str).str.endswith(number)]
        home = _normalize(row.get("home_team")); away = _normalize(row.get("away_team"))
        if home and away and not candidates.empty:
            candidates = candidates[
                candidates.apply(lambda item: home in _normalize(item.get("all_home_team", item.get("home_team", "")))
                                 or _normalize(item.get("all_home_team", item.get("home_team", ""))) in home, axis=1)
                & candidates.apply(lambda item: away in _normalize(item.get("all_away_team", item.get("away_team", "")))
                                   or _normalize(item.get("all_away_team", item.get("away_team", ""))) in away, axis=1)
            ]
        if len(candidates) != 1:
            continue
        result = candidates.iloc[0]
        actual = _text(result.get("rqspf_result"))
        score = _text(result.get("full_time_score"))
        if not actual or not score:
            continue
        predictions.at[index, "actual_rqspf"] = actual
        predictions.at[index, "full_time_score"] = score
        predictions.at[index, "prediction_correct"] = str(actual == _text(row.get("pick_label"))).lower()
        predictions.at[index, "result_status"] = "settled"
        predictions.at[index, "settled_at"] = settled_at
        newly_settled += 1
    _atomic_csv(predictions, prediction_path)

    portfolio = _load(portfolio_path, PORTFOLIO_COLUMNS)
    settled_plans = 0
    prediction_status = predictions.set_index("prediction_id") if not predictions.empty else pd.DataFrame()
    for index, row in portfolio.iterrows():
        if _text(row.get("result")) not in {"", "pending"}:
            continue
        prediction_id = _text(row.get("prediction_id"))
        if prediction_status.empty or prediction_id not in prediction_status.index:
            continue
        prediction = prediction_status.loc[prediction_id]
        if isinstance(prediction, pd.DataFrame): prediction = prediction.iloc[0]
        if _text(prediction.get("result_status")) != "settled":
            continue
        hit = _text(prediction.get("prediction_correct")).lower() == "true"
        stake = float(row.get("shadow_stake") or 0); odds = float(row.get("odds") or 0)
        payout = stake * odds if hit else 0.0
        portfolio.at[index, "result"] = "hit" if hit else "miss"
        portfolio.at[index, "payout"] = f"{payout:.2f}"
        portfolio.at[index, "net_profit"] = f"{payout - stake:.2f}"
        portfolio.at[index, "settled_at"] = settled_at
        settled_plans += 1
    _atomic_csv(portfolio, portfolio_path)
    settled = portfolio[portfolio["result"].astype(str).isin(["hit", "miss"])].copy()
    stake = pd.to_numeric(settled.get("shadow_stake"), errors="coerce").fillna(0.0)
    profit = pd.to_numeric(settled.get("net_profit"), errors="coerce").fillna(0.0)
    cumulative = profit.cumsum(); peak = cumulative.cummax().clip(lower=0.0)
    drawdown = cumulative - peak
    return {
        "schema_version": 1, "status": "ok", "newly_settled_predictions": newly_settled,
        "newly_settled_shadow_plans": settled_plans, "settled_prediction_rows": int(predictions["result_status"].eq("settled").sum()),
        "settled_shadow_plans": int(len(settled)), "settled_shadow_stake": round(float(stake.sum()), 2),
        "shadow_net_profit": round(float(profit.sum()), 2),
        "shadow_roi": round(float(profit.sum() / stake.sum()), 6) if stake.sum() else None,
        "shadow_max_drawdown": round(float(drawdown.min()), 2) if not drawdown.empty else None,
        "production_ledger_write_performed": False,
    }
