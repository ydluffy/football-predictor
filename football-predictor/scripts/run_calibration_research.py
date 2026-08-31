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

from evaluate.calibration_research import run_calibration_research  # noqa: E402


def project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def render_markdown(payload: dict[str, object]) -> str:
    lines = [
        "# 分赛事概率校准研究",
        "",
        f"- 数据集：`{payload['data_path']}`",
        f"- 赛事标签：`{','.join(payload['competition_labels'])}`",
        f"- Bootstrap 次数：{payload['n_bootstrap']}",
        "- 这是研究评估；不会修改生产模型或投注逻辑。",
        "",
        "| 赛事 | 测试场次 | 校准后相对市场均值 | 95% CI | 胜出概率 | 校准 ECE | 市场 ECE | ECE 波动 | 决策 |",
        "| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in payload["competitions"]:
        bootstrap = item["calibrated_bootstrap"]
        lines.append(
            f"| {item['competition_id']} | {item['test_matches']} | "
            f"{bootstrap['mean_logloss_difference']:+.6f} | "
            f"[{bootstrap['ci95_low']:+.6f}, {bootstrap['ci95_high']:+.6f}] | "
            f"{bootstrap['probability_model_better']:.3f} | "
            f"{item['mean_calibrated_ece']:.6f} | {item['mean_market_ece']:.6f} | "
            f"{item['calibrated_ece_std']:.6f} | {item['decision']} |"
        )
        failed = [name for name, passed in item["gates"].items() if not passed]
        lines.append(f"  - 未通过闸门：{', '.join(failed) if failed else '无'}")
    lines.extend(["", "## 结论", ""])
    eligible = [item["competition_id"] for item in payload["competitions"] if item["shadow_eligible"]]
    lines.append(f"- 可进入影子运行：{', '.join(eligible) if eligible else '无'}")
    lines.append("- `promotion_performed=false`。")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run paired bootstrap and calibration-stability gates")
    parser.add_argument(
        "--data-path",
        default="data/processed/historical_matches_europe_extended_candidate.csv",
    )
    parser.add_argument("--competition-labels", default="I1,N1,P1")
    parser.add_argument("--feature-version", default="v1")
    parser.add_argument("--calibration-method", choices=["sigmoid", "isotonic"], default="sigmoid")
    parser.add_argument("--min-train-seasons", type=int, default=2)
    parser.add_argument("--n-bootstrap", type=int, default=5000)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--csv-output", required=True)
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--markdown-output", required=True)
    args = parser.parse_args()

    data_path = project_path(args.data_path)
    labels = [value.strip() for value in args.competition_labels.split(",") if value.strip()]
    fold_results, summaries, skipped = run_calibration_research(
        pd.read_csv(data_path, low_memory=False),
        competition_labels=labels,
        feature_version=args.feature_version,
        calibration_method=args.calibration_method,
        min_train_seasons=args.min_train_seasons,
        n_bootstrap=args.n_bootstrap,
        random_state=args.random_state,
    )
    payload: dict[str, object] = {
        "schema_version": 1,
        "data_path": str(data_path),
        "competition_labels": labels,
        "feature_version": args.feature_version,
        "calibration_method": args.calibration_method,
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
    fold_results.to_csv(csv_output, index=False)
    json_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_output.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
