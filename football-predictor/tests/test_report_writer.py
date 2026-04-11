from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from config.settings import get_settings
from research_director.report_writer import write_daily_report, write_post_match_report


def test_write_daily_report_writes_research_reports(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    s = get_settings()

    run_dir = s.research_director_runs_dir / "run1"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_manifest.json").write_text(
        json.dumps(
            {
                "execution_context": {"model_type": "logit", "feature_version": "v3", "use_verifier": True},
                "context": {"data_mode": "real"},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    preds = run_dir / "daily_predictions.csv"
    pd.DataFrame({"match_id": ["m1", "m2"], "p_home": [0.4, 0.3], "p_draw": [0.3, 0.4], "p_away": [0.3, 0.3], "predicted_label": ["H", "D"]}).to_csv(
        preds, index=False
    )

    verifier = run_dir / "daily_verifier_results.csv"
    pd.DataFrame(
        {
            "match_id": ["m1", "m2"],
            "risk_flags": ['["line_move_risk"]', "[]"],
            "manual_review_required": [True, False],
            "source_confidence": [0.9, 0.9],
            "summary": ["x", "y"],
        }
    ).to_csv(verifier, index=False)

    (run_dir / "steps" / "predict").mkdir(parents=True, exist_ok=True)
    (run_dir / "steps" / "predict" / "step_result.json").write_text(
        json.dumps({"metrics": {"model_artifact_status": "warning", "model_load_error": "x", "fallback_used": True, "fallback_policy": "graceful"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (run_dir / "steps" / "data").mkdir(parents=True, exist_ok=True)
    (run_dir / "steps" / "data" / "step_result.json").write_text(
        json.dumps({"metrics": {"standardized_data_path": str(run_dir / "daily_matches.csv"), "required_fields_missing": []}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (run_dir / "import_validation.json").write_text(json.dumps({"required_fields_missing": []}, ensure_ascii=False), encoding="utf-8")

    out_path = write_daily_report(run_dir, predictions_path=preds, verifier_path=verifier)
    assert out_path.exists()
    assert s.research_daily_prediction_report_json_path.exists()
    assert s.research_daily_prediction_report_md_path.exists()

    payload = json.loads(s.research_daily_prediction_report_json_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "run1"
    assert payload["match_count"] == 2
    assert payload["input_data_mode"] == "real"
    assert payload["standardized_data_path"]
    assert payload["validation_result"] is not None
    assert payload["model_type"] == "logit"
    assert payload["feature_version"] == "v3"
    assert bool(payload["use_verifier"]) is True
    assert payload["risk_summary"]["manual_review_required_count"] == 1
    assert payload["fallback_used"] is True
    assert payload["model_artifact_status"] == "warning"
    assert payload["fallback_policy"] == "graceful"

    md = s.research_daily_prediction_report_md_path.read_text(encoding="utf-8")
    assert "run_id" in md
    assert "今日比赛数量" in md
    assert "本次预测非正式模型推理结果" in md


def test_write_post_match_report_writes_research_reports(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    s = get_settings()

    run_dir = s.research_director_runs_dir / "run2"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_manifest.json").write_text(
        json.dumps(
            {
                "execution_context": {"model_type": "lightgbm", "feature_version": "v3"},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    (run_dir / "post_match_results_proxy.csv").write_text("match_id,p_home,p_draw,p_away,actual\nm1,0.3,0.3,0.4,H\n", encoding="utf-8")
    err_path = run_dir / "error_analysis_with_risk.csv"
    pd.DataFrame(
        [
            {
                "match_id": "m1",
                "league": "EPL",
                "error_type": "high_confidence_error",
                "predicted_label": "H",
                "actual": "A",
                "max_proba": 0.9,
                "p_home": 0.9,
                "p_draw": 0.05,
                "p_away": 0.05,
                "risk_flags": "[]",
                "manual_review_required": False,
            },
            {
                "match_id": "m2",
                "league": "EPL",
                "error_type": "underestimated_draw",
                "predicted_label": "A",
                "actual": "D",
                "max_proba": 0.7,
                "p_home": 0.2,
                "p_draw": 0.1,
                "p_away": 0.7,
                "risk_flags": "[]",
                "manual_review_required": False,
            },
        ]
    ).to_csv(err_path, index=False)

    (run_dir / "optimizer_suggestions.json").write_text(json.dumps({"suggestions": [{"type": "x"}, {"type": "y"}, {"type": "x"}]}, ensure_ascii=False), encoding="utf-8")

    out_path = write_post_match_report(run_dir, metrics={"brier": 0.2, "logloss": 1.0}, error_analysis_path=err_path)
    assert out_path.exists()
    assert s.research_post_match_report_json_path.exists()
    assert s.research_post_match_report_md_path.exists()

    payload = json.loads(s.research_post_match_report_json_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "run2"
    assert payload["sample_count"] == 1
    assert payload["high_confidence_error_count"] == 1
    assert payload["underestimated_draw_count"] == 1
    assert payload["optimizer_summary"]["suggestion_count"] == 3

    md = s.research_post_match_report_md_path.read_text(encoding="utf-8")
    assert "Post-Match" in md
    assert "高置信错判数" in md
