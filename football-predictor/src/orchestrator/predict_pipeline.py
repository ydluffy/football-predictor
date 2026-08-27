from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from agent.mock_verifier import MockVerifier
from agent.schemas import MatchContext
from config.settings import ensure_project_dirs, get_settings
from evaluate.error_analysis import export_error_analysis_with_risk
from evaluate.metrics import compute_metrics
from evaluate.splitters import time_based_split
from features.basic_features import build_basic_features, build_training_frame
from ingest.load_data import load_matches, load_matches_csv, load_matches_with_meta
from models.baseline_logit import BaselineLogitModel, save_model, train_baseline_logit
from models.calibration import fit_calibrator, predict_calibrated_proba
from evaluate.reliability import build_reliability_table
from models.model_factory import predict_model_proba, save_model as save_any_model, train_model
from evaluate.feature_importance import build_lightgbm_importance_table
from evaluate.shap_analysis import try_build_shap_summary
from evaluate.league_eval import evaluate_by_league
from models.stacking_meta import stacking_meta_features
from models.stacking_oof import stacking_oof_meta_features
from models.artifact_manifest import build_manifest, write_manifest
from utils.logger import configure_logger, get_logger


def _nan_ratio_by_column(df: pd.DataFrame) -> dict[str, float]:
    if df.empty:
        return {}
    ratios: dict[str, float] = {}
    for c in df.columns:
        ratios[str(c)] = float(df[c].isna().mean())
    return ratios


def _step_record(*, name: str, row_count: int, baseline_row_count: int, details: dict[str, object] | None = None) -> dict[str, object]:
    base = int(baseline_row_count)
    cur = int(row_count)
    dropped = int(max(0, base - cur))
    ratio = float(dropped / base) if base else 0.0
    rec: dict[str, object] = {
        "name": str(name),
        "row_count": cur,
        "baseline_row_count": base,
        "dropped_rows": dropped,
        "dropped_ratio": ratio,
    }
    if details:
        rec["details"] = details
    return rec


def train_and_save(*, data_path: Path | None = None) -> dict[str, object]:
    ensure_project_dirs()
    configure_logger()
    log = get_logger()
    settings = get_settings()

    df = load_matches_csv(data_path)
    X, y = build_training_frame(df)
    result = train_baseline_logit(X, y)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    model_path = settings.artifacts_models_dir / f"baseline_logit_{stamp}.pkl"
    save_model(result.model, model_path)

    metrics_path = settings.artifacts_eval_dir / f"baseline_logit_{stamp}.json"
    metrics_payload = {"model_path": str(model_path), "metrics": result.metrics, "features": result.feature_names}
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info("trained_model_path={}", str(model_path))
    log.info("metrics_path={}", str(metrics_path))

    return {"model_path": model_path, "metrics_path": metrics_path, "metrics": result.metrics}


