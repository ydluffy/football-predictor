from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from config.settings import ensure_project_dirs, get_settings
from research_director.agents.agent_base import AgentBase, StepArtifact, StepResult


class OptimizerAgent(AgentBase):
    name = "optimizer"

    def plan(self, *, context: dict[str, Any]) -> dict[str, Any]:
        return {"action": "produce_improvement_suggestions"}

    def execute(self, *, context: dict[str, Any], gate: Any) -> StepResult:
        ensure_project_dirs()
        s = get_settings()
        started = self._now()

        run_dir = Path(str(context.get("run_dir") or (s.research_director_runs_dir / str(context["run_id"]))))
        run_dir.mkdir(parents=True, exist_ok=True)
        suggestions_path = run_dir / "optimizer_suggestions.json"

        suggestions: dict[str, Any] = {"suggestions": []}
        eval_dir = run_dir / "sandbox_project" / "artifacts" / "eval"
        if not eval_dir.exists():
            eval_dir = s.artifacts_eval_dir

        model_compare_path = eval_dir / "model_compare.csv"
        if model_compare_path.exists():
            mc = pd.read_csv(model_compare_path)
            if not mc.empty:
                last = mc.tail(1).iloc[0].to_dict()
                suggestions["suggestions"].append(
                    {
                        "type": "latest_model_compare",
                        "model_type": str(last.get("model_type")),
                        "feature_version": str(last.get("feature_version")),
                        "calibration_method": str(last.get("calibration_method")),
                        "brier": float(last.get("brier")) if last.get("brier") is not None else None,
                        "logloss": float(last.get("logloss")) if last.get("logloss") is not None else None,
                        "reliability_gap_mean": float(last.get("reliability_gap_mean")) if last.get("reliability_gap_mean") is not None else None,
                        "notes": str(last.get("notes") or ""),
                    }
                )
                try:
                    rg = float(last.get("reliability_gap_mean"))
                    if rg > 0.05:
                        suggestions["suggestions"].append({"type": "calibration_hint", "reason": "reliability_gap_high", "suggested_methods": ["sigmoid", "isotonic"]})
                except Exception:
                    pass

        feature_compare_path = eval_dir / "feature_compare.csv"
        if feature_compare_path.exists():
            fc = pd.read_csv(feature_compare_path)
            if not fc.empty:
                last = fc.tail(1).iloc[0].to_dict()
                suggestions["suggestions"].append(
                    {
                        "type": "latest_feature_compare",
                        "feature_version": str(last.get("feature_version")),
                        "n_features": int(last.get("n_features")) if last.get("n_features") is not None else None,
                        "n_samples": int(last.get("n_samples")) if last.get("n_samples") is not None else None,
                    }
                )

        error_path = run_dir / "error_analysis_with_risk.csv"
        if not error_path.exists():
            error_path = eval_dir / "error_analysis_with_risk.csv"
        if not error_path.exists():
            error_path = s.eval_error_analysis_with_risk_path
        if error_path.exists():
            df = pd.read_csv(error_path)
            if "error_type" in df.columns and not df.empty:
                vc = df["error_type"].astype(str).value_counts()
                for k, v in vc.items():
                    suggestions["suggestions"].append({"type": "error_type_count", "error_type": str(k), "count": int(v)})
            if "manual_review_required" in df.columns and not df.empty:
                cnt = int(df["manual_review_required"].fillna(False).astype(bool).sum())
                suggestions["suggestions"].append({"type": "manual_review_required_count", "count": cnt})
            if "risk_flags" in df.columns and not df.empty:
                top = df["risk_flags"].astype(str).value_counts().head(5)
                for k, v in top.items():
                    suggestions["suggestions"].append({"type": "risk_flags_top", "risk_flags": str(k), "count": int(v)})

        suggestions_path.write_text(json.dumps(suggestions, ensure_ascii=False, indent=2), encoding="utf-8")

        finished = self._now()
        return StepResult(
            status="completed",
            summary="suggested",
            started_at=started,
            finished_at=finished,
            artifacts=[StepArtifact(name="optimizer_suggestions", path=str(suggestions_path), artifact_type="json", metadata={})],
            metrics={"suggestion_count": int(len(suggestions["suggestions"]))},
        )

    def summarize(self, result: StepResult) -> str:
        return result.summary
