from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from multi_agent.agents.data_scout import DataScoutAgent
from multi_agent.gate import RuleGate
from multi_agent.schemas import AgentName, RiskLevel, TaskKind, TaskOutcome, TaskSpec, TaskStatus, WorkflowKind, WorkflowRun
from multi_agent.state_store import SQLiteStateStore


class ResearchDirectorAgent:
    def __init__(self, *, store: SQLiteStateStore | None = None, gate: RuleGate | None = None) -> None:
        self._store = store or SQLiteStateStore()
        self._gate = gate or RuleGate(allow_high_risk=False)
        self._agents = {
            AgentName.data_scout: DataScoutAgent(),
        }

    @property
    def store(self) -> SQLiteStateStore:
        return self._store

    def plan_workflow(self, kind: WorkflowKind, *, params: dict[str, Any] | None = None) -> WorkflowRun:
        run_id = str(uuid.uuid4())
        p = params or {}

        tasks: list[TaskSpec] = []
        if kind == WorkflowKind.daily_prediction:
            tasks.append(
                TaskSpec(
                    task_id=f"{run_id}:validate_dataset",
                    kind=TaskKind.validate_dataset,
                    agent=AgentName.data_scout,
                    risk_level=RiskLevel.low,
                    params={"run_id": run_id, "feature_version": p.get("feature_version", "v3"), **p},
                )
            )
            tasks.append(
                TaskSpec(
                    task_id=f"{run_id}:predict",
                    kind=TaskKind.predict,
                    agent=AgentName.predictor,
                    risk_level=RiskLevel.medium,
                    params={"run_id": run_id, **p},
                )
            )
        elif kind == WorkflowKind.post_match_learning:
            tasks.append(
                TaskSpec(
                    task_id=f"{run_id}:validate_dataset",
                    kind=TaskKind.validate_dataset,
                    agent=AgentName.data_scout,
                    risk_level=RiskLevel.low,
                    params={"run_id": run_id, "feature_version": p.get("feature_version", "v3"), **p},
                )
            )
            tasks.append(
                TaskSpec(
                    task_id=f"{run_id}:evaluate",
                    kind=TaskKind.evaluate_model,
                    agent=AgentName.evaluator,
                    risk_level=RiskLevel.medium,
                    params={"run_id": run_id, **p},
                )
            )
        else:
            tasks.append(
                TaskSpec(
                    task_id=f"{run_id}:train_candidate",
                    kind=TaskKind.train_model,
                    agent=AgentName.model_trainer,
                    risk_level=RiskLevel.high,
                    params={"run_id": run_id, **p},
                )
            )
            tasks.append(
                TaskSpec(
                    task_id=f"{run_id}:evaluate",
                    kind=TaskKind.evaluate_model,
                    agent=AgentName.evaluator,
                    risk_level=RiskLevel.medium,
                    params={"run_id": run_id, **p},
                )
            )
            tasks.append(
                TaskSpec(
                    task_id=f"{run_id}:optimize",
                    kind=TaskKind.optimize,
                    agent=AgentName.optimizer,
                    risk_level=RiskLevel.medium,
                    params={"run_id": run_id, **p},
                )
            )

        return WorkflowRun(run_id=run_id, kind=kind, tasks=tasks)

    def run_workflow(self, kind: WorkflowKind, *, params: dict[str, Any] | None = None, execute_low_risk: bool = True) -> WorkflowRun:
        run = self.plan_workflow(kind, params=params)
        now = datetime.now(timezone.utc)
        self._store.create_run(run_id=run.run_id, kind=kind)
        for t in run.tasks:
            self._store.add_task(run_id=run.run_id, task=t)

        outcomes: list[TaskOutcome] = []
        for task in run.tasks:
            if not execute_low_risk or task.risk_level != RiskLevel.low:
                outcome = TaskOutcome(
                    task_id=task.task_id,
                    status=TaskStatus.planned,
                    started_at=now,
                    finished_at=now,
                    summary="planned_only",
                )
                outcomes.append(outcome)
                continue

            agent = self._agents.get(task.agent)
            if agent is None:
                outcome = TaskOutcome(
                    task_id=task.task_id,
                    status=TaskStatus.skipped,
                    started_at=now,
                    finished_at=now,
                    summary="agent_not_registered",
                )
                outcomes.append(outcome)
                continue

            self._store.set_task_status(task_id=task.task_id, status=TaskStatus.running)
            outcome = agent.execute(task, gate=self._gate, store=self._store)
            self._store.record_outcome(outcome)
            outcomes.append(outcome)

        run.outcomes = outcomes
        run.decision = {"status": "no_upgrade", "reason": "skeleton_no_automatic_model_replacement"}
        return run
