"""Prospective paper experiments; never writes the production ledger."""
from __future__ import annotations

import re
from itertools import combinations, product
from math import isfinite, log, prod

import pandas as pd

LABELS = {"spf": ("主胜", "平", "客胜"), "rqspf": ("让胜", "让平", "让负")}
KEYS = ("home", "draw", "away")


def number(value: object) -> str:
    match = re.search(r"(\d{1,3})(?:\.0)?$", str(value).strip())
    if not match:
        raise ValueError(f"invalid match number: {value}")
    return match[1].zfill(3)


def timestamp(value: object) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        raise ValueError("missing timestamp")
    return stamp.tz_localize("Asia/Shanghai") if stamp.tzinfo is None else stamp.tz_convert("Asia/Shanghai")


def market_leg(row: dict, play: str, count: int = 1, forced: str = "") -> dict | None:
    odds = []
    for key in KEYS:
        try:
            odd = float(row.get(f"{play}_odds_{key}", ""))
        except (TypeError, ValueError):
            return None
        if not isfinite(odd) or odd <= 1:
            return None
        odds.append(odd)
    probabilities = [(1 / odd) / sum(1 / value for value in odds) for odd in odds]
    source = "market_implied_only"
    if play == "rqspf" and row.get("handicap_model_usage") in {"shadow_only", "production_auxiliary", "limited_auxiliary"}:
        model = [row.get(f"handicap_model_probability_{key}") for key in KEYS]
        try:
            model = [float(value) for value in model]
            if all(isfinite(value) and 0 <= value <= 1 for value in model) and abs(sum(model) - 1) < 0.001:
                probabilities, source = model, "margin_model_market_features"
        except (TypeError, ValueError):
            pass
    indexes = [KEYS.index(forced)] if forced else sorted(range(3), key=lambda i: (-probabilities[i], i))[:count]
    return {
        "match_number": row["match_number"], "competition": row.get("competition", ""),
        "home_team": row["home_team"], "away_team": row["away_team"],
        "kickoff_time": row["kickoff_time"], "home_handicap": row.get("home_handicap", ""),
        "play": play, "probability_source": source,
        "selections": [{"key": KEYS[i], "label": LABELS[play][i], "odds": odds[i], "probability": probabilities[i]} for i in indexes],
    }


def build_experiments(rows: list[dict], config: dict) -> tuple[list[dict], list[dict]]:
    """No probability/price/positive-EV screen; retain source and uncertainty."""
    if config.get('research_focus') == 'independent_comparison_only':
        return [], [{'match_number': row['match_number'], 'reason': 'broad_variants_retired_use_independent_comparison'} for row in rows]
    experiments, skips = [], []
    pools = {family: [] for family in ("spf_direction", "rqspf_direction", "rqspf_exact_margin", "spf_double_cover")}
    for row in rows:
        for family, play, count, forced in (
            ("spf_direction", "spf", 1, ""), ("rqspf_direction", "rqspf", 1, ""),
            ("rqspf_exact_margin", "rqspf", 1, "draw"), ("spf_double_cover", "spf", 2, ""),
        ):
            leg = market_leg(row, play, count, forced)
            if leg is None or (play == "rqspf" and pd.isna(pd.to_numeric(row.get("home_handicap"), errors="coerce"))):
                skips.append({"family": family, "match_number": row["match_number"], "reason": "missing_valid_prices_or_handicap"})
            else:
                pools[family].append(leg)

    def add(family: str, legs: list[dict], structure: str = "double") -> None:
        tickets = []
        for selections in product(*(leg["selections"] for leg in legs)):
            odds = prod(selection["odds"] for selection in selections)
            tickets.append({"keys": [selection["key"] for selection in selections], "odds": odds, "stake": config["unit_stake"]})
        experiments.append({"experiment_id": f"{family}_{structure}_" + "_".join(leg["match_number"] for leg in legs),
            "family": family, "structure": structure, "is_shadow": True, "real_money_allowed": False,
            "ticket_eligibility": "unverified_theoretical" if len(legs) == 1 else "simulation_not_issuance_verification",
            "legs": legs, "tickets": tickets, "stake": sum(ticket["stake"] for ticket in tickets),
            "positive_ev_claim": False, "independent_prediction_count": len(legs)})

    for family, legs in pools.items():
        if not legs:
            skips.append({"family": family, "reason": "no_usable_legs"})
        for leg in legs:
            add(family, [leg], "single_theoretical")
        for pair in list(combinations(legs, 2))[:config["max_pairs_per_family"]]:
            add(family, list(pair))
    singles = pools["spf_direction"]
    doubles = {leg["match_number"]: leg for leg in pools["spf_double_cover"]}
    ranked = sorted(singles, key=lambda leg: (-leg["selections"][0]["probability"], leg["match_number"]))
    if len(ranked) >= 2:
        add("anchor_double_cover", [ranked[0], doubles[ranked[1]["match_number"]]])
    chosen = ranked[:config["max_structure_matches"]]
    if len(chosen) >= 3:
        add("structure_threefold", chosen[:3], "threefold")
    if len(chosen) == 4:
        add("structure_fourfold", chosen, "fourfold")
        for pair in combinations(chosen, 2):
            add("structure_four_all_doubles", list(pair))
    return experiments, skips


