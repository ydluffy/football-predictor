from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class ExecutionContext(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_name: str
    trigger_mode: str = "manual"
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    status: str = "running"
    model_type: str | None = None
    feature_version: str | None = None
    calibration_method: str | None = None
    use_verifier: bool = False
    input_paths: dict[str, str] = Field(default_factory=dict)
    output_paths: dict[str, str] = Field(default_factory=dict)
    notes: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None

    model_config = {"extra": "ignore"}

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def to_json(self) -> str:
        return self.model_dump_json()

    def finish(self, *, status: str, error_message: str | None = None, finished_at: datetime | None = None) -> "ExecutionContext":
        self.status = str(status)
        self.error_message = error_message
        self.finished_at = finished_at or datetime.now(timezone.utc)
        return self

