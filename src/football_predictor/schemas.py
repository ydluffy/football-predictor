from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class MatchResult(str, Enum):
    home = "H"
    draw = "D"
    away = "A"


class MatchRecord(BaseModel):
    match_id: str
    date: date
    league: str
    home_team: str
    away_team: str
    odds_home: float
    odds_draw: float
    odds_away: float
    xg_home: float
    xg_away: float
    injury_flag: int = Field(ge=0, le=1)
    line_move: float
    actual_result: MatchResult | None = None


class RiskFlag(BaseModel):
    code: str
    detail: dict[str, Any] = Field(default_factory=dict)


class PredictionProba(BaseModel):
    p_home: float = Field(ge=0.0, le=1.0)
    p_draw: float = Field(ge=0.0, le=1.0)
    p_away: float = Field(ge=0.0, le=1.0)


class PredictionRecord(BaseModel):
    match_id: str
    date: date
    league: str
    home_team: str
    away_team: str
    proba: PredictionProba
    model_name: str
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    requires_review: bool = False
    calibration: Literal["none", "sigmoid", "isotonic"] = "sigmoid"


class EvaluationReport(BaseModel):
    model_name: str
    n_samples: int
    brier: float
    logloss: float
    label_order: list[MatchResult]
