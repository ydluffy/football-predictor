from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from agent.mock_verifier import MockVerifier
from agent.schemas import MatchContext
from config.settings import ensure_project_dirs, get_settings
from research_director.agents.agent_base import AgentBase, StepArtifact, StepResult


class VerifierAgent(AgentBase):
    name = "verifier"

    def plan(self, *, context: dict[str, Any]) -> dict[str, Any]:
        return {"action": "mock_verify"}

    def execute(self, *, context: dict[str, Any], gate: Any) -> StepResult:
        ensure_project_dirs()
        s = get_settings()
        started = self._now()

        run_dir = Path(str(context.get("run_dir") or (s.research_director_runs_dir / str(context["run_id"]))))
        run_dir.mkdir(parents=True, exist_ok=True)

        pred_path = Path(str(context.get("predictions_path") or (run_dir / "daily_predictions.csv")))
        if not pred_path.is_absolute():
            pred_path = (s.project_root / pred_path).resolve()
        preds = pd.read_csv(pred_path)

        inp = Path(str(context.get("today_matches_path") or (run_dir / "daily_matches.csv")))
        if not inp.is_absolute():
            inp = (s.project_root / inp).resolve()
        matches = pd.read_csv(inp)
        if "match_id" in matches.columns:
            matches["match_id"] = matches["match_id"].astype(str)
        preds["match_id"] = preds["match_id"].astype(str)
        df = preds.merge(matches, how="left", on="match_id")

        verifier = MockVerifier()
        rows: list[dict[str, object]] = []
        for _, r in df.iterrows():
            mc = MatchContext(
                match_id=str(r.get("match_id")),
                date=str(r.get("date")) if r.get("date") is not None else None,
                league=str(r.get("league")) if r.get("league") is not None else None,
                home_team=str(r.get("home_team")) if r.get("home_team") is not None else None,
                away_team=str(r.get("away_team")) if r.get("away_team") is not None else None,
                odds_home=float(r.get("odds_home")) if r.get("odds_home") is not None else None,
                odds_draw=float(r.get("odds_draw")) if r.get("odds_draw") is not None else None,
                odds_away=float(r.get("odds_away")) if r.get("odds_away") is not None else None,
                injury_flag=int(r.get("injury_flag")) if r.get("injury_flag") is not None else None,
                line_move=float(r.get("line_move")) if r.get("line_move") is not None else None,
            )
            bundle = verifier.collect_evidence(mc)
            local_result = verifier.verify_local(bundle)
            global_result = verifier.verify_global(bundle)
            vr = verifier.generate_result(bundle=bundle, local_result=local_result, global_result=global_result)
            rows.append(
                {
                    "match_id": vr.match_id,
                    "risk_flags": json.dumps(vr.risk_flags, ensure_ascii=False),
                    "manual_review_required": bool(vr.manual_review_required),
                    "source_confidence": float(vr.source_confidence),
                    "summary": str(vr.summary),
                }
            )

        out = pd.DataFrame(rows)
        out_path = run_dir / "daily_verifier_results.csv"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(out_path, index=False)

        s.eval_verifier_results_path.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(s.eval_verifier_results_path, index=False)

        merged = preds.merge(out, how="left", on="match_id")
        merged_path = run_dir / "daily_predictions_with_risk.csv"
        merged.to_csv(merged_path, index=False)

        finished = self._now()
        return StepResult(
            status="completed",
            summary="verified",
            started_at=started,
            finished_at=finished,
            artifacts=[
                StepArtifact(name="daily_verifier_results", path=str(out_path), artifact_type="csv", metadata={"rows": int(len(out))}),
                StepArtifact(name="verifier_results", path=str(s.eval_verifier_results_path), artifact_type="csv", metadata={"rows": int(len(out))}),
                StepArtifact(name="daily_predictions_with_risk", path=str(merged_path), artifact_type="csv", metadata={"rows": int(len(merged))}),
            ],
            metrics={"manual_review_required_count": int(out["manual_review_required"].fillna(False).astype(bool).sum()) if not out.empty else 0},
        )

    def summarize(self, result: StepResult) -> str:
        return result.summary
