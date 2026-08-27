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
from world_cup.live_tracking import (
    combine_completed_results,
    goal_environment_report,
    load_prediction_files,
    load_result_overrides,
    settle_predictions,
    summarize_settled_predictions,
)


TEAM_ZH = {
    "Germany": "德国",
    "Curaçao": "库拉索",
    "Ivory Coast": "科特迪瓦",
    "Ecuador": "厄瓜多尔",
    "Netherlands": "荷兰",
    "Japan": "日本",
    "Sweden": "瑞典",
    "Tunisia": "突尼斯",
    "Belgium": "比利时",
    "Egypt": "埃及",
    "Iran": "伊朗",
    "New Zealand": "新西兰",
    "Spain": "西班牙",
    "Cape Verde": "佛得角",
    "Saudi Arabia": "沙特阿拉伯",
    "Uruguay": "乌拉圭",
}
RESULT_ZH = {"H": "主队胜", "D": "平局", "A": "客队胜"}


def _percent(value: object) -> str:
    return "" if pd.isna(value) else f"{float(value):.1%}"


def _number(value: object, digits: int = 2) -> str:
    return "—" if pd.isna(value) else f"{float(value):.{digits}f}"


def build_chinese_report(
    settled: pd.DataFrame,
    summaries: dict[str, dict[str, object]],
    environment: dict[str, object],
) -> str:
    lines = [
        "# 2026 世界杯实时预测评估",
        "",
        "## 累计表现",
        "",
        "| 模型版本 | 已结算 | 待结算 | 胜平负命中率 | Log Loss | 实际/预测进球比 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for variant, summary in summaries.items():
        lines.append(
            f"| {variant} | {summary.get('settled_matches', 0)} | "
            f"{summary.get('pending_predictions', 0)} | "
            f"{_percent(summary.get('accuracy'))} | "
            f"{_number(summary.get('mean_logloss'), 4)} | "
            f"{_number(summary.get('goal_ratio_actual_to_expected'), 2)} |"
        )

    completed = settled[settled["settled"]].copy()
    lines.extend(
        [
            "",
            "## 已结算比赛",
            "",
            "| 日期 | 比赛 | 模型 | 预测 | 实际比分 | 是否命中 | 实际结果概率 |",
            "| --- | --- | --- | --- | ---: | --- | ---: |",
        ]
    )
    for row in completed.itertuples(index=False):
        home = TEAM_ZH.get(row.home_team, row.home_team)
        away = TEAM_ZH.get(row.away_team, row.away_team)
        lines.append(
            f"| {row.date.date()} | {home} vs {away} | {row.model_variant} | "
            f"{RESULT_ZH.get(row.predicted_result, row.predicted_result)} | "
            f"{int(row.home_goals)}:{int(row.away_goals)} | "
            f"{'是' if row.correct else '否'} | {_percent(row.actual_probability)} |"
        )

    status_text = {
        "higher_scoring": "本届赛事目前明显偏高进球",
        "lower_scoring": "本届赛事目前明显偏低进球",
        "normal_range": "本届赛事目前处于历史正常范围",
        "insufficient_data": "当前样本不足",
    }[str(environment["status"])]
    lines.extend(
        [
            "",
            "## 进球环境监控",
            "",
            f"- 2026 年已完成世界杯比赛：{environment['current_matches']} 场",
            f"- 2026 年场均进球：{environment['current_goals_per_match']:.2f}",
            f"- 2010–2022 历史场均进球：{environment['historical_goals_per_match']:.2f}",
            f"- 当前与历史比例：{environment['current_to_historical_ratio']:.2f}",
            f"- 判断：**{status_text}**",
            "",
            "该监控只负责发现环境变化，不会在样本很少时自动修改模型参数。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--international-results",
        default="data/external/international-results/results.csv",
    )
    parser.add_argument(
        "--overrides",
        default="data/manual/world_cup_results_overrides.csv",
    )
    parser.add_argument("--predictions-dir", default="artifacts/predictions")
    parser.add_argument("--output-dir", default="artifacts/live")
    args = parser.parse_args()

    all_results = load_international_results(
        _ROOT / args.international_results,
        start_date="2000-01-01",
        completed_only=False,
    )
    overrides = load_result_overrides(_ROOT / args.overrides)
    completed = combine_completed_results(all_results, overrides)
    predictions = load_prediction_files(_ROOT / args.predictions_dir)
    settled = settle_predictions(predictions, completed)
    summaries = {
        variant: summarize_settled_predictions(group)
        for variant, group in settled.groupby("model_variant", sort=True)
    }
    environment = goal_environment_report(completed)

    output_dir = _ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    settled.to_csv(output_dir / "world_cup_prediction_ledger.csv", index=False)
    summary = {
        "models": summaries,
        "goal_environment": environment,
    }
    (output_dir / "world_cup_live_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report = build_chinese_report(settled, summaries, environment)
    (output_dir / "世界杯实时预测评估.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
