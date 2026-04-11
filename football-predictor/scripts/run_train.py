from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from config.settings import get_settings
from evaluate.cross_validate import run_time_series_cv
from ingest.load_data import load_matches_with_meta
from orchestrator.predict_pipeline import run_pipeline
from models.artifact_manifest import build_manifest, default_manifest_path_for_artifact, write_manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-type", choices=["logit", "lightgbm", "stacking", "stacking_oof"], default="logit")
    parser.add_argument("--feature-version", choices=["v1", "v2", "v3"], default="v2")
    parser.add_argument("--calibration", choices=["none", "sigmoid", "isotonic"], default="none")
    parser.add_argument("--cv", choices=["false", "true"], default="false")
    parser.add_argument("--use-verifier", choices=["false", "true"], default="false")
    parser.add_argument("--data-path", default="")
    args = parser.parse_args()

    settings = get_settings()
    cv = args.cv == "true"
    use_verifier = args.use_verifier == "true"

    if not cv:
        df = run_pipeline(
            input_dataset_path=(args.data_path if args.data_path else None),
            feature_version=args.feature_version,
            calibration_method=args.calibration,
            model_type=args.model_type,
            use_verifier=use_verifier,
        )
        if args.model_type == "logit":
            model_path = settings.logit_model_path
            manifest_path = settings.logit_model_manifest_path
        elif args.model_type == "lightgbm":
            model_path = settings.lightgbm_model_path
            manifest_path = settings.lightgbm_model_manifest_path
        elif args.model_type == "stacking":
            model_path = settings.stacking_meta_model_path
            manifest_path = settings.stacking_meta_model_manifest_path
        else:
            model_path = settings.stacking_oof_meta_model_path
            manifest_path = settings.stacking_oof_meta_model_manifest_path

        m = build_manifest(model_type=args.model_type, feature_version=args.feature_version, calibration_method=args.calibration, artifact_path=model_path)
        write_manifest(path=manifest_path if manifest_path else default_manifest_path_for_artifact(model_path), manifest=m)
        if args.model_type == "logit":
            print(str(settings.logit_model_path))
        elif args.model_type == "lightgbm":
            print(str(settings.lightgbm_model_path))
        elif args.model_type == "stacking":
            print(str(settings.stacking_meta_model_path))
        else:
            print(str(settings.stacking_oof_meta_model_path))
        print(str(settings.eval_results_path))
        print(str(settings.eval_metrics_path))
        print(str(settings.eval_run_summary_path))
        print(str(settings.eval_feature_compare_path))
        if args.calibration != "none":
            print(str(settings.eval_calibration_compare_path))
        print(str(settings.eval_reliability_table_path))
        print(str(settings.eval_model_compare_path))
        if settings.eval_league_metrics_path.exists():
            print(str(settings.eval_league_metrics_path))
        if settings.eval_verifier_results_path.exists():
            print(str(settings.eval_verifier_results_path))
        payload = json.loads(settings.eval_metrics_path.read_text(encoding="utf-8"))
        print(payload)
        audit_path = settings.artifacts_eval_dir / "data_flow_audit.json"
        if audit_path.exists():
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            steps = audit.get("steps") or []
            by_name = {s.get("name"): s for s in steps if isinstance(s, dict) and s.get("name")}
            raw_rows = int((by_name.get("raw_loaded_rows") or {}).get("row_count") or 0)
            train_rows = int((by_name.get("train_rows") or {}).get("row_count") or 0)
            test_rows = int((by_name.get("test_rows") or {}).get("row_count") or 0)
            input_path = str(audit.get("input_dataset_path") or "")
            max_step = None
            max_drop = -1
            for s in steps:
                if not isinstance(s, dict):
                    continue
                drop = int(s.get("dropped_rows") or 0)
                if drop > max_drop:
                    max_drop = drop
                    max_step = str(s.get("name") or "")
            print(f"data_flow.input_dataset_path={input_path}")
            print(f"data_flow.input_dataset_row_count={raw_rows}")
            print(f"data_flow.raw_rows={raw_rows}")
            print(f"data_flow.train_rows={train_rows}")
            print(f"data_flow.test_rows={test_rows}")
            print(f"data_flow.max_drop_step={max_step}")
        print(df.head().to_string(index=False))
        return

    if args.model_type in {"stacking", "stacking_oof"}:
        raise ValueError("cv=true 暂不支持 stacking/stacking_oof（后续阶段再实现 nested/OOF CV）；请使用 --model-type logit 或 lightgbm")
    if use_verifier:
        print("cv=true 当前不启用 verifier；仅在 cv=false 的单次评估模式下支持 --use-verifier true")

    try:
        data_path = "data/raw/sample_matches.csv"
        df = load_matches_with_meta(
            data_path,
            extra_columns=["date", "league", "xg_home", "xg_away", "injury_flag", "line_move"],
        )
    except FileNotFoundError:
        fallback = settings.project_root.parent / "data" / "sample_matches.csv"
        df = load_matches_with_meta(
            str(fallback),
            extra_columns=["date", "league", "xg_home", "xg_away", "injury_flag", "line_move"],
        )

    out = run_time_series_cv(df, feature_version=args.feature_version, n_splits=3, model_type=args.model_type, calibration_method=args.calibration)
    print(str(settings.eval_cv_results_path))
    if settings.eval_cv_league_metrics_path.exists():
        print(str(settings.eval_cv_league_metrics_path))
    print(out.head().to_string(index=False))


if __name__ == "__main__":
    main()
