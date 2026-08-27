from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from evaluate.competition_holdout import (  # noqa: E402
    run_competition_season_holdouts,
    summarize_competition_holdouts,
)


def project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def render_markdown(payload: dict[str, object]) -> str:
    lines = [
        "# 分赛事赛季留出评估",
        "",
        f"- 数据集：`{payload['data_path']}`",
        f"- 特征版本：`{payload['feature_version']}`",
        f"- 模型：`{payload['model_type']}`",
        "- 正的相对市场差值表示模型弱于市场基线。",
        "",
        "| 赛事 | 留出数 | 测试场次 | 模型 Log Loss | 市场 Log Loss | 相对市场 | 优于市场留出 | 决策 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in payload["competitions"]:
        lines.append(
            f"| {item['competition_id']} | {item['holdouts']} | {item['test_matches']} | "
            f"{item['mean_logloss']:.6f} | {item['mean_market_logloss']:.6f} | "
            f"{item['mean_logloss_vs_market']:+.6f} | {item['holdouts_better_than_market']} | "
            f"{item['decision']} |"
        )
    lines.extend(["", "## 跳过项", ""])
    if payload["skipped"]:
        lines.extend(
            f"- `{item['source_label']}`：{item['reason']}，{item['rows']} 场，{item['season_count']} 个赛季"
            for item in payload["skipped"]
        )
    else:
        lines.append("- 无")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run season holdouts independently for each competition")
    parser.add_argument("--data-path", required=True)
    parser.add_argument("--competition-col", default="league")
    parser.add_argument("--feature-version", choices=["v1", "v4", "v5", "v6", "v7", "v8"], default="v1")
    parser.add_argument("--model-type", choices=["logit", "lightgbm"], default="logit")
    parser.add_argument("--min-train-seasons", type=int, default=2)
    parser.add_argument("--csv-output", required=True)
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--markdown-output", required=True)
    args = parser.parse_args()

    data_path = project_path(args.data_path)
    matches = pd.read_csv(data_path, low_memory=False)
    results, skipped = run_competition_season_holdouts(
        matches,
        competition_col=args.competition_col,
        feature_version=args.feature_version,
        model_type=args.model_type,
        min_train_seasons=args.min_train_seasons,
    )
    summaries = summarize_competition_holdouts(results)
    payload: dict[str, object] = {
        "schema_version": 1,
        "data_path": str(data_path),
        "feature_version": args.feature_version,
        "model_type": args.model_type,
        "promotion_performed": False,
        "competitions": summaries,
        "skipped": skipped,
    }
    csv_output = project_path(args.csv_output)
    json_output = project_path(args.json_output)
    markdown_output = project_path(args.markdown_output)
    for path in (csv_output, json_output, markdown_output):
        path.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(csv_output, index=False)
    json_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_output.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
