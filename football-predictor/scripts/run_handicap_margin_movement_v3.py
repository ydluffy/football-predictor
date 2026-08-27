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

from evaluate.handicap_margin_movement_v3 import (  # noqa: E402
    build_movement_model_frame,
    make_movement_margin_model,
    run_handicap_margin_movement_v3,
)


def _path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _settled_shadow_plans(path: Path) -> int:
    if not path.exists() or not path.stat().st_size:
        return 0
    try:
        frame = pd.read_csv(path, low_memory=False)
    except pd.errors.EmptyDataError:
        return 0
    if frame.empty:
        return 0
    for column in ("settlement_status", "status", "result_status"):
        if column in frame.columns:
            return int(frame[column].astype(str).str.lower().isin({"settled", "completed", "已结算"}).sum())
    if "result" in frame.columns:
        return int(frame["result"].astype(str).str.lower().isin({"hit", "miss", "命中", "未中"}).sum())
    return 0


def _markdown(payload: dict[str, object]) -> str:
    report = payload["report"]
    bootstrap = report["bootstrap_vs_v2"]
    lines = [
        "# 外盘盘口变化净胜球 v3 影子回测",
        "",
        "该候选把外盘开盘至赛前终盘的让球线和水位变化转换为净胜球分布，再映射体彩整数让球胜平负。历史回测是欧洲联赛代理验证，不等同于体彩时间对齐实盘证据。",
        "",
        f"- 模式：`{report['mode']}`",
        f"- 时间顺序留出比赛：{report['oos_matches']:,}",
        f"- 相对v2平均Log Loss：{bootstrap['mean_logloss_difference']:+.6f}",
        f"- 95%区间：[{bootstrap['ci95_low']:+.6f}, {bootstrap['ci95_high']:+.6f}]",
        f"- 历史代理统计闸门：{'通过' if report['statistical_gate_passed'] else '未通过'}",
        f"- 体彩时间对齐场次：{report['time_aligned_sporttery_events']}/{report['required_time_aligned_sporttery_events']}",
        f"- 已结算影子方案：{report['settled_shadow_plans']}/{report['required_settled_shadow_plans']}",
        f"- 允许进入生产：{'是' if report['production_promotion_allowed'] else '否'}",
        f"- 决策：`{report['decision']}`",
        "- 生产配置变更：否",
        "",
        "| 体彩让球 | 场景 | v3 Log Loss | v2 Log Loss | 差值 | v3 ECE | v2 ECE |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["handicap_summaries"]:
        lines.append(
            f"| {row['sporttery_handicap']:+d} | {row['scenario_rows']:,} | {row['v3_logloss']:.6f} | "
            f"{row['v2_logloss']:.6f} | {row['logloss_vs_v2']:+.6f} | {row['v3_ece']:.6f} | {row['v2_ece']:.6f} |"
        )
    lines.extend(["", "## 生产闸门", ""])
    for key, value in report["production_gates"].items():
        lines.append(f"- `{key}`：{'通过' if value else '未通过'}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest the v3 handicap movement margin model in shadow mode.")
    parser.add_argument("--config", default="config/handicap_margin_movement_v3.json")
    parser.add_argument("--data-path", default="data/processed/historical_matches_europe_extended_candidate.csv")
    parser.add_argument("--alignment-audit", default="artifacts/data/inner_outer_market_alignment_latest.json")
    parser.add_argument("--shadow-ledger", default="data/manual/shadow_portfolio_ledger_v2.csv")
    parser.add_argument("--n-bootstrap", type=int, default=None)
    parser.add_argument("--predictions-output", required=True)
    parser.add_argument("--folds-output", required=True)
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--markdown-output", required=True)
    parser.add_argument("--model-output", default="")
    parser.add_argument("--model-metadata-output", default="")
    args = parser.parse_args()

    config = json.loads(_path(args.config).read_text(encoding="utf-8"))
    alignment_path = _path(args.alignment_audit)
    alignment = json.loads(alignment_path.read_text(encoding="utf-8")) if alignment_path.exists() else {}
    matches = pd.read_csv(_path(args.data_path), low_memory=False)
    predictions, folds, payload = run_handicap_margin_movement_v3(
        matches,
        model_c=float(config["model_c"]),
        baseline_smoothing=float(config["baseline_smoothing"]),
        alpha_grid=tuple(float(value) for value in config["alpha_grid"]),
        max_alpha_by_handicap={int(key): float(value) for key, value in config["max_alpha_by_handicap"].items()},
        beta_grid=tuple(float(value) for value in config["beta_grid"]),
        max_beta_by_handicap={int(key): float(value) for key, value in config["max_beta_by_handicap"].items()},
        min_validation_improvement=float(config["min_validation_improvement"]),
        max_validation_ece_degradation=float(config["max_validation_ece_degradation"]),
        n_bootstrap=args.n_bootstrap or int(config["n_bootstrap"]),
        time_aligned_events=int(alignment.get("time_aligned_events", 0)),
        required_time_aligned_events=int(config["promotion_gates"]["time_aligned_sporttery_events"]),
        settled_shadow_plans=_settled_shadow_plans(_path(args.shadow_ledger)),
        required_settled_shadow_plans=int(config["promotion_gates"]["settled_shadow_plans"]),
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
        frame, training_audit = build_movement_model_frame(matches)
        model = make_movement_margin_model(c=float(config["model_c"])).fit(frame, frame["margin_class"])
        model_output = _path(args.model_output)
        metadata_output = _path(args.model_metadata_output) if args.model_metadata_output else model_output.with_suffix(".json")
        model_output.parent.mkdir(parents=True, exist_ok=True)
        metadata_output.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, model_output)
        metadata = {
            "schema_version": 1,
            "model_id": config["candidate_id"],
            "created_at": datetime.now().astimezone().isoformat(),
            "deployment_mode": "shadow_only",
            "model_path": str(model_output),
            "data_path": str(_path(args.data_path)),
            "data_sha256": hashlib.sha256(_path(args.data_path).read_bytes()).hexdigest(),
            "training_audit": training_audit,
            "research_decision": payload["report"]["decision"],
            "production_promotion_allowed": False,
            "can_trigger_bet_alone": False,
            "can_write_production_ledger": False,
            "deployment_gate": payload["report"]["deployment_gate"],
        }
        metadata_output.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["report"], ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
