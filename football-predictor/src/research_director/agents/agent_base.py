from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class StepArtifact:
    name: str
    path: str
    artifact_type: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class StepResult:
    status: str
    summary: str
    started_at: datetime
    finished_at: datetime
    artifacts: list[StepArtifact]
    metrics: dict[str, Any]


class AgentBase(ABC):
    name: str

    @abstractmethod
    def plan(self, *, context: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def execute(self, *, context: dict[str, Any], gate: Any) -> StepResult: ...

    @abstractmethod
    def summarize(self, result: StepResult) -> str: ...

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

