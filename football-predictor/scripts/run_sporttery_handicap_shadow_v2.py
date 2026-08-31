from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import sys
from pathlib import Path

import joblib
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from evaluate.sporttery_handicap_shadow_v2 import run_sporttery_handicap_shadow_v2  # noqa: E402
from evaluate.sporttery_handicap_model import fit_final_margin_model  # noqa: E402


def _path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _markdown(payload: dict[str, object]) -> str:
    report = payload["report"]
    bootstrap = report["bootstrap"]
    lines = [
        "# 体彩整数让球 v2 影子候选",
        "",
        "该候选使用前一赛季内层验证选择模型权重，并向历史盘口基线收缩。所有产物仅用于影子评估。",
        "",
        f"- 模式：`{report['mode']}`",
        f"- 留出比赛：{report['oos_matches']:,}",
        f"- 场景数：{report['scenario_rows']:,}",
        f"- 相对基线 Log Loss：{bootstrap['mean_logloss_difference']:+.6f}",
        f"- 95%区间：[{bootstrap['ci95_low']:+.6f}, {bootstrap['ci95_high']:+.6f}]",
        f"- 统计闸门：{'通过' if report['statistical_gate_passed'] else '未通过'}",
        f"- 决策：`{report['decision']}`",
        f"- 部署闸门：`{report['deployment_gate']}`",
        "- 生产配置变更：否",
        "",
        "| 让球 | 场景 | 影子Log Loss | 基线 | 差值 | 影子ECE |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["handicap_summaries"]:
        lines.append(
            f"| {row['sporttery_handicap']:+d} | {row['scenario_rows']:,} | {row['shadow_logloss']:.6f} | "
            f"{row['baseline_logloss']:.6f} | {row['logloss_vs_baseline']:+.6f} | {row['shadow_ece']:.6f} |"
        )
    lines.extend(["", "## 闸门", ""])
    for key, value in report["gates"].items():
        lines.append(f"- `{key}`：{'通过' if value else '未通过'}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Sporttery handicap v2 in shadow mode")
    parser.add_argument("--config", default="config/shadow_v2.json")
    parser.add_argument("--data-path", default="data/processed/historical_matches_europe_extended_candidate.csv")
    parser.add_argument("--n-bootstrap", type=int, default=None)
    parser.add_argument("--predictions-output", required=True)
    parser.add_argument("--folds-output", required=True)
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--markdown-output", required=True)
    parser.add_argument("--model-output", default="")
    parser.add_argument("--model-metadata-output", default="")
    args = parser.parse_args()

    config = json.loads(_path(args.config).read_text(encoding="utf-8"))
    model_config = config["model"]
    matches = pd.read_csv(_path(args.data_path), low_memory=False)
    predictions, folds, payload = run_sporttery_handicap_shadow_v2(
        matches,
        model_c=float(model_config["model_c"]),
        baseline_smoothing=float(model_config["baseline_smoothing"]),
        alpha_grid=tuple(float(value) for value in model_config["alpha_grid"]),
        max_alpha_by_handicap={int(key): float(value) for key, value in model_config["max_alpha_by_handicap"].items()},
        min_validation_improvement=float(model_config["min_validation_improvement"]),
        n_bootstrap=args.n_bootstrap or int(model_config["n_bootstrap"]),
    )
    payload["report"]["config_path"] = str(_path(args.config))
    outputs = [_path(args.predictions_output), _path(args.folds_output), _path(args.json_output), _path(args.markdown_output)]
    for output in outputs:
        output.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(outputs[0], index=False)
    folds.to_csv(outputs[1], index=False)
    outputs[2].write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    outputs[3].write_text(_markdown(payload), encoding="utf-8")
    if args.model_output:
        model, training_audit = fit_final_margin_model(matches, c=float(model_config["model_c"]))
        model_output = _path(args.model_output)
        metadata_output = _path(args.model_metadata_output) if args.model_metadata_output else model_output.with_suffix(".json")
        model_output.parent.mkdir(parents=True, exist_ok=True)
        metadata_output.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, model_output)
        metadata = {
            "schema_version": 2,
            "model_id": model_config["candidate_id"],
            "created_at": datetime.now().astimezone().isoformat(),
            "deployment_mode": "shadow_only",
            "model_path": str(model_output),
            "data_path": str(_path(args.data_path)),
            "data_sha256": hashlib.sha256(_path(args.data_path).read_bytes()).hexdigest(),
            "training_audit": training_audit,
            "research_decision": payload["report"]["decision"],
            "stable_handicaps": [-2, -1],
            "limited_handicaps": [1, 2],
            "stable_weight": float(model_config["max_alpha_by_handicap"]["-1"]),
            "limited_weight": float(model_config["max_alpha_by_handicap"]["1"]),
            "can_trigger_bet_alone": False,
            "can_write_production_ledger": False,
            "deployment_gate": payload["report"]["deployment_gate"],
        }
        metadata_output.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        payload["report"]["shadow_model_written"] = str(model_output)
        payload["report"]["shadow_metadata_written"] = str(metadata_output)
        outputs[2].write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["report"], ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