def run_pipeline(
    *,
    data_path: str = "data/raw/sample_matches.csv",
    input_dataset_path: str | None = None,
    feature_version: str = "v2",
    calibration_method: str = "none",
    model_type: str = "logit",
    use_verifier: bool = False,
) -> pd.DataFrame:
    ensure_project_dirs()
    configure_logger()
    log = get_logger()
    settings = get_settings()

    model_name = "baseline_logit_multinomial"
    run_time = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    if calibration_method not in {"none", "sigmoid", "isotonic"}:
        raise ValueError("calibration_method 仅支持 none/sigmoid/isotonic")
    if model_type not in {"logit", "lightgbm", "stacking", "stacking_oof"}:
        raise ValueError("model_type 仅支持 logit/lightgbm/stacking/stacking_oof")
    log.info("model_type={}", model_type)
    if model_type != "lightgbm":
        log.info("lightgbm_feature_importance_skipped model_type={}", model_type)

    chosen = input_dataset_path if input_dataset_path else data_path
    p = Path(chosen)
    if not p.is_absolute():
        p = (settings.project_root / p).resolve()
    if not p.exists():
        raise FileNotFoundError(str(p))
    df_full = load_matches_with_meta(
        str(p),
        extra_columns=[
            "date",
            "league",
            "xg_home",
            "xg_away",
            "injury_flag",
            "line_move",
            "home_goals",
            "away_goals",
        ],
    )
    if feature_version == "v4":
        from features.team_history_features import build_team_history_features

        history_features = build_team_history_features(df_full)
        df_full = pd.concat([df_full, history_features], axis=1)

    steps: list[dict[str, object]] = []
    raw_rows = int(len(df_full))
    steps.append(_step_record(name="raw_loaded_rows", row_count=raw_rows, baseline_row_count=raw_rows))
    steps.append(_step_record(name="after_mapping_rows", row_count=raw_rows, baseline_row_count=raw_rows))
    steps.append(_step_record(name="after_standardize_rows", row_count=raw_rows, baseline_row_count=raw_rows))
    log.info("data_flow.raw_loaded_rows={}", raw_rows)
    log.info("data_flow.input_dataset_path={}", str(p))
    log.info("data_flow.input_dataset_row_count={}", raw_rows)

    if "date" in df_full.columns:
        train_df, test_df = time_based_split(df_full, date_col="date", test_size=0.2)
    else:
        train_df = df_full.reset_index(drop=True)
        test_df = df_full.reset_index(drop=True)

    X_train, y_train, feature_names = build_basic_features(train_df, feature_version=feature_version)
    X_test, y_test, _ = build_basic_features(test_df, feature_version=feature_version)
    feature_rows = int(len(X_train) + len(X_test))
    steps.append(_step_record(name="after_feature_build_rows", row_count=feature_rows, baseline_row_count=raw_rows))

    train_nan_ratio = _nan_ratio_by_column(X_train)
    test_nan_ratio = _nan_ratio_by_column(X_test)
    rows_with_any_nan_train = int(X_train.isna().any(axis=1).sum()) if not X_train.empty else 0
    rows_with_any_nan_test = int(X_test.isna().any(axis=1).sum()) if not X_test.empty else 0
    cols_with_any_nan = sorted({k for k, v in train_nan_ratio.items() if v > 0.0} | {k for k, v in test_nan_ratio.items() if v > 0.0})
    dropna_would_drop = int(rows_with_any_nan_train + rows_with_any_nan_test)
    after_dropna_rows = int(feature_rows - dropna_would_drop)
    steps.append(
        _step_record(
            name="after_dropna_rows",
            row_count=after_dropna_rows,
            baseline_row_count=feature_rows,
            details={
                "would_drop_rows_with_any_nan": dropna_would_drop,
                "rows_with_any_nan_train": rows_with_any_nan_train,
                "rows_with_any_nan_test": rows_with_any_nan_test,
                "columns_with_any_nan": cols_with_any_nan,
                "nan_ratio_by_column_train": train_nan_ratio,
                "nan_ratio_by_column_test": test_nan_ratio,
            },
        )
    )
    steps.append(_step_record(name="train_rows", row_count=int(len(X_train)), baseline_row_count=after_dropna_rows))
    steps.append(_step_record(name="test_rows", row_count=int(len(X_test)), baseline_row_count=after_dropna_rows))
    log.info("data_flow.train_rows={}", int(len(X_train)))
    log.info("data_flow.test_rows={}", int(len(X_test)))

    if model_type == "logit":
        model_name = "baseline_logit_multinomial"
        model_path = settings.logit_model_path
        model = train_model("logit", X_train, y_train)
        save_any_model("logit", model, model_path)
        write_manifest(path=settings.logit_model_manifest_path, manifest=build_manifest(model_type=model_type, feature_version=feature_version, calibration_method=calibration_method, artifact_path=model_path))
        proba_raw = predict_model_proba("logit", model, X_test)
        estimator_for_cal = model._pipeline
    elif model_type == "lightgbm":
        model_name = "lightgbm_multiclass"
        model_path = settings.lightgbm_model_path
        model = train_model("lightgbm", X_train, y_train)
        save_any_model("lightgbm", model, model_path)
        write_manifest(path=settings.lightgbm_model_manifest_path, manifest=build_manifest(model_type=model_type, feature_version=feature_version, calibration_method=calibration_method, artifact_path=model_path))
        proba_raw = predict_model_proba("lightgbm", model, X_test)
        estimator_for_cal = model
        build_lightgbm_importance_table(model, list(X_train.columns))
        shap_df = try_build_shap_summary(model, X_train)
        if shap_df is None:
            log.info("shap_skipped")
    elif model_type == "stacking_oof":
        model_name = "stacking_oof_logit_lightgbm"
        model_path = settings.stacking_oof_meta_model_path
        model = train_model("stacking_oof", X_train, y_train)
        save_any_model("stacking_oof", model, model_path)
        write_manifest(path=settings.stacking_oof_meta_model_manifest_path, manifest=build_manifest(model_type=model_type, feature_version=feature_version, calibration_method=calibration_method, artifact_path=model_path))
        proba_raw = predict_model_proba("stacking_oof", model, X_test)
        estimator_for_cal = model.meta_model
    else:
        model_name = "stacking_prototype_logit_lightgbm"
        model_path = settings.stacking_meta_model_path
        model = train_model("stacking", X_train, y_train)
        save_any_model("stacking", model, model_path)
        write_manifest(path=settings.stacking_meta_model_manifest_path, manifest=build_manifest(model_type=model_type, feature_version=feature_version, calibration_method=calibration_method, artifact_path=model_path))
        proba_raw = predict_model_proba("stacking", model, X_test)
        estimator_for_cal = model.meta_model

    metrics_raw = compute_metrics(y_test, proba_raw)
    log.info("model_path={}", str(model_path))
    log.info("metrics_raw={}", metrics_raw)

    settings.artifacts_eval_dir.mkdir(parents=True, exist_ok=True)
    audit_path = settings.artifacts_eval_dir / "data_flow_audit.json"
    audit_payload: dict[str, object] = {
        "schema_version": "data_flow_audit_v1",
        "run_time": run_time,
        "input_dataset_path": str(p),
        "input_dataset_exists": True,
        "input_dataset_row_count": raw_rows,
        "input_dataset_columns": list(map(str, df_full.columns)),
        "model_type": model_type,
        "feature_version": feature_version,
        "calibration_method": calibration_method,
        "steps": steps,
    }
    audit_path.write_text(json.dumps(audit_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("data_flow_audit_path={}", str(audit_path))

    if calibration_method == "none":
        proba_cal = proba_raw
        metrics_cal = metrics_raw
    else:
        if model_type == "stacking":
            Z_train = stacking_meta_features(model, X_train)
            Z_test = stacking_meta_features(model, X_test)
            calibrator = fit_calibrator(estimator_for_cal, Z_train, y_train, method=calibration_method)
            proba_cal = predict_calibrated_proba(calibrator, Z_test)
        elif model_type == "stacking_oof":
            Z_train = stacking_oof_meta_features(model, X_train)
            Z_test = stacking_oof_meta_features(model, X_test)
            calibrator = fit_calibrator(estimator_for_cal, Z_train, y_train, method=calibration_method)
            proba_cal = predict_calibrated_proba(calibrator, Z_test)
        else:
            calibrator = fit_calibrator(estimator_for_cal, X_train, y_train, method=calibration_method)
            proba_cal = predict_calibrated_proba(calibrator, X_test)
        metrics_cal = compute_metrics(y_test, proba_cal)
        log.info("metrics_calibrated={}", metrics_cal)

    results = proba_raw.copy()
    if "match_id" in test_df.columns:
        results["match_id"] = test_df["match_id"].astype(str).to_numpy()
    if "date" in test_df.columns:
        results["date"] = test_df["date"].astype(str).to_numpy()
    results["actual"] = y_test
    results["model_type"] = model_type
    if "league" in test_df.columns:
        results["league"] = test_df["league"].astype(str).to_numpy()
        base_cols = [c for c in ["match_id", "date"] if c in results.columns]
        results = results[base_cols + ["p_home", "p_draw", "p_away", "actual", "model_type", "league"]]
    else:
        base_cols = [c for c in ["match_id", "date"] if c in results.columns]
        results = results[base_cols + ["p_home", "p_draw", "p_away", "actual", "model_type"]]

    results.to_csv(settings.eval_results_path, index=False)
    reliability_df = build_reliability_table(y_test, proba_cal[["p_home", "p_draw", "p_away"]], n_bins=10)
    reliability_gap_mean = float(reliability_df.loc[reliability_df["sample_count"] > 0, "gap"].mean())

    league_metrics_df: pd.DataFrame | None = None
    if "league" in results.columns:
        league_df = evaluate_by_league(results, league_col="league")
        league_df["run_time"] = run_time
        league_df["model_type"] = model_type
        league_df["feature_version"] = feature_version
        league_df["calibration_method"] = calibration_method
        league_df = league_df[
            ["run_time", "model_type", "feature_version", "calibration_method", "league", "n_samples", "brier", "logloss"]
        ]
        write_header = not settings.eval_league_metrics_path.exists()
        league_df.to_csv(settings.eval_league_metrics_path, index=False, mode="a", header=write_header)
        league_metrics_df = league_df
    else:
        log.info("league_metrics_skipped_missing_league")

    metrics_payload = {
        "run_time": run_time,
        "model_type": model_type,
        "model_name": model_name,
        "n_samples": int(len(results)),
        "brier": float(metrics_raw["brier"]),
        "logloss": float(metrics_raw["logloss"]),
        "input_dataset_path": str(p),
    }
    settings.eval_metrics_path.write_text(json.dumps(metrics_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    summary_row = pd.DataFrame(
        [
            {
                "run_time": run_time,
                "model_type": model_type,
                "model_name": model_name,
                "n_samples": int(len(results)),
                "brier": float(metrics_raw["brier"]),
                "logloss": float(metrics_raw["logloss"]),
                "feature_version": feature_version,
            }
        ]
    )
    write_header = not settings.eval_run_summary_path.exists()
    summary_row.to_csv(settings.eval_run_summary_path, index=False, mode="a", header=write_header)

    compare_row = pd.DataFrame(
        [
            {
                "run_time": run_time,
                "model_type": model_type,
                "feature_version": feature_version,
                "n_features": int(len(feature_names)),
                "n_samples": int(len(results)),
                "brier": float(metrics_raw["brier"]),
                "logloss": float(metrics_raw["logloss"]),
            }
        ]
    )
    write_header = not settings.eval_feature_compare_path.exists()
    compare_row.to_csv(settings.eval_feature_compare_path, index=False, mode="a", header=write_header)

    if calibration_method != "none":
        calibration_row = pd.DataFrame(
            [
                {
                    "run_time": run_time,
                    "model_type": model_type,
                    "feature_version": feature_version,
                    "calibration_method": calibration_method,
                    "n_samples": int(len(results)),
                    "brier_raw": float(metrics_raw["brier"]),
                    "logloss_raw": float(metrics_raw["logloss"]),
                    "brier_calibrated": float(metrics_cal["brier"]),
                    "logloss_calibrated": float(metrics_cal["logloss"]),
                }
            ]
        )
        write_header = not settings.eval_calibration_compare_path.exists()
        calibration_row.to_csv(settings.eval_calibration_compare_path, index=False, mode="a", header=write_header)

    model_compare_row = pd.DataFrame(
        [
            {
                "run_time": run_time,
                "model_type": model_type,
                "feature_version": feature_version,
                "calibration_method": calibration_method,
                "n_features": int(len(feature_names)),
                "n_samples": int(len(results)),
                "brier_raw": float(metrics_raw["brier"]),
                "logloss_raw": float(metrics_raw["logloss"]),
                "brier_calibrated": float(metrics_cal["brier"]),
                "logloss_calibrated": float(metrics_cal["logloss"]),
                "brier": float(metrics_cal["brier"] if calibration_method != "none" else metrics_raw["brier"]),
                "logloss": float(metrics_cal["logloss"] if calibration_method != "none" else metrics_raw["logloss"]),
                "reliability_gap_mean": reliability_gap_mean,
                "notes": ";".join(
                    [
                        s
                        for s in [
                            "prototype_stacking" if model_type == "stacking" else "",
                            "oof_stacking" if model_type == "stacking_oof" else "",
                            "feature_importance_exported" if model_type == "lightgbm" else "",
                            "verifier_enabled" if use_verifier else "",
                        ]
                        if s
                    ]
                ),
            }
        ]
    )
    write_header = not settings.eval_model_compare_path.exists()
    model_compare_row.to_csv(settings.eval_model_compare_path, index=False, mode="a", header=write_header)

    verifier_df: pd.DataFrame | None = None
    if use_verifier:
        verifier_rows: list[dict[str, object]] = []
        verifier = MockVerifier()
        for _, row in test_df.reset_index(drop=True).iterrows():
            date_val = row.get("date")
            if hasattr(date_val, "isoformat"):
                date_str = str(date_val.isoformat())
            else:
                date_str = str(date_val) if date_val is not None else None

            mc = MatchContext(
                match_id=str(row.get("match_id")),
                date=date_str,
                league=str(row.get("league")) if row.get("league") is not None else None,
                home_team=str(row.get("home_team")) if row.get("home_team") is not None else None,
                away_team=str(row.get("away_team")) if row.get("away_team") is not None else None,
                odds_home=float(row.get("odds_home")) if row.get("odds_home") is not None else None,
                odds_draw=float(row.get("odds_draw")) if row.get("odds_draw") is not None else None,
                odds_away=float(row.get("odds_away")) if row.get("odds_away") is not None else None,
                xg_home=float(row.get("xg_home")) if row.get("xg_home") is not None else None,
                xg_away=float(row.get("xg_away")) if row.get("xg_away") is not None else None,
                injury_flag=int(row.get("injury_flag")) if row.get("injury_flag") is not None else None,
                line_move=float(row.get("line_move")) if row.get("line_move") is not None else None,
            )
            bundle = verifier.collect_evidence(mc)
            local_result = verifier.verify_local(bundle)
            global_result = verifier.verify_global(bundle)
            vr = verifier.generate_result(bundle=bundle, local_result=local_result, global_result=global_result)
            verifier_rows.append(
                {
                    "match_id": vr.match_id,
                    "risk_flags": json.dumps(vr.risk_flags, ensure_ascii=False),
                    "source_confidence": float(vr.source_confidence),
                    "manual_review_required": bool(vr.manual_review_required),
                    "summary": str(vr.summary),
                }
            )

        verifier_df = pd.DataFrame(verifier_rows)
        verifier_df.to_csv(settings.eval_verifier_results_path, index=False)
        results_for_analysis = results.copy()
        if "match_id" in test_df.columns:
            results_for_analysis["match_id"] = test_df["match_id"].astype(str).to_numpy()
        if "league" in test_df.columns and "league" not in results_for_analysis.columns:
            results_for_analysis["league"] = test_df["league"].astype(str).to_numpy()
        export_error_analysis_with_risk(results_for_analysis, verifier_results=verifier_df)

    log.info("results_path={}", str(settings.eval_results_path))
    log.info("metrics_path={}", str(settings.eval_metrics_path))
    log.info("run_summary_path={}", str(settings.eval_run_summary_path))
    log.info("feature_compare_path={}", str(settings.eval_feature_compare_path))
    if calibration_method != "none":
        log.info("calibration_compare_path={}", str(settings.eval_calibration_compare_path))
    log.info("reliability_table_path={}", str(settings.eval_reliability_table_path))
    log.info("model_compare_path={}", str(settings.eval_model_compare_path))
    if use_verifier:
        log.info("verifier_results_path={}", str(settings.eval_verifier_results_path))
    return results
