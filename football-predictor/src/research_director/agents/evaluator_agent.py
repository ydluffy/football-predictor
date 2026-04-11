from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from config.settings import ensure_project_dirs, get_settings
from evaluate.error_analysis import export_error_analysis_with_risk
from evaluate.league_eval import evaluate_by_league
from evaluate.metrics import compute_metrics, reliability_table
from research_director.agents.agent_base import AgentBase, StepArtifact, StepResult


class EvaluatorAgent(AgentBase):
    name = "evaluator"

    def plan(self, *, context: dict[str, Any]) -> dict[str, Any]:
        return {"action": "evaluate"}

    def execute(self, *, context: dict[str, Any], gate: Any) -> StepResult:
        ensure_project_dirs()
        s = get_settings()
        started = self._now()

        run_dir = Path(str(context.get("run_dir") or (s.research_director_runs_dir / str(context["run_id"]))))
        run_dir.mkdir(parents=True, exist_ok=True)

        inp = Path(str(context.get("matches_path") or (s.data_processed_dir / "real_matches_standardized.csv")))
        if not inp.is_absolute():
            inp = (s.project_root / inp).resolve()
        df = pd.read_csv(inp)

        pred_path = context.get("predictions_path")
        if pred_path:
            pp = Path(str(pred_path))
            if not pp.is_absolute():
                pp = (s.project_root / pp).resolve()
            preds = pd.read_csv(pp)
            preds["match_id"] = preds["match_id"].astype(str)
            df2 = df.copy()
            if "match_id" in df2.columns:
                df2["match_id"] = df2["match_id"].astype(str)
            merged = preds.merge(df2, how="left", on="match_id")
            p_home = pd.to_numeric(merged.get("p_home"), errors="coerce").astype(float)
            p_draw = pd.to_numeric(merged.get("p_draw"), errors="coerce").astype(float)
            p_away = pd.to_numeric(merged.get("p_away"), errors="coerce").astype(float)
            actual = merged.get("actual_result") if "actual_result" in merged.columns else merged.get("actual")
            actual = actual.astype(str).str.upper() if actual is not None else pd.Series([], dtype=str)
            results = pd.DataFrame(
                {
                    "match_id": merged.get("match_id").astype(str),
                    "league": merged.get("league") if "league" in merged.columns else None,
                    "p_home": p_home,
                    "p_draw": p_draw,
                    "p_away": p_away,
                    "actual": actual,
                }
            )
        else:
            eps = 1e-12
            oh = pd.to_numeric(df.get("odds_home"), errors="coerce").astype(float).clip(lower=eps)
            od = pd.to_numeric(df.get("odds_draw"), errors="coerce").astype(float).clip(lower=eps)
            oa = pd.to_numeric(df.get("odds_away"), errors="coerce").astype(float).clip(lower=eps)
            imp_h = 1.0 / oh
            imp_d = 1.0 / od
            imp_a = 1.0 / oa
            s_imp = (imp_h + imp_d + imp_a).clip(lower=eps)
            p_home = (imp_h / s_imp).astype(float)
            p_draw = (imp_d / s_imp).astype(float)
            p_away = (imp_a / s_imp).astype(float)

            results = pd.DataFrame(
                {
                    "match_id": df.get("match_id").astype(str),
                    "league": df.get("league") if "league" in df.columns else None,
                    "p_home": p_home,
                    "p_draw": p_draw,
                    "p_away": p_away,
                    "actual": df.get("actual_result").astype(str).str.upper(),
                }
            )

        metrics = compute_metrics(results["actual"], results[["p_home", "p_draw", "p_away"]])

        results_path = run_dir / "post_match_results_proxy.csv"
        results.to_csv(results_path, index=False)

        metrics_path = run_dir / "post_match_metrics.json"
        metrics_path.write_text(
            json.dumps({"brier": float(metrics["brier"]), "logloss": float(metrics["logloss"])}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        rel_rows = reliability_table(results["actual"], results[["p_home", "p_draw", "p_away"]], n_bins=10)
        rel_path = run_dir / "reliability_table.csv"
        pd.DataFrame(rel_rows).to_csv(rel_path, index=False)

        league_path = None
        if "league" in results.columns and results["league"].notna().any():
            league_df = evaluate_by_league(results.fillna({"league": ""}))
            league_path = run_dir / "league_metrics.csv"
            league_df.to_csv(league_path, index=False)

        error_path = run_dir / "error_analysis_with_risk.csv"
        export_error_analysis_with_risk(results, output_csv_path=str(error_path))

        finished = self._now()
        artifacts = [
            StepArtifact(name="post_match_results_proxy", path=str(results_path), artifact_type="csv", metadata={"rows": int(len(results))}),
            StepArtifact(name="post_match_metrics", path=str(metrics_path), artifact_type="json", metadata={}),
            StepArtifact(name="reliability_table", path=str(rel_path), artifact_type="csv", metadata={}),
            StepArtifact(name="error_analysis_with_risk", path=str(error_path), artifact_type="csv", metadata={}),
        ]
        if league_path is not None and league_path.exists():
            artifacts.append(StepArtifact(name="league_metrics", path=str(league_path), artifact_type="csv", metadata={}))

        return StepResult(
            status="completed",
            summary="evaluated",
            started_at=started,
            finished_at=finished,
            artifacts=artifacts,
            metrics={"brier": float(metrics["brier"]), "logloss": float(metrics["logloss"])},
        )

    def summarize(self, result: StepResult) -> str:
        return result.summary
