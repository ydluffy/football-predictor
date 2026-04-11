from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    project_root: Path = Field(default_factory=Path)
    data_dir: Path
    data_raw_dir: Path
    data_interim_dir: Path
    data_processed_dir: Path
    data_templates_dir: Path
    data_mock_dir: Path
    data_external_dir: Path
    data_ingested_dir: Path
    data_mappings_dir: Path
    artifacts_dir: Path
    artifacts_models_dir: Path
    artifacts_eval_dir: Path
    artifacts_logs_dir: Path
    artifacts_agent_dir: Path
    agent_state_db_path: Path
    agent_runs_dir: Path
    artifacts_research_director_dir: Path
    artifacts_research_dir: Path
    artifacts_research_reports_dir: Path
    artifacts_research_registry_dir: Path
    artifacts_research_schedules_dir: Path
    research_director_state_db_path: Path
    research_director_runs_dir: Path
    research_director_step_records_dir: Path
    research_director_audit_dir: Path
    research_execution_history_path: Path
    research_latest_execution_summary_path: Path
    research_daily_prediction_report_json_path: Path
    research_daily_prediction_report_md_path: Path
    research_post_match_report_json_path: Path
    research_post_match_report_md_path: Path
    research_model_registry_path: Path
    research_current_model_pointer_path: Path
    research_registry_events_path: Path
    research_scheduler_state_path: Path
    research_scheduler_history_path: Path
    research_scheduler_config_path: Path
    logit_model_path: Path
    logit_model_manifest_path: Path
    lightgbm_model_path: Path
    lightgbm_model_manifest_path: Path
    baseline_model_path: Path
    lgbm_model_path: Path
    stacking_logit_model_path: Path
    stacking_lightgbm_model_path: Path
    stacking_meta_model_path: Path
    stacking_meta_model_manifest_path: Path
    stacking_oof_logit_model_path: Path
    stacking_oof_lightgbm_model_path: Path
    stacking_oof_meta_model_path: Path
    stacking_oof_meta_model_manifest_path: Path
    eval_results_path: Path
    eval_metrics_path: Path
    eval_run_summary_path: Path
    eval_feature_compare_path: Path
    eval_phase3_time_split_path: Path
    eval_phase3_cv_folds_path: Path
    eval_phase3_cv_summary_path: Path
    eval_phase3_reliability_path: Path
    eval_cv_results_path: Path
    eval_cv_league_metrics_path: Path
    eval_calibration_compare_path: Path
    eval_reliability_table_path: Path
    eval_model_compare_path: Path
    eval_lightgbm_feature_importance_path: Path
    eval_league_metrics_path: Path
    eval_lightgbm_shap_summary_path: Path
    eval_verifier_report_path: Path
    eval_high_confidence_errors_path: Path
    eval_underestimated_draws_path: Path
    eval_verifier_results_path: Path
    eval_error_analysis_with_risk_path: Path
    data_matches_template_path: Path
    data_mock_matches_path: Path
    eval_data_quality_report_path: Path
    eval_data_missing_report_path: Path
    eval_dataset_validation_path: Path
    eval_dataset_missing_report_path: Path
    data_ingest_input_default_path: Path
    data_ingest_output_path: Path
    eval_ingest_mapping_record_path: Path
    eval_ingest_validation_path: Path
    eval_ingest_missing_report_path: Path
    eval_import_summary_path: Path
    eval_field_mapping_report_path: Path

    model_config = {"arbitrary_types_allowed": True}


