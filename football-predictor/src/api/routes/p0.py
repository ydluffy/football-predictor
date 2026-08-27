from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from p0.db import connect as p0_db_connect
from p0.db import get_db_path as p0_get_db_path
from p0.db import get_fixture as p0_get_fixture
from p0.db import select_fixtures_by_date as p0_select_fixtures_by_date
from p0.db import select_recent_finished_matches as p0_select_recent_finished_matches
from p0.db import upsert_fixtures as p0_upsert_fixtures
from p0.football_data_org import fetch_major_league_matches
from p0.poisson import compute_lambdas, compute_team_averages, confidence_from_probs, predict_1x2


class P0Fixture(BaseModel):
    fixture_id: int
    competition_code: str | None = None
    competition_name: str | None = None
    utc_date: str | None = None
    status: str | None = None
    home_team_id: int | None = None
    home_team_name: str | None = None
    away_team_id: int | None = None
    away_team_name: str | None = None
    home_score: int | None = None
    away_score: int | None = None


class P0FixturesResponse(BaseModel):
    date_from: str
    date_to: str
    count: int
    fixtures: list[P0Fixture]


class P0IngestResponse(BaseModel):
    date_from: str
    date_to: str
    inserted_or_updated: int
    db_path: str


class P0Prediction(BaseModel):
    fixture_id: int
    p_home: float
    p_draw: float
    p_away: float
    confidence: float
    lambda_home: float
    lambda_away: float
    factors: list[str]


class P0PredictionsRequest(BaseModel):
    fixture_ids: list[int] | None = None
    date: str | None = None


class P0PredictionsResponse(BaseModel):
    count: int
    predictions: list[P0Prediction]


router = APIRouter()


def _utc_date() -> str:
    return datetime.now(UTC).date().isoformat()


@router.post("/api/ingest/football-data", response_model=P0IngestResponse)
def p0_ingest_football_data(
    date_from: str | None = None,
    date_to: str | None = None,
) -> P0IngestResponse:
    d0 = date_from or _utc_date()
    d1 = date_to or d0
    try:
        rows = fetch_major_league_matches(d0, d1)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                f"ingest_failed: {exc}. Please set FOOTBALL_DATA_API_KEY "
                "in football-predictor/.env"
            ),
        ) from exc

    conn = p0_db_connect()
    try:
        count = p0_upsert_fixtures(conn, rows)
    finally:
        conn.close()
    return P0IngestResponse(
        date_from=d0,
        date_to=d1,
        inserted_or_updated=count,
        db_path=str(p0_get_db_path()),
    )


@router.get("/api/fixtures", response_model=P0FixturesResponse)
def p0_list_fixtures(
    date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> P0FixturesResponse:
    if date:
        d0 = date
        d1 = date
    else:
        d0 = date_from or _utc_date()
        d1 = date_to or d0

    conn = p0_db_connect()
    try:
        fixtures = p0_select_fixtures_by_date(conn, d0, d1)
    finally:
        conn.close()
    return P0FixturesResponse(
        date_from=d0,
        date_to=d1,
        count=len(fixtures),
        fixtures=[P0Fixture(**fixture) for fixture in fixtures],
    )


def _p0_predict_fixture(conn: Any, fixture_id: int) -> P0Prediction:
    fixture = p0_get_fixture(conn, fixture_id)
    if not fixture:
        raise HTTPException(status_code=404, detail=f"fixture not found: {fixture_id}")

    home_id = fixture.get("home_team_id")
    away_id = fixture.get("away_team_id")
    utc_date = fixture.get("utc_date")
    if not home_id or not away_id or not utc_date:
        raise HTTPException(
            status_code=400,
            detail=f"fixture missing fields: {fixture_id}",
        )

    home_matches = p0_select_recent_finished_matches(
        conn,
        int(home_id),
        str(utc_date),
        limit=12,
    )
    away_matches = p0_select_recent_finished_matches(
        conn,
        int(away_id),
        str(utc_date),
        limit=12,
    )
    home_avg = compute_team_averages(home_matches, int(home_id))
    away_avg = compute_team_averages(away_matches, int(away_id))
    lambda_home, lambda_away = compute_lambdas(home_avg, away_avg)
    p_home, p_draw, p_away = predict_1x2(lambda_home, lambda_away)
    confidence = confidence_from_probs(p_home, p_draw, p_away)

    factors = [
        (
            f"主队近{home_avg.matches or 0}场：场均进球{home_avg.goals_for:.2f}，"
            f"场均失球{home_avg.goals_against:.2f}"
        ),
        (
            f"客队近{away_avg.matches or 0}场：场均进球{away_avg.goals_for:.2f}，"
            f"场均失球{away_avg.goals_against:.2f}"
        ),
        f"泊松期望进球：主{lambda_home:.2f} vs 客{lambda_away:.2f}",
    ]
    return P0Prediction(
        fixture_id=fixture_id,
        p_home=float(p_home),
        p_draw=float(p_draw),
        p_away=float(p_away),
        confidence=float(confidence),
        lambda_home=float(lambda_home),
        lambda_away=float(lambda_away),
        factors=factors,
    )


@router.post("/api/predictions", response_model=P0PredictionsResponse)
def p0_predict(req: P0PredictionsRequest) -> P0PredictionsResponse:
    if req.fixture_ids:
        fixture_ids = [int(fixture_id) for fixture_id in req.fixture_ids]
    elif req.date:
        lookup_conn = p0_db_connect()
        try:
            fixtures = p0_select_fixtures_by_date(lookup_conn, req.date, req.date)
            fixture_ids = [int(fixture["fixture_id"]) for fixture in fixtures]
        finally:
            lookup_conn.close()
    else:
        raise HTTPException(status_code=400, detail="provide fixture_ids or date")

    conn = p0_db_connect()
    try:
        predictions = [
            _p0_predict_fixture(conn, fixture_id) for fixture_id in fixture_ids
        ]
    finally:
        conn.close()
    return P0PredictionsResponse(
        count=len(predictions),
        predictions=predictions,
    )
