from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from world_cup.markets import implied_probabilities_from_decimal_odds


OUTCOME_LABELS = {
    "home": "主胜",
    "draw": "平",
    "away": "客胜",
}

HANDICAP_LABELS = {
    "handicap_home": "让胜",
    "handicap_draw": "让平",
    "handicap_away": "让负",
}


@dataclass(frozen=True)
class MarketResearchSummary:
    rows: int
    finished_rows: int
    model_1x2_accuracy: float | None
    sporttery_1x2_accuracy: float | None
    external_1x2_accuracy: float | None
    model_handicap_accuracy: float | None
    sporttery_handicap_accuracy: float | None
    model_total_bucket_accuracy: float | None


def _as_float(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        result = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(result):
        return None
    return result


def _as_text(value: object) -> str:
    text = "" if value is None else str(value).strip()
    return "" if text.lower() in {"nan", "none"} else text


def _best_key(probabilities: dict[str, object]) -> str:
    parsed = {
        key: value
        for key, raw in probabilities.items()
        if (value := _as_float(raw)) is not None
    }
    if not parsed:
        return ""
    return max(parsed, key=lambda key: parsed[key])


def _probability_gap(
    left: object,
    right: object,
) -> float | None:
    left_value = _as_float(left)
    right_value = _as_float(right)
    if left_value is None or right_value is None:
        return None
    return left_value - right_value


def actual_1x2_result(home_score: object, away_score: object) -> str:
    home = _as_float(home_score)
    away = _as_float(away_score)
    if home is None or away is None:
        return ""
    if home > away:
        return "home"
    if home < away:
        return "away"
    return "draw"


def actual_handicap_result(
    home_score: object,
    away_score: object,
    home_handicap: object,
) -> str:
    home = _as_float(home_score)
    away = _as_float(away_score)
    line = _as_float(home_handicap)
    if home is None or away is None or line is None:
        return ""
    adjusted_margin = home + line - away
    if adjusted_margin > 1e-12:
        return "handicap_home"
    if adjusted_margin < -1e-12:
        return "handicap_away"
    return "handicap_draw"


def total_goals_bucket(home_score: object, away_score: object) -> str:
    home = _as_float(home_score)
    away = _as_float(away_score)
    if home is None or away is None:
        return ""
    total = int(home + away)
    return "7_plus" if total >= 7 else str(total)


def _settlement_hit(predicted: str, actual: str) -> int | None:
    if not predicted or not actual:
        return None
    return int(predicted == actual)


def _mean_hit(frame: pd.DataFrame, column: str) -> float | None:
    if column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    if values.empty:
        return None
    return float(values.mean())


def _load_csv(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path)


def _merge_results(predictions: pd.DataFrame, results: pd.DataFrame) -> pd.DataFrame:
    result_columns = [
        "match_id",
        "home_team",
        "away_team",
        "status",
        "home_score",
        "away_score",
        "winner",
    ]
    available = [column for column in result_columns if column in results.columns]
    results_slim = results[available].copy()
    if "match_id" in predictions.columns and "match_id" in results_slim.columns:
        predictions = predictions.copy()
        predictions["match_id"] = predictions["match_id"].astype(str)
        results_slim["match_id"] = results_slim["match_id"].astype(str)
        return predictions.merge(
            results_slim,
            on="match_id",
            how="left",
            suffixes=("", "_actual"),
        )
    return predictions.merge(
        results_slim,
        on=["home_team", "away_team"],
        how="left",
        suffixes=("", "_actual"),
    )


def build_market_research_dataset(
    predictions: pd.DataFrame,
    results: pd.DataFrame,
) -> pd.DataFrame:
    merged = _merge_results(predictions, results)
    rows: list[dict[str, object]] = []

    for _, match in merged.fillna("").iterrows():
        actual_1x2 = actual_1x2_result(match.get("home_score"), match.get("away_score"))
        actual_handicap = actual_handicap_result(
            match.get("home_score"),
            match.get("away_score"),
            match.get("handicap_line"),
        )
        actual_total_bucket = total_goals_bucket(
            match.get("home_score"),
            match.get("away_score"),
        )

        model_1x2 = _best_key(
            {
                "home": match.get("adjusted_p_home"),
                "draw": match.get("adjusted_p_draw"),
                "away": match.get("adjusted_p_away"),
            }
        )
        sporttery_1x2 = _best_key(
            {
                "home": match.get("spf_market_home_probability"),
                "draw": match.get("spf_market_draw_probability"),
                "away": match.get("spf_market_away_probability"),
            }
        )
        external_1x2 = _best_key(
            {
                "home": match.get("the_odds_api_market_home_probability"),
                "draw": match.get("the_odds_api_market_draw_probability"),
                "away": match.get("the_odds_api_market_away_probability"),
            }
        )
        model_handicap = {
            "handicap_home_win": "handicap_home",
            "handicap_draw": "handicap_draw",
            "handicap_away_win": "handicap_away",
        }.get(_as_text(match.get("handicap_recommended_key")), "")
        sporttery_handicap = _best_key(
            {
                "handicap_home": match.get("handicap_market_home_probability"),
                "handicap_draw": match.get("handicap_market_draw_probability"),
                "handicap_away": match.get("handicap_market_away_probability"),
            }
        )
        model_total_bucket = _as_text(match.get("sporttery_total_goals_best_selection"))

        favorite = sporttery_1x2 or external_1x2 or model_1x2
        sporttery_favorite_probability = (
            match.get(f"spf_market_{favorite}_probability") if favorite else ""
        )
        external_favorite_probability = (
            match.get(f"the_odds_api_market_{favorite}_probability") if favorite else ""
        )

        rows.append(
            {
                "date": match.get("date", ""),
                "match_id": match.get("match_id", ""),
                "stage": match.get("stage", ""),
                "home_team": match.get("home_team", ""),
                "away_team": match.get("away_team", ""),
                "status": match.get("status", ""),
                "home_score": match.get("home_score", ""),
                "away_score": match.get("away_score", ""),
                "actual_1x2": actual_1x2,
                "actual_1x2_label": OUTCOME_LABELS.get(actual_1x2, ""),
                "actual_handicap": actual_handicap,
                "actual_handicap_label": HANDICAP_LABELS.get(actual_handicap, ""),
                "actual_total_goals_bucket": actual_total_bucket,
                "handicap_line": match.get("handicap_line", ""),
                "handicap_label": match.get("handicap_label", ""),
                "model_1x2_pick": model_1x2,
                "model_1x2_label": OUTCOME_LABELS.get(model_1x2, ""),
                "sporttery_1x2_pick": sporttery_1x2,
                "sporttery_1x2_label": OUTCOME_LABELS.get(sporttery_1x2, ""),
                "external_1x2_pick": external_1x2,
                "external_1x2_label": OUTCOME_LABELS.get(external_1x2, ""),
                "model_handicap_pick": model_handicap,
                "model_handicap_label": HANDICAP_LABELS.get(model_handicap, ""),
                "sporttery_handicap_pick": sporttery_handicap,
                "sporttery_handicap_label": HANDICAP_LABELS.get(
                    sporttery_handicap,
                    "",
                ),
                "model_total_goals_pick": model_total_bucket,
                "model_1x2_hit": _settlement_hit(model_1x2, actual_1x2),
                "sporttery_1x2_hit": _settlement_hit(sporttery_1x2, actual_1x2),
                "external_1x2_hit": _settlement_hit(external_1x2, actual_1x2),
                "model_handicap_hit": _settlement_hit(
                    model_handicap,
                    actual_handicap,
                ),
                "sporttery_handicap_hit": _settlement_hit(
                    sporttery_handicap,
                    actual_handicap,
                ),
                "model_total_bucket_hit": _settlement_hit(
                    model_total_bucket,
                    actual_total_bucket,
                ),
                "model_home_probability": match.get("adjusted_p_home", ""),
                "model_draw_probability": match.get("adjusted_p_draw", ""),
                "model_away_probability": match.get("adjusted_p_away", ""),
                "sporttery_home_probability": match.get(
                    "spf_market_home_probability",
                    "",
                ),
                "sporttery_draw_probability": match.get(
                    "spf_market_draw_probability",
                    "",
                ),
                "sporttery_away_probability": match.get(
                    "spf_market_away_probability",
                    "",
                ),
                "external_home_probability": match.get(
                    "the_odds_api_market_home_probability",
                    "",
                ),
                "external_draw_probability": match.get(
                    "the_odds_api_market_draw_probability",
                    "",
                ),
                "external_away_probability": match.get(
                    "the_odds_api_market_away_probability",
                    "",
                ),
                "inner_outer_favorite_probability_gap": _probability_gap(
                    sporttery_favorite_probability,
                    external_favorite_probability,
                ),
                "model_vs_sporttery_home_gap": _probability_gap(
                    match.get("adjusted_p_home"),
                    match.get("spf_market_home_probability"),
                ),
                "model_vs_sporttery_draw_gap": _probability_gap(
                    match.get("adjusted_p_draw"),
                    match.get("spf_market_draw_probability"),
                ),
                "model_vs_sporttery_away_gap": _probability_gap(
                    match.get("adjusted_p_away"),
                    match.get("spf_market_away_probability"),
                ),
                "model_vs_external_home_gap": _probability_gap(
                    match.get("adjusted_p_home"),
                    match.get("the_odds_api_market_home_probability"),
                ),
                "model_vs_external_draw_gap": _probability_gap(
                    match.get("adjusted_p_draw"),
                    match.get("the_odds_api_market_draw_probability"),
                ),
                "model_vs_external_away_gap": _probability_gap(
                    match.get("adjusted_p_away"),
                    match.get("the_odds_api_market_away_probability"),
                ),
                "market_alignment": _market_alignment(
                    model_1x2,
                    sporttery_1x2,
                    external_1x2,
                ),
                "risk_flags": match.get("knockout_calibration_risk_flags", ""),
            }
        )

    return pd.DataFrame(rows)


def _market_alignment(model: str, sporttery: str, external: str) -> str:
    available = [item for item in [model, sporttery, external] if item]
    if len(available) < 2:
        return "insufficient_market"
    if model and sporttery and external and len({model, sporttery, external}) == 1:
        return "model_inner_outer_aligned"
    if sporttery and external and sporttery == external:
        return "inner_outer_aligned_model_disagrees"
    if model and sporttery and model == sporttery:
        return "model_inner_aligned"
    if model and external and model == external:
        return "model_outer_aligned"
    return "three_way_disagreement"


def summarize_market_research(dataset: pd.DataFrame) -> MarketResearchSummary:
    finished = dataset[dataset["actual_1x2"].astype(str).ne("")].copy()
    return MarketResearchSummary(
        rows=int(len(dataset)),
        finished_rows=int(len(finished)),
        model_1x2_accuracy=_mean_hit(finished, "model_1x2_hit"),
        sporttery_1x2_accuracy=_mean_hit(finished, "sporttery_1x2_hit"),
        external_1x2_accuracy=_mean_hit(finished, "external_1x2_hit"),
        model_handicap_accuracy=_mean_hit(finished, "model_handicap_hit"),
        sporttery_handicap_accuracy=_mean_hit(finished, "sporttery_handicap_hit"),
        model_total_bucket_accuracy=_mean_hit(finished, "model_total_bucket_hit"),
    )


def build_market_research_from_files(
    *,
    predictions_path: str | Path,
    results_path: str | Path,
) -> pd.DataFrame:
    return build_market_research_dataset(
        predictions=_load_csv(predictions_path),
        results=_load_csv(results_path),
    )


def render_market_research_report(
    dataset: pd.DataFrame,
    summary: MarketResearchSummary | None = None,
) -> str:
    summary = summary or summarize_market_research(dataset)
    lines = [
        "# 盘口研究报告",
        "",
        "## 样本概况",
        "",
        f"- 研究样本：{summary.rows} 场",
        f"- 已完赛可复盘：{summary.finished_rows} 场",
        f"- 模型胜平负命中率：{_format_rate(summary.model_1x2_accuracy)}",
        f"- 体彩胜平负最低赔率方向命中率：{_format_rate(summary.sporttery_1x2_accuracy)}",
        f"- 外盘胜平负方向命中率：{_format_rate(summary.external_1x2_accuracy)}",
        f"- 模型让球命中率：{_format_rate(summary.model_handicap_accuracy)}",
        f"- 体彩让球最低赔率方向命中率：{_format_rate(summary.sporttery_handicap_accuracy)}",
        f"- 模型总进球单项命中率：{_format_rate(summary.model_total_bucket_accuracy)}",
        "",
        "## 逐场复盘",
        "",
    ]
    finished = dataset[dataset["actual_1x2"].astype(str).ne("")]
    if finished.empty:
        lines.append("暂无已完赛样本。")
    for _, row in finished.iterrows():
        lines.extend(
            [
                f"### {row.get('home_team', '')} vs {row.get('away_team', '')}",
                "",
                f"- 比分：{_as_text(row.get('home_score'))}-{_as_text(row.get('away_score'))}",
                f"- 实际胜平负：{row.get('actual_1x2_label', '')}",
                f"- 模型胜平负：{row.get('model_1x2_label', '')}，命中：{_yes_no(row.get('model_1x2_hit'))}",
                f"- 体彩胜平负：{row.get('sporttery_1x2_label', '') or '无'}，命中：{_yes_no(row.get('sporttery_1x2_hit'))}",
                f"- 外盘胜平负：{row.get('external_1x2_label', '') or '无'}，命中：{_yes_no(row.get('external_1x2_hit'))}",
                f"- 让球盘：{row.get('handicap_label', '')}，实际：{row.get('actual_handicap_label', '')}",
                f"- 模型让球：{row.get('model_handicap_label', '') or '无'}，命中：{_yes_no(row.get('model_handicap_hit'))}",
                f"- 体彩让球：{row.get('sporttery_handicap_label', '') or '无'}，命中：{_yes_no(row.get('sporttery_handicap_hit'))}",
                f"- 实际总进球：{row.get('actual_total_goals_bucket', '')}，模型总进球：{row.get('model_total_goals_pick', '') or '无'}，命中：{_yes_no(row.get('model_total_bucket_hit'))}",
                f"- 内外盘热门概率差：{_format_float(row.get('inner_outer_favorite_probability_gap'))}",
                f"- 市场一致性：{row.get('market_alignment', '')}",
                "",
            ]
        )
    lines.extend(
        [
            "## 研究提示",
            "",
            "- 胜平负命中不等于让球命中，强队赢球和强队穿盘必须分开评估。",
            "- 内外盘同向时，胜负方向可信度通常更高；若让球盘谨慎，则要防强队小胜。",
            "- 内盘比外盘更热某一方，可能是方向信号，也可能意味着赔率价值下降。",
            "- 后续应继续积累初盘、赛前 12 小时、赛前 2 小时和临场盘口快照，研究盘口移动。",
        ]
    )
    return "\n".join(lines) + "\n"


def _format_rate(value: float | None) -> str:
    if value is None:
        return "无样本"
    return f"{value:.1%}"


def _format_float(value: object) -> str:
    parsed = _as_float(value)
    if parsed is None:
        return "无"
    return f"{parsed:+.3f}"


def _yes_no(value: object) -> str:
    parsed = _as_float(value)
    if parsed is None:
        return "无样本"
    return "是" if int(parsed) == 1 else "否"


def implied_probabilities_for_triplet(
    home_odds: object,
    draw_odds: object,
    away_odds: object,
) -> dict[str, float | None]:
    return implied_probabilities_from_decimal_odds(
        {
            "home": home_odds,
            "draw": draw_odds,
            "away": away_odds,
        }
    )
