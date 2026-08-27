from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import joblib


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from evaluate.sporttery_handicap_model import (  # noqa: E402
    fit_final_margin_model,
    run_sporttery_handicap_research,
)


def path_for(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def render_markdown(payload: dict[str, object]) -> str:
    report = payload["report"]
    audit = report["audit"]
    lines = [
        "# 体彩整数让球候选模型研究",
        "",
        "模型先预测九档净胜球分布，再转换为体彩 `-2/-1/+1/+2` 的让胜、让平、让负概率。全部特征来自赛前开盘市场；收盘赔率没有进入训练。",
        "",
        "## 数据与留出",
        "",
        f"- 可用比赛：{audit['model_rows']:,} / {audit['source_rows']:,}",
        f"- 滚动留出比赛：{report['oos_matches']:,}",
        f"- 体彩让球场景：{report['scenario_rows']:,}",
        f"- 留出赛季：{', '.join(report['holdout_seasons'])}",
        "",
        "## 分让球评估",
        "",
        "| 体彩让球 | 场景 | 模型Log Loss | 历史盘口基线 | 差值 | 模型Brier | 模型ECE |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["handicap_summaries"]:
        lines.append(
            f"| {row['sporttery_handicap']:+d} | {row['scenario_rows']:,} | {row['model_logloss']:.6f} | "
            f"{row['baseline_logloss']:.6f} | {row['logloss_vs_baseline']:+.6f} | "
            f"{row['model_brier']:.6f} | {row['model_ece']:.6f} |"
        )
    bootstrap = report["bootstrap"]
    lines.extend(
        [
            "",
            "## 闸门结论",
            "",
            f"- 同场聚类Bootstrap相对基线：{bootstrap['mean_logloss_difference']:+.6f}",
            f"- 95%区间：[{bootstrap['ci95_low']:+.6f}, {bootstrap['ci95_high']:+.6f}]",
            f"- 模型优于基线概率：{bootstrap['probability_model_better']:.2%}",
            f"- 统计闸门：{'通过' if report['statistical_gate_passed'] else '未通过'}",
            f"- 研究决策：`{report['decision']}`",
            f"- 最近两季稳定性：{'通过' if report['gates']['last_two_holdouts_all_handicaps_not_worse'] else '未通过'}",
            f"- 部署闸门：`{report['deployment_gate']}`",
            "- 本次不会修改生产模型和投注逻辑。即使统计闸门通过，也必须等历史体彩赔率完成同场时间对齐后才能评估真实价值和ROI。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Research Sporttery integer-handicap probabilities")
    parser.add_argument("--data-path", default="data/processed/historical_matches_europe_extended_candidate.csv")
    parser.add_argument("--handicaps", default="-2,-1,1,2")
    parser.add_argument("--n-bootstrap", type=int, default=2000)
    parser.add_argument("--predictions-output", required=True)
    parser.add_argument("--folds-output", required=True)
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--markdown-output", required=True)
    parser.add_argument("--model-output", default="")
    parser.add_argument("--model-metadata-output", default="")
    args = parser.parse_args()
    handicaps = [int(value.strip()) for value in args.handicaps.split(",") if value.strip()]
    data_path = path_for(args.data_path)
    matches = pd.read_csv(data_path, low_memory=False)
    predictions, folds, payload = run_sporttery_handicap_research(
        matches,
        handicaps=handicaps,
        n_bootstrap=args.n_bootstrap,
    )
    destinations = [path_for(args.predictions_output), path_for(args.folds_output), path_for(args.json_output), path_for(args.markdown_output)]
    for destination in destinations:
        destination.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(destinations[0], index=False)
    folds.to_csv(destinations[1], index=False)
    destinations[2].write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    destinations[3].write_text(render_markdown(payload), encoding="utf-8")
    if args.model_output:
        model, training_audit = fit_final_margin_model(matches)
        model_output = path_for(args.model_output)
        model_output.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, model_output)
        metadata = {
            "schema_version": 1,
            "model_id": "sporttery_handicap_margin_v1",
            "created_at": datetime.now().astimezone().isoformat(),
            "model_path": str(model_output),
            "data_path": str(data_path),
            "data_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
            "training_audit": training_audit,
            "research_decision": payload["report"]["decision"],
            "deployment_mode": "controlled_auxiliary_user_override",
            "stable_handicaps": [-2, -1],
            "limited_handicaps": [1, 2],
            "stable_weight": 0.25,
            "limited_weight": 0.10,
            "can_trigger_bet_alone": False,
        }
        metadata_output = path_for(args.model_metadata_output) if args.model_metadata_output else model_output.with_suffix(".json")
        metadata_output.parent.mkdir(parents=True, exist_ok=True)
        metadata_output.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        payload["report"]["controlled_model_written"] = str(model_output)
        destinations[2].write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["report"], ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
