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

from world_cup.data import load_international_results
from world_cup.goal_environment import (
    estimate_live_goal_environment,
    over_2_5_probability,
)
from world_cup.live_tracking import combine_completed_results, load_result_overrides
from world_cup.markets import summarize_score_markets
from world_cup.model import WorldCupBaselineModel


TEAM_ZH = {
    "Belgium": "比利时",
    "Egypt": "埃及",
    "Iran": "伊朗",
    "New Zealand": "新西兰",
    "Spain": "西班牙",
    "Cape Verde": "佛得角",
    "Saudi Arabia": "沙特阿拉伯",
    "Uruguay": "乌拉圭",
}


def _normal_result(prediction: dict[str, object]) -> tuple[str, float]:
    probabilities = {
        "主胜": float(prediction["p_home"]),
        "平局": float(prediction["p_draw"]),
        "客胜": float(prediction["p_away"]),
    }
    result = max(probabilities, key=probabilities.get)
    return result, probabilities[result]


def _write_chinese_report(
    result: pd.DataFrame,
    *,
    output: Path,
    home_handicap: float,
) -> None:
    handicap_text = (
        f"主队让 {abs(home_handicap):g} 球"
        if home_handicap < 0
        else f"主队受让 {home_handicap:g} 球"
    )
    lines = [
        f"# 世界杯比分与进球预测：{result.iloc[0]['date']}",
        "",
        f"让球规则：**{handicap_text}**。结算时把让球数加到主队比分，再判断让球主胜、让球平或让球客胜。",
        "",
        "| 比赛 | 普通胜平负 | 两个最可能比分 | 让球判断 | 最可能总进球 | 大于2.5球 | 大于3.5球 |",
        "| --- | --- | --- | --- | ---: | ---: | ---: |",
    ]
    for row in result.itertuples(index=False):
        home = TEAM_ZH.get(row.home_team, row.home_team)
        away = TEAM_ZH.get(row.away_team, row.away_team)
        lines.append(
            f"| {home} vs {away} | {row.normal_recommendation} "
            f"{row.normal_recommendation_probability:.1%} | "
            f"{row.first_score}（{row.first_score_probability:.1%}）、"
            f"{row.second_score}（{row.second_score_probability:.1%}） | "
            f"{row.handicap_recommendation} "
            f"{row.handicap_recommendation_probability:.1%} | "
            f"{int(row.most_likely_total_goals)} 球 "
            f"（{row.most_likely_total_probability:.1%}） | "
            f"{row.over_2_5_probability:.1%} | "
            f"{row.over_3_5_probability:.1%} |"
        )
    lines.extend(
        [
            "",
            "## 如何理解",
            "",
            "- 两个比分是单一比分中概率最高的两个，但精确比分本身通常只有约 10%–15% 概率。",
            "- 让球主胜：主队扣除让球后仍然获胜。",
            "- 让球平：主队扣除让球后双方比分相同。",
            "- 让球客胜：主队扣除让球后落后。",
            "- 总进球建议同时看最可能数量和大于 2.5 球概率，不应只看一个整数。",
            "- 这些是研究概率，不代表确定赛果，也不是投注建议。",
        ]
    )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--predict-date", required=True)
    parser.add_argument(
        "--home-handicap",
        type=float,
        default=-1.0,
        help="home-team handicap; -1 means the home team gives one goal",
    )
    parser.add_argument(
        "--international-results",
        default="data/external/international-results/results.csv",
    )
    parser.add_argument(
        "--overrides",
        default="data/manual/world_cup_results_overrides.csv",
    )
    args = parser.parse_args()

    prediction_date = pd.Timestamp(args.predict_date).normalize()
    all_matches = load_international_results(
        _ROOT / args.international_results,
        completed_only=False,
    )
    overrides = load_result_overrides(_ROOT / args.overrides)
    completed = combine_completed_results(all_matches, overrides)
    current_results = completed[
        completed["tournament"].astype(str).eq("FIFA World Cup")
        & completed["date"].dt.year.eq(prediction_date.year)
        & completed["date"].lt(prediction_date)
    ].copy()
    if current_results.empty:
        raise SystemExit("no completed tournament matches before prediction date")

    tournament_start = current_results["date"].min()
    training = all_matches[
        all_matches["home_goals"].notna()
        & all_matches["away_goals"].notna()
        & all_matches["date"].lt(tournament_start)
    ]
    model = WorldCupBaselineModel().fit(training)
    environment = estimate_live_goal_environment(model, current_results)
    scale = environment.scale()

    fixtures = all_matches[
        all_matches["date"].eq(prediction_date)
        & all_matches["tournament"].astype(str).eq("FIFA World Cup")
        & all_matches["home_goals"].isna()
        & all_matches["away_goals"].isna()
    ]
    rows = []
    for fixture in fixtures.itertuples(index=False):
        static = model.predict_match(
            fixture.home_team,
            fixture.away_team,
            neutral=bool(fixture.neutral),
        )
        dynamic = model.predict_match(
            fixture.home_team,
            fixture.away_team,
            neutral=bool(fixture.neutral),
            goal_scale=scale,
        )
        static_total = float(static["expected_home_goals"]) + float(
            static["expected_away_goals"]
        )
        normal_result, normal_probability = _normal_result(static)
        dynamic_total = float(dynamic["expected_home_goals"]) + float(
            dynamic["expected_away_goals"]
        )
        markets = summarize_score_markets(
            dynamic["score_matrix"],
            home_handicap=args.home_handicap,
        )
        first_score, second_score = markets["top_scorelines"]
        handicap = markets["handicap"]
        totals = markets["total_goals"]
        rows.append(
            {
                "date": str(prediction_date.date()),
                "home_team": fixture.home_team,
                "away_team": fixture.away_team,
                "completed_tournament_matches": environment.observed_matches,
                "dynamic_goal_scale": scale,
                "static_expected_total_goals": static_total,
                "dynamic_expected_total_goals": dynamic_total,
                "static_over_2_5_probability": over_2_5_probability(static_total),
                "dynamic_over_2_5_probability": over_2_5_probability(dynamic_total),
                "normal_recommendation": normal_result,
                "normal_recommendation_probability": normal_probability,
                "normal_home_win": static["p_home"],
                "normal_draw": static["p_draw"],
                "normal_away_win": static["p_away"],
                "first_score": first_score["score"],
                "first_score_probability": first_score["probability"],
                "second_score": second_score["score"],
                "second_score_probability": second_score["probability"],
                "home_handicap": args.home_handicap,
                "handicap_recommendation": handicap["recommended_result"],
                "handicap_recommendation_probability": handicap[
                    "recommended_probability"
                ],
                "handicap_home_win": handicap["handicap_home_win"],
                "handicap_draw": handicap["handicap_draw"],
                "handicap_away_win": handicap["handicap_away_win"],
                "most_likely_total_goals": totals["most_likely_total_goals"],
                "most_likely_total_probability": totals[
                    "most_likely_total_probability"
                ],
                "under_2_5_probability": totals["under_2_5_probability"],
                "over_2_5_probability": totals["over_2_5_probability"],
                "under_3_5_probability": totals["under_3_5_probability"],
                "over_3_5_probability": totals["over_3_5_probability"],
                "total_goals_distribution": json.dumps(
                    totals["exact_total_probabilities"],
                    ensure_ascii=False,
                ),
            }
        )
    result = pd.DataFrame(rows)
    output = (
        _ROOT
        / "artifacts"
        / "predictions"
        / f"world_cup_{prediction_date.date()}_dynamic_totals.csv"
    )
    result.to_csv(output, index=False)
    report_output = (
        _ROOT
        / "artifacts"
        / "predictions"
        / f"世界杯比分与进球预测_{prediction_date.date()}.md"
    )
    _write_chinese_report(
        result,
        output=report_output,
        home_handicap=args.home_handicap,
    )
    print(result.to_string(index=False))
    print(str(output))
    print(str(report_output))


if __name__ == "__main__":
    main()
