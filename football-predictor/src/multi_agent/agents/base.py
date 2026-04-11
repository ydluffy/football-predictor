from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from config.settings import get_settings
from multi_agent.gate import RuleGate
from multi_agent.schemas import ProposedAction, TaskOutcome, TaskSpec, TaskStatus
from multi_agent.state_store import SQLiteStateStore


class AgentBase(ABC):
    @abstractmethod
    def propose_actions(self, task: TaskSpec) -> list[ProposedAction]: ...

    @abstractmethod
    def execute(self, task: TaskSpec, *, gate: RuleGate, store: SQLiteStateStore) -> TaskOutcome: ...

    def _blocked_outcome(self, task: TaskSpec, *, reason: str, actions: list[ProposedAction]) -> TaskOutcome:
        now = datetime.now(timezone.utc)
        return TaskOutcome(
            task_id=task.task_id,
            status=TaskStatus.blocked,
            started_at=now,
            finished_at=now,
            actions=actions,
            summary=reason,
        )

    def _skipped_outcome(self, task: TaskSpec, *, reason: str, actions: list[ProposedAction]) -> TaskOutcome:
        now = datetime.now(timezone.utc)
        return TaskOutcome(
            task_id=task.task_id,
            status=TaskStatus.skipped,
            started_at=now,
            finished_at=now,
            actions=actions,
            summary=reason,
        )

    def _settings(self):
        return get_settings()
