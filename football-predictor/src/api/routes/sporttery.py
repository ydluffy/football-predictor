from __future__ import annotations

from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from api.views import SPORTTTERY_EDITOR_HTML
from world_cup.sporttery_markets import (
    append_sporttery_market_history,
    build_sporttery_template_from_fixtures,
    load_sporttery_handicap_markets,
    parse_home_handicap,
    parse_sporttery_paste_text,
)


class SportteryMarketRow(BaseModel):
    date: str
    match_id: str
    match_number: str
    home_team: str
    away_team: str
    home_handicap_raw: str
    home_handicap: float | None
    is_filled: bool
    source: str
    updated_at: str
    notes: str


class SportteryMarketsResponse(BaseModel):
    date: str
    path: str
    exists: bool
    count: int
    filled_count: int
    rows: list[SportteryMarketRow]


class SportteryMarketSaveRow(BaseModel):
    date: str
    match_id: str = ""
    match_number: str = ""
    home_team: str
    away_team: str
    home_handicap: str = ""
    source: str = "sporttery_manual"
    updated_at: str = ""
    notes: str = ""


class SportteryMarketSaveRequest(BaseModel):
    date: str
    rows: list[SportteryMarketSaveRow]
    snapshot_type: str = "latest"
    captured_at: str = ""


class SportteryMarketSaveResponse(BaseModel):
    ok: bool
    date: str
    path: str
    history_path: str
    count: int
    filled_count: int
    history_count: int


class SportteryPasteParseRequest(BaseModel):
    text: str


class SportteryPasteParseResponse(BaseModel):
    count: int
    rows: list[dict[str, str]]


router = APIRouter(prefix="/world-cup/sporttery", tags=["sporttery"])


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _sporttery_market_path(run_date: str) -> Path:
    return _project_root() / "data" / "manual" / (
        f"sporttery_handicap_markets_{run_date}.csv"
    )


def _sporttery_market_history_path() -> Path:
    return _project_root() / "data" / "manual" / (
        "sporttery_handicap_market_history.csv"
    )


def _sporttery_template_rows(run_date: str) -> pd.DataFrame:
    fixtures_path = (
        _project_root()
        / "data"
        / "player_level"
        / "espn_world_cup_2026"
        / "fixtures.csv"
    )
    fixtures = pd.read_csv(fixtures_path)
    return build_sporttery_template_from_fixtures(fixtures, as_of_date=run_date)


def _raw_sporttery_file(path: Path, run_date: str) -> tuple[pd.DataFrame, bool]:
    if path.exists():
        return pd.read_csv(path).fillna(""), True
    return _sporttery_template_rows(run_date).fillna(""), False


def _sporttery_rows_to_frame(
    rows: list[SportteryMarketSaveRow],
    *,
    run_date: str,
) -> pd.DataFrame:
    records = []
    for row in rows:
        row_date = str(pd.Timestamp(row.date).date())
        if row_date != run_date:
            raise ValueError(
                f"row date {row_date} does not match request date {run_date}"
            )
        handicap = row.home_handicap.strip()
        if handicap:
            parse_home_handicap(handicap)
        records.append(
            {
                "date": row_date,
                "match_id": row.match_id.strip(),
                "match_number": row.match_number.strip(),
                "home_team": row.home_team.strip(),
                "away_team": row.away_team.strip(),
                "home_handicap": handicap,
                "source": row.source.strip() or "sporttery_manual",
                "updated_at": row.updated_at.strip(),
                "notes": row.notes.strip(),
            }
        )
    return pd.DataFrame(
        records,
        columns=[
            "date",
            "match_id",
            "match_number",
            "home_team",
            "away_team",
            "home_handicap",
            "source",
            "updated_at",
            "notes",
        ],
    )


@router.get("/handicap-markets", response_model=SportteryMarketsResponse)
def world_cup_sporttery_handicap_markets(date: str) -> SportteryMarketsResponse:
    run_date = str(pd.Timestamp(date).date())
    path = _sporttery_market_path(run_date)
    raw, exists = _raw_sporttery_file(path, run_date)
    parsed_by_key: dict[tuple[str, str, str], dict[str, object]] = {}
    if exists:
        try:
            parsed = load_sporttery_handicap_markets(path)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        parsed_by_key = {
            (
                str(row["date"]),
                str(row["home_team"]),
                str(row["away_team"]),
            ): row.to_dict()
            for _, row in parsed.iterrows()
        }

    rows: list[SportteryMarketRow] = []
    for _, row in raw.iterrows():
        raw_handicap = str(row.get("home_handicap", "") or "").strip()
        key = (
            str(pd.Timestamp(row["date"]).date()),
            str(row.get("home_team", "")),
            str(row.get("away_team", "")),
        )
        parsed_row = parsed_by_key.get(key, {})
        rows.append(
            SportteryMarketRow(
                date=key[0],
                match_id=str(row.get("match_id", "") or ""),
                match_number=str(row.get("match_number", "") or ""),
                home_team=key[1],
                away_team=key[2],
                home_handicap_raw=raw_handicap,
                home_handicap=(
                    float(parsed_row["home_handicap"])
                    if "home_handicap" in parsed_row and raw_handicap
                    else None
                ),
                is_filled=bool(raw_handicap),
                source=str(row.get("source", "") or ""),
                updated_at=str(row.get("updated_at", "") or ""),
                notes=str(row.get("notes", "") or ""),
            )
        )
    return SportteryMarketsResponse(
        date=run_date,
        path=str(path),
        exists=exists,
        count=len(rows),
        filled_count=sum(1 for row in rows if row.is_filled),
        rows=rows,
    )


@router.post("/handicap-markets", response_model=SportteryMarketSaveResponse)
def save_world_cup_sporttery_handicap_markets(
    request: SportteryMarketSaveRequest,
) -> SportteryMarketSaveResponse:
    run_date = str(pd.Timestamp(request.date).date())
    try:
        frame = _sporttery_rows_to_frame(request.rows, run_date=run_date)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    path = _sporttery_market_path(run_date)
    history_path = _sporttery_market_history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    history = append_sporttery_market_history(
        history_path,
        frame,
        snapshot_type=request.snapshot_type.strip() or "latest",
        captured_at=request.captured_at.strip(),
    )
    return SportteryMarketSaveResponse(
        ok=True,
        date=run_date,
        path=str(path),
        history_path=str(history_path),
        count=int(len(frame)),
        filled_count=int(frame["home_handicap"].astype(str).str.strip().ne("").sum()),
        history_count=int(len(history)),
    )


@router.post("/parse-paste", response_model=SportteryPasteParseResponse)
def parse_world_cup_sporttery_paste(
    request: SportteryPasteParseRequest,
) -> SportteryPasteParseResponse:
    rows = parse_sporttery_paste_text(request.text)
    return SportteryPasteParseResponse(count=len(rows), rows=rows)


@router.get("/editor", response_class=HTMLResponse)
def world_cup_sporttery_editor() -> HTMLResponse:
    return HTMLResponse(content=SPORTTTERY_EDITOR_HTML)
