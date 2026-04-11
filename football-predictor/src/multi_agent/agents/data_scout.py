from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from data.validate_dataset import validate_matches_dataset
from multi_agent.agents.base import AgentBase
from multi_agent.gate import RuleGate
from multi_agent.schemas import ActionType, ArtifactRef, ProposedAction, RiskLevel, TaskKind, TaskOutcome, TaskSpec, TaskStatus
from multi_agent.state_store import SQLiteStateStore


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class DataScoutAgent(AgentBase):
    def propose_actions(self, task: TaskSpec) -> list[ProposedAction]:
        if task.kind == TaskKind.validate_dataset:
            return [
                ProposedAction(
                    action_type=ActionType.write_file,
                    risk_level=RiskLevel.low,
                    description="validate_dataset_and_write_reports",
                )
            ]
        return [
            ProposedAction(
                action_type=ActionType.read_file,
                risk_level=RiskLevel.low,
                description="noop",
            )
        ]

    def execute(self, task: TaskSpec, *, gate: RuleGate, store: SQLiteStateStore) -> TaskOutcome:
        now = datetime.now(timezone.utc)
        actions = self.propose_actions(task)
        for a in actions:
            d = gate.evaluate(a)
            if not d.allowed:
                return self._blocked_outcome(task, reason=d.reason, actions=actions)

        if task.kind != TaskKind.validate_dataset:
            return self._skipped_outcome(task, reason="unsupported_task_kind", actions=actions)

        s = self._settings()
        run_id = str(task.params.get("run_id") or "run")
        run_dir = s.agent_runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        json_path = run_dir / "dataset_validation.json"
        csv_path = run_dir / "dataset_missing_report.csv"

        df: pd.DataFrame | None = task.params.get("df")  # type: ignore[assignment]
        if df is None:
            input_path = task.params.get("input_csv_path")
            if not input_path:
                return TaskOutcome(
                    task_id=task.task_id,
                    status=TaskStatus.failed,
                    started_at=now,
                    finished_at=now,
                    actions=actions,
                    summary="missing_df_or_input_csv_path",
                )
            df = pd.read_csv(str(input_path))

        fv = str(task.params.get("feature_version") or "v3")
        payload = validate_matches_dataset(df, fv, output_json_path=str(json_path), missing_report_csv_path=str(csv_path))

        artifacts = [
            ArtifactRef(name="dataset_validation", path=str(json_path), artifact_type="json", sha256=_sha256_file(json_path)),
            ArtifactRef(name="dataset_missing_report", path=str(csv_path), artifact_type="csv", sha256=_sha256_file(csv_path)),
        ]
        return TaskOutcome(
            task_id=task.task_id,
            status=TaskStatus.completed,
            started_at=now,
            finished_at=now,
            actions=actions,
            artifacts=artifacts,
            summary="validated",
            metrics={"row_count": payload.get("row_count"), "parseable_date_ratio": payload.get("parseable_date_ratio")},
        )