def settle(snapshot: dict, results: list[dict]) -> dict:
    settled, pending = [], []
    for experiment in snapshot["experiments"]:
        actual = []
        for leg in experiment["legs"]:
            kickoff_day = timestamp(leg["kickoff_time"]).date().isoformat()
            candidates = [row for row in results if number(row["match_number"]) == leg["match_number"]
                and str(row["home_team"]) == leg["home_team"] and str(row["away_team"]) == leg["away_team"]
                and str(row["date"]) == kickoff_day and row.get("status") in {"已完成", "finished", "completed"}]
            if len(candidates) != 1:
                actual = []
                break
            # Only the official, uniquely matched explicit void declaration
            # authorizes a refund. Missing scores or postponed statuses do not.
            if str(candidates[0].get('full_time_score', '')).strip() == '无效场次':
                actual.append(None)
                continue
            score = re.fullmatch(r"(\d+)[:：](\d+)", str(candidates[0].get("full_time_score", "")))
            if not score:
                actual = []
                break
            margin = int(score[1]) - int(score[2])
            if leg["play"] == "rqspf":
                margin += float(leg["home_handicap"])
            actual.append("home" if margin > 0 else "away" if margin < 0 else "draw")
        if not actual:
            pending.append(experiment["experiment_id"])
            continue
        void_numbers = [leg['match_number'] for leg, outcome in zip(experiment['legs'], actual) if outcome is None]
        payout = 0.0
        for ticket in experiment['tickets']:
            if len(ticket['keys']) != len(actual):
                raise ValueError('ticket key count does not match legs')
            if not all(outcome is None or key == outcome for key, outcome in zip(ticket['keys'], actual)):
                continue
            if void_numbers:
                odds = prod(next(float(s['odds']) for s in leg['selections'] if s['key'] == key)
                    for leg, key, outcome in zip(experiment['legs'], ticket['keys'], actual) if outcome is not None)
            else:
                odds = ticket['odds']
            payout += ticket['stake'] * odds
        settled.append({"experiment_id": experiment["experiment_id"], "family": experiment["family"],
            "stake": experiment["stake"], "payout": round(payout, 2),
            "net": round(payout - experiment["stake"], 2), "hit": payout > 0 and any(x is not None for x in actual),
            "void_match_numbers": void_numbers, 'refund_only': all(x is None for x in actual)})
    groups = {}
    for family in sorted({row["family"] for row in settled}):
        rows = [row for row in settled if row["family"] == family]
        stake, payout = sum(row["stake"] for row in rows), sum(row["payout"] for row in rows)
        groups[family] = {"experiments": len(rows), "hits": sum(row["hit"] for row in rows),
            "stake": stake, "payout": round(payout, 2), "roi": (payout - stake) / stake}
    prediction_scores = []
    names = ("away_4plus", "away_3", "away_2", "away_1", "draw", "home_1", "home_2", "home_3", "home_4plus")
    for match in snapshot.get("matches", []):
        candidates = [row for row in results if number(row["match_number"]) == match["match_number"]
            and str(row["home_team"]) == match["home_team"] and str(row["away_team"]) == match["away_team"]
            and str(row["date"]) == timestamp(match["kickoff_time"]).date().isoformat()
            and row.get("status") in {"已完成", "finished", "completed"}]
        if len(candidates) != 1:
            continue
        score = re.fullmatch(r"(\d+)[:：](\d+)", str(candidates[0].get("full_time_score", "")))
        if not score:
            continue
        try:
            probabilities = [float(match[f"margin_probability_{name}"]) for name in names]
        except (KeyError, TypeError, ValueError):
            continue
        if not all(isfinite(value) and 0 <= value <= 1 for value in probabilities) or abs(sum(probabilities) - 1) > 0.001:
            continue
        margin = int(score[1]) - int(score[2])
        target = min(4, max(-4, margin)) + 4
        prediction_scores.append({"match_number": match["match_number"], "actual_margin": margin,
            "source": match.get("margin_probability_source", "margin_model_market_features"),
            "model_id": match.get("handicap_model_id", "unknown"),
            "margin_log_loss": -log(max(probabilities[target], 1e-15)),
            "margin_brier": sum((probability - (i == target)) ** 2 for i, probability in enumerate(probabilities))})
    return {"protocol_version": snapshot["protocol_version"], "simulation_only": True,
        "settled": settled, "pending": pending, "by_family": groups,
        "prediction_scores": prediction_scores,
        "warning": "Correlated variants are not independent samples; unequal budgets must not be compared by payout alone."}


