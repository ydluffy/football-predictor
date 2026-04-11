from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MatchContext(BaseModel):
    match_id: str
    date: str | None = None
    league: str | None = None
    home_team: str | None = None
    away_team: str | None = None
    odds_home: float | None = None
    odds_draw: float | None = None
    odds_away: float | None = None
    odds_home_open: float | None = None
    odds_draw_open: float | None = None
    odds_away_open: float | None = None
    odds_home_last: float | None = None
    odds_draw_last: float | None = None
    odds_away_last: float | None = None
    xg_home: float | None = None
    xg_away: float | None = None
    injury_flag: int | None = None
    line_move: float | None = None

    model_config = {"extra": "allow"}


class EvidenceItem(BaseModel):
    source_type: str
    content: str
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: datetime | None = None


class EvidenceBundle(BaseModel):
    match: MatchContext
    items: list[EvidenceItem] = Field(default_factory=list)


class VerificationResult(BaseModel):
    match_id: str
    risk_flags: list[str] = Field(default_factory=list)
    source_confidence: float = Field(ge=0.0, le=1.0)
    conflict_notes: list[str] = Field(default_factory=list)
    manual_review_required: bool
    summary: str

