from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from config.settings import ensure_project_dirs, get_settings
from features.basic_features import build_basic_features, build_inference_features
from data.validate_dataset import validate_matches_dataset
from research_director.agents.agent_base import AgentBase, StepArtifact, StepResult


class FeatureLabAgent(AgentBase):
    name = "feature_lab"

    def plan(self, *, context: dict[str, Any]) -> dict[str, Any]:
        return {"action": "build_features", "feature_version": str(context.get("feature_version") or "v3")}

    def execute(self, *, context: dict[str, Any], gate: Any) -> StepResult:
        ensure_project_dirs()
        s = get_settings()
        started = self._now()

        run_dir = Path(str(context.get("run_dir") or (s.research_director_runs_dir / str(context["run_id"]))))
        run_dir.mkdir(parents=True, exist_ok=True)

        inp = Path(str(context.get("today_matches_path") or (run_dir / "daily_matches.csv")))
        if not inp.is_absolute():
            inp = (s.project_root / inp).resolve()
        df = pd.read_csv(inp)

        feature_version = str(context.get("feature_version") or "v3")
        has_labels = False
        if "actual_result" in df.columns:
            vals = df["actual_result"].fillna("").astype(str).str.strip().str.upper()
            allowed = {"H", "D", "A"}
            has_labels = bool(vals.isin(list(allowed)).any())
            if has_labels:
                non_empty = vals[vals != ""]
                if not non_empty.isin(list(allowed)).all():
                    has_labels = False

        if has_labels:
            X, y, feature_names = build_basic_features(df, feature_version=feature_version)
            feats = X.copy()
            feats.insert(0, "actual_result", y.astype(str))
        else:
            X, feature_names = build_inference_features(df, feature_version=feature_version)
            feats = X.copy()

        match_id = df.get("match_id")
        if match_id is None:
            match_id = pd.Series(range(len(df)), index=df.index).astype(str)
        else:
            match_id = match_id.astype(str)
        feats.insert(0, "match_id", match_id)

        out_path = run_dir / "features.csv"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        feats.to_csv(out_path, index=False)

        input_validation_path = run_dir / "feature_input_validation.json"
        input_missing_path = run_dir / "feature_input_missing_report.csv"
        validate_matches_dataset(df, feature_version, output_json_path=str(input_validation_path), missing_report_csv_path=str(input_missing_path))

        snapshot_path = run_dir / "feature_snapshot.json"
        snapshot_path.write_text(
            json.dumps(
                {
                    "feature_version": feature_version,
                    "feature_count": int(len(feature_names)),
                    "features": [str(x) for x in feature_names],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        finished = self._now()
        return StepResult(
            status="completed",
            summary="features_built",
            started_at=started,
            finished_at=finished,
            artifacts=[
                StepArtifact(name="features", path=str(out_path), artifact_type="csv", metadata={"rows": int(len(feats))}),
                StepArtifact(name="feature_input_validation", path=str(input_validation_path), artifact_type="json", metadata={}),
                StepArtifact(name="feature_input_missing_report", path=str(input_missing_path), artifact_type="csv", metadata={}),
                StepArtifact(name="feature_snapshot", path=str(snapshot_path), artifact_type="json", metadata={}),
            ],
            metrics={"rows": int(len(feats)), "columns": int(feats.shape[1]), "feature_version": feature_version, "feature_count": int(len(feature_names))},
        )

    def summarize(self, result: StepResult) -> str:
        return result.summary