def summarize(pairs: list[tuple[dict, dict | None]]) -> dict:
    groups = {}
    prediction_scores = {}
    for snapshot, review in sorted(pairs, key=lambda pair: pair[0]["frozen_at"]):
        if review:
            for score in review.get("prediction_scores", []):
                key = (snapshot["sales_day"], score["match_number"], score["model_id"])
                prediction_scores[key] = score
        settled = {row["experiment_id"]: row for row in review["settled"]} if review else {}
        families = {exp["family"] for exp in snapshot["experiments"]}
        for family in families:
            group = groups.setdefault(family, {"plans": 0, "settled_plans": 0, "pending_plans": 0,
                "hits": 0, "stake": 0.0, "payout": 0.0, "sales_days": set(), "events": set(),
                "settled_batches": [], "theoretical_plans": 0})
            experiments = [exp for exp in snapshot["experiments"] if exp["family"] == family]
            group["plans"] += len(experiments)
            done = [settled[exp["experiment_id"]] for exp in experiments if exp["experiment_id"] in settled]
            group["settled_plans"] += len(done)
            group["pending_plans"] += len(experiments) - len(done)
            group["hits"] += sum(row["hit"] for row in done)
            group["theoretical_plans"] += sum(exp["ticket_eligibility"] == "unverified_theoretical" for exp in experiments)
            stake, payout = sum(row["stake"] for row in done), sum(row["payout"] for row in done)
            group["stake"] += stake
            group["payout"] += payout
            if done:
                group["sales_days"].add(snapshot["sales_day"])
                group["events"].update((leg["kickoff_time"], leg["home_team"], leg["away_team"]) for exp in experiments if exp["experiment_id"] in settled for leg in exp["legs"] if leg['match_number'] not in settled[exp['experiment_id']].get('void_match_numbers', []))
            if len(done) == len(experiments) and stake:
                group["settled_batches"].append({"batch": snapshot["sales_day"] + "|" + snapshot["batch_id"],
                    "net": payout - stake, "normalized_12_net": 12 * (payout / stake - 1)})
    all_complete = [set(row["batch"] for row in group["settled_batches"]) for group in groups.values()]
    common = set.intersection(*all_complete) if all_complete else set()
    for group in groups.values():
        group["valid_sales_days"] = len(group.pop("sales_days"))
        group["independent_events"] = len(group.pop("events"))
        group["roi"] = (group["payout"] - group["stake"]) / group["stake"] if group["stake"] else None
        balance = peak = drawdown = 0.0
        for row in group["settled_batches"]:
            balance += row["net"]
            peak = max(peak, balance)
            drawdown = max(drawdown, peak - balance)
        group["complete_batch_max_drawdown"] = round(drawdown, 2)
        comparable = [row for row in group["settled_batches"] if row["batch"] in common]
        group["common_batch_normalized_12_roi"] = sum(row["normalized_12_net"] for row in comparable) / (12 * len(comparable)) if comparable else None
    models = {}
    for score in prediction_scores.values():
        model = models.setdefault(score["model_id"], {"samples": 0, "margin_log_loss": 0.0, "margin_brier": 0.0})
        model["samples"] += 1
        model["margin_log_loss"] += score["margin_log_loss"]
        model["margin_brier"] += score["margin_brier"]
    for model in models.values():
        model["margin_log_loss"] /= model["samples"]
        model["margin_brier"] /= model["samples"]
    return {"simulation_only": True, "families": groups, "common_complete_batches": sorted(common), "model_scores": models,
        "production_promotion_allowed": False,
        "interpretation": "12-unit normalization compares complete common batches; strategy families may select different matches, so differences are not pure structure effects. Theoretical singles are not verified issuable tickets."}
