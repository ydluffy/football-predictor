from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class WorkflowKind(str, Enum):
    daily_prediction = "daily_prediction"
    post_match_learning = "post_match_learning"
    candidate_model_upgrade = "candidate_model_upgrade"


class AgentName(str, Enum):
    research_director = "research_director"
    data_scout = "data_scout"
    feature_lab = "feature_lab"
    model_trainer = "model_trainer"
    evaluator = "evaluator"
    predictor = "predictor"
    verifier = "verifier"
    optimizer = "optimizer"


class TaskKind(str, Enum):
    validate_dataset = "validate_dataset"
    import_real_csv = "import_real_csv"
    generate_mock_data = "generate_mock_data"
    train_model = "train_model"
    evaluate_model = "evaluate_model"
    predict = "predict"
    verify = "verify"
    optimize = "optimize"


class ActionType(str, Enum):
    read_file = "read_file"
    write_file = "write_file"
    run_command = "run_command"
    modify_code = "modify_code"
    delete_file = "delete_file"


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class TaskStatus(str, Enum):
    planned = "planned"
    running = "running"
    blocked = "blocked"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class ProposedAction(BaseModel):
    action_type: ActionType
    risk_level: RiskLevel
    description: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ArtifactRef(BaseModel):
    name: str
    path: str
    artifact_type: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sha256: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskSpec(BaseModel):
    task_id: str
    kind: TaskKind
    agent: AgentName
    risk_level: RiskLevel = RiskLevel.low
    params: dict[str, Any] = Field(default_factory=dict)


class TaskOutcome(BaseModel):
    task_id: str
    status: TaskStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    actions: list[ProposedAction] = Field(default_factory=list)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    summary: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)


class WorkflowRun(BaseModel):
    run_id: str
    kind: WorkflowKind
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tasks: list[TaskSpec] = Field(default_factory=list)
    outcomes: list[TaskOutcome] = Field(default_factory=list)
    decision: dict[str, Any] = Field(default_factory=dict)
