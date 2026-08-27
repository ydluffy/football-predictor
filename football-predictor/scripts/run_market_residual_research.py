from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from evaluate.market_residual_research import run_market_residual_research  # noqa: E402


def project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def render_markdown(payload: dict[str, object]) -> str:
    lines = [
        "# 市场残差模型研究",
        "",
        "市场概率保持为基线，模型仅使用非赔率上下文特征进行收缩修正。参数只在外层留出赛季之前的验证赛季选择。",
        "",
        "| 赛事 | 测试场次 | 相对市场 Log Loss | 95% CI | 胜出概率 | 非零修正留出 | 决策 |",
        "| --- | ---: | ---: | --- | ---: | ---: | --- |",
    ]
    for item in payload["competitions"]:
        result = item["bootstrap"]
        lines.append(
            f"| {item['competition_id']} | {item['test_matches']} | "
            f"{result['mean_logloss_difference']:+.6f} | "
            f"[{result['ci95_low']:+.6f}, {result['ci95_high']:+.6f}] | "
            f"{result['probability_model_better']:.3f} | {item['nonzero_strength_holdouts']} | "
            f"{item['decision']} |"
        )
        failed = [name for name, passed in item["gates"].items() if not passed]
        lines.append(f"  - 未通过闸门：{', '.join(failed) if failed else '无'}")
    lines.extend(["", "- 本报告不会修改生产模型、影子配置或投注逻辑。", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate non-market context as a market residual")
    parser.add_argument(
        "--data-path",
        default="data/processed/historical_matches_europe_extended_candidate.csv",
    )
    parser.add_argument("--competition-labels", default="E0,SP1,D1,F1,I1,N1,P1")
    parser.add_argument("--feature-version", default="v7")
    parser.add_argument("--n-bootstrap", type=int, default=5000)
    parser.add_argument("--csv-output", required=True)
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--markdown-output", required=True)
    args = parser.parse_args()

    data_path = project_path(args.data_path)
    labels = [value.strip() for value in args.competition_labels.split(",") if value.strip()]
    folds, summaries, skipped = run_market_residual_research(
        pd.read_csv(data_path, low_memory=False),
        competition_labels=labels,
        feature_version=args.feature_version,
        n_bootstrap=args.n_bootstrap,
    )
    payload: dict[str, object] = {
        "schema_version": 1,
        "data_path": str(data_path),
        "competition_labels": labels,
        "feature_version": args.feature_version,
        "n_bootstrap": args.n_bootstrap,
        "promotion_performed": False,
        "shadow_configuration_written": False,
        "competitions": summaries,
        "skipped": skipped,
    }
    csv_output = project_path(args.csv_output)
    json_output = project_path(args.json_output)
    markdown_output = project_path(args.markdown_output)
    for path in (csv_output, json_output, markdown_output):
        path.parent.mkdir(parents=True, exist_ok=True)
    folds.to_csv(csv_output, index=False)
    json_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_output.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