def _resolve_project_root() -> Path:
    env_root = os.getenv("FOOTBALL_PREDICTOR_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


@lru_cache
def get_settings() -> Settings:
    project_root = _resolve_project_root()
    data_dir = project_root / "data"
    data_templates_dir = data_dir / "templates"
    data_mock_dir = data_dir / "mock"
    data_external_dir = data_dir / "external"
    data_ingested_dir = data_dir / "ingested"
    data_mappings_dir = data_dir / "mappings"
    artifacts_dir = project_root / "artifacts"
    artifacts_models_dir = artifacts_dir / "models"
    artifacts_eval_dir = artifacts_dir / "eval"
    artifacts_agent_dir = artifacts_dir / "agent"
    artifacts_research_director_dir = artifacts_dir / "research_director"
    artifacts_research_dir = artifacts_dir / "research"
    artifacts_research_reports_dir = artifacts_research_dir / "reports"
    artifacts_research_registry_dir = artifacts_research_dir / "registry"
    artifacts_research_schedules_dir = artifacts_research_dir / "schedules"
    research_director_step_records_dir = artifacts_research_director_dir / "step_records"
    research_director_audit_dir = artifacts_research_director_dir / "audit"
    research_execution_history_path = artifacts_research_dir / "execution_history.jsonl"
    research_latest_execution_summary_path = artifacts_research_dir / "latest_execution_summary.json"
    research_daily_prediction_report_json_path = artifacts_research_reports_dir / "daily_prediction_report.json"
    research_daily_prediction_report_md_path = artifacts_research_reports_dir / "daily_prediction_report.md"
    research_post_match_report_json_path = artifacts_research_reports_dir / "post_match_report.json"
    research_post_match_report_md_path = artifacts_research_reports_dir / "post_match_report.md"
    research_model_registry_path = artifacts_research_dir / "model_registry.json"
    research_current_model_pointer_path = artifacts_research_registry_dir / "current_model.json"
    research_registry_events_path = artifacts_research_registry_dir / "registry_events.jsonl"
    research_scheduler_state_path = artifacts_research_schedules_dir / "scheduler_state.json"
    research_scheduler_history_path = artifacts_research_schedules_dir / "scheduler_history.jsonl"
    research_scheduler_config_path = artifacts_research_schedules_dir / "scheduler_config.json"

    return Settings(
        project_root=project_root,
        data_dir=data_dir,
        data_raw_dir=data_dir / "raw",
        data_interim_dir=data_dir / "interim",
        data_processed_dir=data_dir / "processed",
        data_templates_dir=data_templates_dir,
        data_mock_dir=data_mock_dir,
        data_external_dir=data_external_dir,
        data_ingested_dir=data_ingested_dir,
        data_mappings_dir=data_mappings_dir,
        artifacts_dir=artifacts_dir,
        artifacts_models_dir=artifacts_models_dir,
        artifacts_eval_dir=artifacts_eval_dir,
        artifacts_logs_dir=artifacts_dir / "logs",
        artifacts_agent_dir=artifacts_agent_dir,
        agent_state_db_path=artifacts_agent_dir / "state.sqlite",
        agent_runs_dir=artifacts_agent_dir / "runs",
        artifacts_research_director_dir=artifacts_research_director_dir,
        artifacts_research_dir=artifacts_research_dir,
        artifacts_research_reports_dir=artifacts_research_reports_dir,
        artifacts_research_registry_dir=artifacts_research_registry_dir,
        artifacts_research_schedules_dir=artifacts_research_schedules_dir,
        research_director_state_db_path=artifacts_research_director_dir / "state.sqlite",
        research_director_runs_dir=artifacts_research_director_dir / "runs",
        research_director_step_records_dir=research_director_step_records_dir,
        research_director_audit_dir=research_director_audit_dir,
        research_execution_history_path=research_execution_history_path,
        research_latest_execution_summary_path=research_latest_execution_summary_path,
        research_daily_prediction_report_json_path=research_daily_prediction_report_json_path,
        research_daily_prediction_report_md_path=research_daily_prediction_report_md_path,
        research_post_match_report_json_path=research_post_match_report_json_path,
        research_post_match_report_md_path=research_post_match_report_md_path,
        research_model_registry_path=research_model_registry_path,
        research_current_model_pointer_path=research_current_model_pointer_path,
        research_registry_events_path=research_registry_events_path,
        research_scheduler_state_path=research_scheduler_state_path,
        research_scheduler_history_path=research_scheduler_history_path,
        research_scheduler_config_path=research_scheduler_config_path,
        logit_model_path=artifacts_models_dir / "logit_baseline.pkl",
        logit_model_manifest_path=artifacts_models_dir / "logit_baseline.manifest.json",
        lightgbm_model_path=artifacts_models_dir / "lightgbm_baseline.pkl",
        lightgbm_model_manifest_path=artifacts_models_dir / "lightgbm_baseline.manifest.json",
        baseline_model_path=artifacts_models_dir / "logit_baseline.pkl",
        lgbm_model_path=artifacts_models_dir / "lightgbm_baseline.pkl",
        stacking_logit_model_path=artifacts_models_dir / "stacking_logit_base.pkl",
        stacking_lightgbm_model_path=artifacts_models_dir / "stacking_lightgbm_base.pkl",
        stacking_meta_model_path=artifacts_models_dir / "stacking_meta.pkl",
        stacking_meta_model_manifest_path=artifacts_models_dir / "stacking_meta.manifest.json",
        stacking_oof_logit_model_path=artifacts_models_dir / "stacking_oof_logit_base.pkl",
        stacking_oof_lightgbm_model_path=artifacts_models_dir / "stacking_oof_lightgbm_base.pkl",
        stacking_oof_meta_model_path=artifacts_models_dir / "stacking_oof_meta.pkl",
        stacking_oof_meta_model_manifest_path=artifacts_models_dir / "stacking_oof_meta.manifest.json",
        eval_results_path=artifacts_eval_dir / "results.csv",
        eval_metrics_path=artifacts_eval_dir / "metrics.json",
        eval_run_summary_path=artifacts_eval_dir / "run_summary.csv",
        eval_feature_compare_path=artifacts_eval_dir / "feature_compare.csv",
        eval_phase3_time_split_path=artifacts_eval_dir / "phase3_time_split.json",
        eval_phase3_cv_folds_path=artifacts_eval_dir / "phase3_cv_folds.csv",
        eval_phase3_cv_summary_path=artifacts_eval_dir / "phase3_cv_summary.json",
        eval_phase3_reliability_path=artifacts_eval_dir / "phase3_reliability.csv",
        eval_cv_results_path=artifacts_eval_dir / "cv_results.csv",
        eval_cv_league_metrics_path=artifacts_eval_dir / "cv_league_summary.csv",
        eval_calibration_compare_path=artifacts_eval_dir / "calibration_compare.csv",
        eval_reliability_table_path=artifacts_eval_dir / "reliability_table.csv",
        eval_model_compare_path=artifacts_eval_dir / "model_compare.csv",
        eval_lightgbm_feature_importance_path=artifacts_eval_dir / "lightgbm_feature_importance.csv",
        eval_league_metrics_path=artifacts_eval_dir / "league_metrics.csv",
        eval_lightgbm_shap_summary_path=artifacts_eval_dir / "lightgbm_shap_summary.csv",
        eval_verifier_report_path=artifacts_eval_dir / "verifier_report.json",
        eval_high_confidence_errors_path=artifacts_eval_dir / "high_confidence_errors.csv",
        eval_underestimated_draws_path=artifacts_eval_dir / "underestimated_draws.csv",
        eval_verifier_results_path=artifacts_eval_dir / "verifier_results.csv",
        eval_error_analysis_with_risk_path=artifacts_eval_dir / "error_analysis_with_risk.csv",
        data_matches_template_path=data_templates_dir / "matches_template.csv",
        data_mock_matches_path=data_mock_dir / "mock_matches.csv",
        eval_data_quality_report_path=artifacts_eval_dir / "data_quality_report.json",
        eval_data_missing_report_path=artifacts_eval_dir / "data_missing_report.csv",
        eval_dataset_validation_path=artifacts_eval_dir / "dataset_validation.json",
        eval_dataset_missing_report_path=artifacts_eval_dir / "dataset_missing_report.csv",
        data_ingest_input_default_path=data_external_dir / "incoming_matches.csv",
        data_ingest_output_path=data_ingested_dir / "matches_standardized.csv",
        eval_ingest_mapping_record_path=artifacts_eval_dir / "ingest_mapping_record.json",
        eval_ingest_validation_path=artifacts_eval_dir / "ingest_validation.json",
        eval_ingest_missing_report_path=artifacts_eval_dir / "ingest_missing_report.csv",
        eval_import_summary_path=artifacts_eval_dir / "import_summary.json",
        eval_field_mapping_report_path=artifacts_eval_dir / "field_mapping_report.csv",
    )


def ensure_project_dirs() -> None:
    s = get_settings()
    for p in (
        s.data_raw_dir,
        s.data_interim_dir,
        s.data_processed_dir,
        s.data_templates_dir,
        s.data_mock_dir,
        s.data_external_dir,
        s.data_ingested_dir,
        s.data_mappings_dir,
        s.artifacts_models_dir,
        s.artifacts_eval_dir,
        s.artifacts_logs_dir,
        s.artifacts_agent_dir,
        s.agent_runs_dir,
        s.artifacts_research_director_dir,
        s.research_director_runs_dir,
        s.research_director_step_records_dir,
        s.research_director_audit_dir,
        s.artifacts_research_dir,
        s.artifacts_research_reports_dir,
        s.artifacts_research_registry_dir,
        s.artifacts_research_schedules_dir,
    ):
        p.mkdir(parents=True, exist_ok=True)
