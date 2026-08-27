from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from config.settings import ensure_project_dirs, get_settings
from features.basic_features import build_basic_features
from ingest.load_data import load_matches
from models.baseline_logit import BaselineLogitModel, load_baseline_model
from utils.logger import configure_logger, get_logger
from research_director.director import ResearchDirector

from p0.db import connect as p0_db_connect
from p0.db import get_db_path as p0_get_db_path
from p0.db import get_fixture as p0_get_fixture
from p0.db import init_db as p0_init_db
from p0.db import select_fixtures_by_date as p0_select_fixtures_by_date
from p0.db import select_recent_finished_matches as p0_select_recent_finished_matches
from p0.db import upsert_fixtures as p0_upsert_fixtures
from p0.football_data_org import fetch_major_league_matches
from p0.poisson import TeamAverages
from p0.poisson import compute_lambdas
from p0.poisson import compute_team_averages
from p0.poisson import confidence_from_probs
from p0.poisson import predict_1x2
from world_cup.sporttery_markets import append_sporttery_market_history
from world_cup.sporttery_markets import build_sporttery_template_from_fixtures
from world_cup.sporttery_markets import load_sporttery_handicap_markets
from world_cup.sporttery_markets import parse_sporttery_paste_text
from world_cup.sporttery_markets import parse_home_handicap


def _load_dotenv_if_present(path: Path) -> None:
    if not path.exists():
        return
    try:
        txt = path.read_text(encoding="utf-8")
    except Exception:
        return
    for raw in txt.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        key = k.strip()
        val = v.strip().strip("'").strip('"')
        if not key:
            continue
        if key not in os.environ:
            os.environ[key] = val


_load_dotenv_if_present(Path(__file__).resolve().parents[2] / ".env")


class PredictResponse(BaseModel):
    p_home: float
    p_draw: float
    p_away: float


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: str | None = None


class ChatResponse(BaseModel):
    content: str


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


app = FastAPI(title="football-predictor", version="0.1.0")

_origins = os.getenv("CORS_ALLOW_ORIGINS") or "http://localhost:3000,http://127.0.0.1:3000"
allow_origins = [o.strip() for o in _origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"] ,
    allow_headers=["*"],
)

_MODEL: Any | None = None
_MODEL_PATH: Path | None = None


def _resolve_data_path(path: str, settings) -> str:
    try:
        load_matches(path)
        return path
    except FileNotFoundError:
        fallback = settings.project_root.parent / "data" / "sample_matches.csv"
        if fallback.exists():
            return str(fallback)
        raise


def _load_or_train_model() -> tuple[BaselineLogitModel, Path]:
    settings = get_settings()
    env_model = os.getenv("MODEL_PATH")
    model_path = Path(env_model).expanduser().resolve() if env_model else settings.baseline_model_path

    if model_path.exists():
        return load_baseline_model(model_path), model_path

    data_path = _resolve_data_path("data/raw/sample_matches.csv", settings)
    df = load_matches(data_path)
    X, y, _ = build_basic_features(df)
    model = BaselineLogitModel().train(X, y)
    saved = model.save(model_path)
    return model, saved


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _sporttery_market_path(run_date: str) -> Path:
    return _project_root() / "data" / "manual" / f"sporttery_handicap_markets_{run_date}.csv"


def _sporttery_market_history_path() -> Path:
    return _project_root() / "data" / "manual" / "sporttery_handicap_market_history.csv"


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
            raise ValueError(f"row date {row_date} does not match request date {run_date}")
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


@app.on_event("startup")
def _startup() -> None:
    global _MODEL, _MODEL_PATH
    ensure_project_dirs()
    configure_logger()
    log = get_logger()
    try:
        conn = p0_db_connect()
        p0_init_db(conn)
        conn.close()
        log.info("p0_db_ready={}", str(p0_get_db_path()))
    except Exception as e:
        log.warning("p0_db_init_failed={}", str(e))
    try:
        model, model_path = _load_or_train_model()
        _MODEL = model
        _MODEL_PATH = model_path
        log.info("loaded_model_path={}", str(model_path))
    except Exception as e:
        log.warning("model_load_failed={}", str(e))


@app.get("/health")
def health() -> dict[str, object]:
    return {"ok": True, "model_loaded": _MODEL is not None, "model_path": str(_MODEL_PATH) if _MODEL_PATH else None}


@app.get(
    "/world-cup/sporttery/handicap-markets",
    response_model=SportteryMarketsResponse,
)
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
            (str(row["date"]), str(row["home_team"]), str(row["away_team"])): row.to_dict()
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
    filled_count = sum(1 for row in rows if row.is_filled)
    return SportteryMarketsResponse(
        date=run_date,
        path=str(path),
        exists=exists,
        count=len(rows),
        filled_count=filled_count,
        rows=rows,
    )


@app.post(
    "/world-cup/sporttery/handicap-markets",
    response_model=SportteryMarketSaveResponse,
)
def save_world_cup_sporttery_handicap_markets(
    request: SportteryMarketSaveRequest,
) -> SportteryMarketSaveResponse:
    run_date = str(pd.Timestamp(request.date).date())
    try:
        frame = _sporttery_rows_to_frame(request.rows, run_date=run_date)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    path = _sporttery_market_path(run_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    history = append_sporttery_market_history(
        _sporttery_market_history_path(),
        frame,
        snapshot_type=request.snapshot_type.strip() or "latest",
        captured_at=request.captured_at.strip(),
    )
    filled_count = int(frame["home_handicap"].astype(str).str.strip().ne("").sum())
    return SportteryMarketSaveResponse(
        ok=True,
        date=run_date,
        path=str(path),
        history_path=str(_sporttery_market_history_path()),
        count=int(len(frame)),
        filled_count=filled_count,
        history_count=int(len(history)),
    )


@app.post(
    "/world-cup/sporttery/parse-paste",
    response_model=SportteryPasteParseResponse,
)
def parse_world_cup_sporttery_paste(
    request: SportteryPasteParseRequest,
) -> SportteryPasteParseResponse:
    rows = parse_sporttery_paste_text(request.text)
    return SportteryPasteParseResponse(count=len(rows), rows=rows)


@app.get("/world-cup/sporttery/editor", response_class=HTMLResponse)
def world_cup_sporttery_editor() -> HTMLResponse:
    html = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ä½“å½©è®©çƒç›˜ç¼–è¾‘å™¨</title>
  <style>
    body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f6f8fb; color: #1f2937; }
    header { padding: 18px 24px; background: #0f172a; color: #fff; }
    header h1 { margin: 0; font-size: 22px; }
    header p { margin: 6px 0 0; color: #cbd5e1; }
    main { max-width: 1180px; margin: 22px auto; padding: 0 18px 36px; }
    .toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 14px; }
    input, textarea { box-sizing: border-box; width: 100%; padding: 8px 10px; border: 1px solid #cbd5e1; border-radius: 8px; font: inherit; background: #fff; }
    input:focus, textarea:focus { outline: 2px solid #93c5fd; border-color: #2563eb; }
    input[type="date"] { width: 180px; }
    button { border: 0; border-radius: 8px; padding: 9px 14px; font-weight: 700; cursor: pointer; }
    .primary { background: #2563eb; color: #fff; }
    .secondary { background: #e2e8f0; color: #0f172a; }
    .danger { background: #fee2e2; color: #991b1b; }
    .card { background: #fff; border: 1px solid #e5e7eb; border-radius: 14px; box-shadow: 0 8px 20px rgba(15, 23, 42, 0.06); overflow: hidden; }
    .summary { padding: 14px 16px; border-bottom: 1px solid #e5e7eb; display: flex; gap: 16px; flex-wrap: wrap; color: #475569; }
    table { width: 100%; border-collapse: collapse; }
    th, td { border-bottom: 1px solid #e5e7eb; padding: 9px; vertical-align: top; }
    th { background: #f8fafc; text-align: left; font-size: 13px; color: #475569; }
    td { font-size: 14px; }
    .small { width: 105px; }
    .medium { width: 150px; }
    .handicap { width: 130px; }
    .notes { min-width: 180px; }
    .status { margin-top: 12px; padding: 10px 12px; border-radius: 10px; display: none; }
    .ok { display: block; background: #dcfce7; color: #166534; }
    .err { display: block; background: #fee2e2; color: #991b1b; }
    .hint { margin: 12px 0; color: #64748b; line-height: 1.6; }
    code { background: #eef2ff; color: #3730a3; padding: 2px 5px; border-radius: 5px; }
  </style>
</head>
<body>
  <header>
    <h1>ä½“å½©è®©çƒç›˜ç¼–è¾‘å™¨</h1>
    <p>å¡«å†™ä¸­å›½ä½“å½©ç«žå½©è¶³çƒè®©çƒèƒœå¹³è´Ÿç›˜å£ï¼Œä¿å­˜åŽæ—¥æŠ¥æµæ°´çº¿ä¼šä¼˜å…ˆä½¿ç”¨è¿™äº›çœŸå®žç›˜å£ã€‚</p>
  </header>
  <main>
    <div class="toolbar">
      <input id="date" type="date" />
      <input id="snapshotType" value="latest" placeholder="ç›˜å£é˜¶æ®µï¼šopening/live/closing" />
      <input id="capturedAt" placeholder="é‡‡é›†æ—¶é—´ï¼Œå¯ç•™ç©ºè‡ªåŠ¨ç”Ÿæˆ" />
      <button class="secondary" id="load">åŠ è½½å½“å¤©æ¯”èµ›</button>
      <button class="primary" id="save">ä¿å­˜ CSV</button>
      <button class="danger" id="clear">æ¸…ç©ºç›˜å£åˆ—</button>
    </div>
    <div class="hint">
      è®©çƒå†™æ³•æ”¯æŒï¼š<code>ä¸»é˜Ÿè®©1çƒ</code>ã€<code>ä¸»é˜Ÿå—è®©1çƒ</code>ã€<code>å¹³æ‰‹ç›˜</code>ã€<code>-1</code>ã€<code>+1</code>ã€<code>0</code>ã€‚
      è´Ÿæ•°ä»£è¡¨ä¸»é˜Ÿè®©çƒï¼Œæ­£æ•°ä»£è¡¨ä¸»é˜Ÿå—è®©ã€‚è¯·åªå¡«å·²æ ¸éªŒçš„å®˜æ–¹ä½“å½©ç›˜å£ã€‚
    </div>
    <div class="card" style="margin-bottom:14px; padding:14px 16px;">
      <strong>批量粘贴盘口</strong>
      <p class="hint">可从网页或 Excel 复制多行，例如：<code>周四001    Japan    Sweden    主队让1球</code>。解析后会按竞彩编号、match_id 或主客队填入下方表格。</p>
      <textarea id="pasteBox" rows="5" placeholder="周四001    Japan    Sweden    主队让1球&#10;周四002    Ecuador    Germany    平手盘"></textarea>
      <div class="toolbar" style="margin-top:10px; margin-bottom:0;">
        <button class="secondary" id="applyPaste">解析并填入</button>
        <button class="secondary" id="clearPaste">清空粘贴框</button>
      </div>
    </div>
    <div id="status" class="status"></div>
    <div class="card">
      <div class="summary" id="summary">å°šæœªåŠ è½½</div>
      <table>
        <thead>
          <tr>
            <th>æ—¥æœŸ</th>
            <th>match_id</th>
            <th>ç«žå½©ç¼–å·</th>
            <th>ä¸»é˜Ÿ</th>
            <th>å®¢é˜Ÿ</th>
            <th>è®©çƒç›˜</th>
            <th>æ¥æº</th>
            <th>æ›´æ–°æ—¶é—´</th>
            <th>å¤‡æ³¨</th>
          </tr>
        </thead>
        <tbody id="rows"></tbody>
      </table>
    </div>
  </main>
  <script>
    const dateInput = document.getElementById('date');
    const rowsEl = document.getElementById('rows');
    const summaryEl = document.getElementById('summary');
    const statusEl = document.getElementById('status');
    const today = new Date().toISOString().slice(0, 10);
    dateInput.value = today;

    function setStatus(text, ok = true) {
      statusEl.textContent = text;
      statusEl.className = 'status ' + (ok ? 'ok' : 'err');
    }

    function cellInput(value, cls, placeholder = '') {
      const escaped = String(value || '').replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;');
      return `<input class="${cls}" value="${escaped}" placeholder="${placeholder}" />`;
    }

    function render(data) {
      summaryEl.textContent = `æ—¥æœŸ ${data.date} | æ–‡ä»¶ ${data.exists ? 'å·²å­˜åœ¨' : 'æœªåˆ›å»º'} | å·²å¡« ${data.filled_count}/${data.count} | ${data.path}`;
      rowsEl.innerHTML = data.rows.map(row => `
        <tr>
          <td data-field="date">${row.date}</td>
          <td data-field="match_id">${row.match_id || ''}</td>
          <td>${cellInput(row.match_number, 'match_number small', 'å‘¨å››001')}</td>
          <td data-field="home_team">${row.home_team}</td>
          <td data-field="away_team">${row.away_team}</td>
          <td>${cellInput(row.home_handicap_raw, 'home_handicap handicap', 'ä¸»é˜Ÿè®©1çƒ')}</td>
          <td>${cellInput(row.source || 'sporttery_manual', 'source medium')}</td>
          <td>${cellInput(row.updated_at, 'updated_at medium', '2026-06-25 10:00')}</td>
          <td>${cellInput(row.notes, 'notes')}</td>
        </tr>
      `).join('');
    }

    async function loadRows() {
      statusEl.className = 'status';
      const date = dateInput.value;
      const res = await fetch(`/world-cup/sporttery/handicap-markets?date=${encodeURIComponent(date)}`);
      if (!res.ok) {
        setStatus(await res.text(), false);
        return;
      }
      render(await res.json());
    }

    function collectRows() {
      return [...rowsEl.querySelectorAll('tr')].map(tr => ({
        date: tr.querySelector('[data-field="date"]').textContent.trim(),
        match_id: tr.querySelector('[data-field="match_id"]').textContent.trim(),
        match_number: tr.querySelector('.match_number').value.trim(),
        home_team: tr.querySelector('[data-field="home_team"]').textContent.trim(),
        away_team: tr.querySelector('[data-field="away_team"]').textContent.trim(),
        home_handicap: tr.querySelector('.home_handicap').value.trim(),
        source: tr.querySelector('.source').value.trim() || 'sporttery_manual',
        updated_at: tr.querySelector('.updated_at').value.trim(),
        notes: tr.querySelector('.notes').value.trim(),
      }));
    }

    async function saveRows() {
      const payload = {
        date: dateInput.value,
        snapshot_type: document.getElementById('snapshotType').value.trim() || 'latest',
        captured_at: document.getElementById('capturedAt').value.trim(),
        rows: collectRows()
      };
      const res = await fetch('/world-cup/sporttery/handicap-markets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const text = await res.text();
      if (!res.ok) {
        setStatus(text, false);
        return;
      }
      const data = JSON.parse(text);
      setStatus(`å·²ä¿å­˜ï¼š${data.filled_count}/${data.count} æ¡ç›˜å£ï¼Œæœ€æ–°æ–‡ä»¶ ${data.path}ï¼ŒåŽ†å²ç´¯è®¡ ${data.history_count} æ¡`);
      await loadRows();
    }

    function normalizeText(value) {
      return String(value || "").trim().toLowerCase();
    }

    function applyParsedRows(parsedRows) {
      let applied = 0;
      const trs = [...rowsEl.querySelectorAll("tr")];
      for (const parsed of parsedRows) {
        const parsedMatchNumber = normalizeText(parsed.match_number);
        const parsedHome = normalizeText(parsed.home_team);
        const parsedAway = normalizeText(parsed.away_team);
        const target = trs.find(tr => {
          const matchNumber = normalizeText(tr.querySelector(".match_number").value);
          const matchId = normalizeText(tr.querySelector('[data-field="match_id"]').textContent);
          const home = normalizeText(tr.querySelector('[data-field="home_team"]').textContent);
          const away = normalizeText(tr.querySelector('[data-field="away_team"]').textContent);
          return (parsedMatchNumber && (parsedMatchNumber === matchNumber || parsedMatchNumber === matchId))
            || (parsedHome && parsedAway && home === parsedHome && away === parsedAway);
        });
        if (!target) continue;
        if (parsed.match_number) target.querySelector(".match_number").value = parsed.match_number;
        target.querySelector(".home_handicap").value = parsed.home_handicap || "";
        target.querySelector(".source").value = "sporttery_paste";
        applied += 1;
      }
      return applied;
    }

    async function parsePasteAndApply() {
      const text = document.getElementById("pasteBox").value;
      const res = await fetch("/world-cup/sporttery/parse-paste", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const body = await res.json();
      if (!res.ok) {
        setStatus(JSON.stringify(body), false);
        return;
      }
      const applied = applyParsedRows(body.rows || []);
      setStatus(`解析 ${body.count} 条，成功填入 ${applied} 条。请核对后保存。`, applied > 0);
    }

    document.getElementById('load').addEventListener('click', loadRows);
    document.getElementById('save').addEventListener('click', saveRows);
    document.getElementById('applyPaste').addEventListener('click', parsePasteAndApply);
    document.getElementById('clearPaste').addEventListener('click', () => {
      document.getElementById('pasteBox').value = '';
    });
    document.getElementById('clear').addEventListener('click', () => {
      rowsEl.querySelectorAll('.home_handicap').forEach(input => input.value = '');
    });
    loadRows();
  </script>
</body>
</html>
    """
    return HTMLResponse(html)


@app.get("/predict", response_model=PredictResponse)
def predict(match_id: str | None = None) -> PredictResponse:
    if _MODEL is None:
        raise HTTPException(status_code=503, detail="model not loaded")

    settings = get_settings()
    data_path = _resolve_data_path("data/raw/sample_matches.csv", settings)
    df = load_matches(data_path)
    X, _, _ = build_basic_features(df)

    if match_id is not None and "match_id" in df.columns:
        idxs = df.index[df["match_id"].astype(str) == str(match_id)].tolist()
        row_idx = idxs[0] if idxs else df.index[0]
    else:
        row_idx = df.index[0]

    x_row = X.loc[[row_idx]]
    proba = _MODEL.predict_proba(x_row).iloc[0]
    return PredictResponse(p_home=float(proba["p_home"]), p_draw=float(proba["p_draw"]), p_away=float(proba["p_away"]))


def _call_openai_chat(messages: list[dict[str, str]], model: str, tools: list[dict] = None) -> tuple[str, list[dict]]:
    import json
    import ssl
    from urllib import error, request

    def _chat_completions_url(base: str) -> str:
        b = str(base).rstrip("/")
        if b.endswith("/chat/completions"):
            return b
        if b.endswith("/v1"):
            return b + "/chat/completions"
        return b + "/v1/chat/completions"

    coding_key = os.getenv("CODING_PLAN_API_KEY")
    coding_base = os.getenv("CODING_PLAN_BASE_URL") or "https://coding.dashscope.aliyuncs.com/v1"
    bailian_key = os.getenv("BAILIAN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPEN_ROUTER_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    if coding_key:
        base_url = _chat_completions_url(coding_base)
        token = coding_key
    elif bailian_key:
        base_url = _chat_completions_url(os.getenv("BAILIAN_BASE_URL") or "https://dashscope.aliyuncs.com/compatible-mode/v1")
        token = bailian_key
    elif openrouter_key:
        base_url = _chat_completions_url(os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1")
        token = openrouter_key
    elif openai_key:
        base_url = _chat_completions_url(os.getenv("OPENAI_BASE_URL") or "https://api.openai.com")
        token = openai_key
    else:
        last = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last = m.get("content") or ""
                break
        return f"[mock] æˆ‘å·²æ”¶åˆ°ä½ çš„é—®é¢˜ï¼š{last[:120]} ...", []

    payload_dict = {"model": model, "messages": messages}
    if tools:
        payload_dict["tools"] = tools

    body = json.dumps(payload_dict).encode("utf-8")
    req = request.Request(str(base_url), data=body)
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {token}")
    ctx = ssl.create_default_context()
    try:
        with request.urlopen(req, context=ctx, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else str(e)
        return f"[error] llm_http_error status={getattr(e, 'code', None)} body={raw[:800]}", []
    except Exception as e:
        return f"[error] llm_request_failed {type(e).__name__}: {e}", []

    message = payload.get("choices", [{}])[0].get("message", {})
    content = message.get("content") or ""
    tool_calls = message.get("tool_calls", [])
    return str(content), tool_calls


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    sys_prompt = (
        "ä½ æ˜¯æœ¬ä»“åº“çš„è¶³çƒé¢„æµ‹ç ”ç©¶å‘˜ Copilotã€‚"
        "ä½ éœ€è¦å¸®åŠ©ç”¨æˆ·å®Œæˆï¼šèŽ·å–ä»Šæ—¥èµ›ç¨‹ã€è¿è¡Œé¢„æµ‹å’Œè®­ç»ƒå®žéªŒã€è®­ç»ƒè¯„ä¼°ã€æŒ‡æ ‡è§£è¯»ã€æ•°æ®æµå®¡è®¡ã€ä¸‹ä¸€æ­¥å®žéªŒå»ºè®®ã€‚"
        "å›žç­”è¦ç®€æ´ã€å¯æ‰§è¡Œï¼Œå¹¶å°½é‡å¼•ç”¨äº§ç‰©è·¯å¾„ä¸Žå…³é”®æ•°å­—ã€‚ä½ å¯ä»¥ä½¿ç”¨æä¾›çš„å·¥å…·ï¼ˆå‡½æ•°è°ƒç”¨ï¼‰æ¥æ‰§è¡Œå®žé™…æ“ä½œå¹¶èŽ·å–æ•°æ®ã€‚"
        "ä¸ºäº†æä¾›æ›´å¥½çš„ç”¨æˆ·ä½“éªŒï¼Œè¯·ä½ åœ¨å›žå¤ä¸­å¹¿æ³›ä½¿ç”¨ Markdown æ ¼å¼ï¼ŒåŒ…æ‹¬ï¼šè¡¨æ ¼ï¼ˆå¦‚å±•ç¤ºæ¯”èµ›åˆ—è¡¨å’ŒæŒ‡æ ‡ï¼‰ã€åŠ ç²—ã€åˆ—è¡¨ï¼Œå¹¶ä¸”åˆç†ä½¿ç”¨ç›¸å…³çš„ Emoji å›¾æ ‡ï¼ˆå¦‚ âš½, ðŸ“ˆ, ðŸ“‰, ðŸ’¡, âš ï¸ ç­‰ï¼‰æ¥ç‚¹ç¼€ä½ çš„å›žå¤ï¼Œä½¿å…¶ç¾Žè§‚æ˜“è¯»ã€‚"
    )
    msgs = [{"role": "system", "content": sys_prompt}] + [{"role": m.role, "content": m.content} for m in req.messages]
    model = (
        req.model
        or os.getenv("CODING_PLAN_MODEL")
        or os.getenv("BAILIAN_MODEL")
        or os.getenv("DASHSCOPE_MODEL")
        or os.getenv("OPENROUTER_MODEL")
        or os.getenv("OPENAI_MODEL")
        or "qwen-plus"
    )

    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_today_matches",
                "description": "èŽ·å–ä»Šå¤©æˆ–è¿‘æœŸçš„è¶³çƒæ¯”èµ›èµ›ç¨‹ï¼ŒåŒ…æ‹¬å¯¹é˜µåŒæ–¹ã€èµ”çŽ‡ã€é«˜çº§ç‰¹å¾ç­‰ã€‚",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "run_experiment",
                "description": "æ‰§è¡Œæ¨¡åž‹è®­ç»ƒæˆ–é¢„æµ‹å®žéªŒã€‚å½“ç”¨æˆ·è¦æ±‚'è·‘'ã€'é¢„æµ‹'ã€'è®­ç»ƒ'æˆ–'æŽ¨å•'æ—¶è°ƒç”¨ã€‚",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command_text": {
                            "type": "string",
                            "description": "ç”¨æˆ·åŽŸå§‹çš„è¯·æ±‚æ–‡æœ¬ï¼ŒåŒ…å«å¦‚ 'logit v1 real' æˆ– 'lightgbm v3' ç­‰æŒ‡ä»¤"
                        }
                    },
                    "required": ["command_text"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "analyze_latest_run",
                "description": "åˆ†æžæœ€è¿‘ä¸€æ¬¡å®žéªŒçš„ç»“æžœï¼ŒåŒ…æ‹¬ Brierã€Logloss å’Œæ¨¡åž‹å»ºè®®ã€‚",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "explain_high_brier",
                "description": "è§£é‡Šä¸ºä»€ä¹ˆæœ€è¿‘çš„å®žéªŒ Brier æˆ– Logloss åˆ†æ•°å¾ˆé«˜ï¼Œåˆ†æžæ¨¡åž‹çš„åå·®ã€‚",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "show_system_status",
                "description": "èŽ·å–å½“å‰ç³»ç»Ÿçš„æ¨¡åž‹æ³¨å†ŒçŠ¶æ€ã€ç”Ÿäº§æ¨¡åž‹ä¿¡æ¯ã€‚",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_backtest_status",
                "description": "èŽ·å–æœ€æ–°çš„å›žæµ‹ç»“æžœï¼ˆæ”¶ç›Šã€ROIã€å›žæ’¤ç­‰ï¼‰ã€‚",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }
    ]

    text, tool_calls = _call_openai_chat(msgs, model, tools)

    if tool_calls:
        # LLM decides to call a function
        tool_call = tool_calls[0]
        func_name = tool_call.get("function", {}).get("name")
        import json
        try:
            args = json.loads(tool_call.get("function", {}).get("arguments", "{}"))
        except:
            args = {}
            
        tool_result = ""
        if func_name == "get_today_matches":
            tool_result = _format_today_matches_message()
        elif func_name == "run_experiment":
            res = run_experiment(args.get("command_text", "logit v1 mock"))
            tool_result = json.dumps(res, ensure_ascii=False, indent=2)
        elif func_name == "analyze_latest_run":
            tool_result = _format_latest_analysis_message()
        elif func_name == "explain_high_brier":
            tool_result = _format_high_brier_message()
        elif func_name == "show_system_status":
            tool_result = _format_status_message()
        elif func_name == "get_backtest_status":
            tool_result = _format_backtest_message()
            
        if not tool_result:
            tool_result = "è°ƒç”¨æˆåŠŸï¼Œä½†æ²¡æœ‰è¿”å›žç»“æžœã€‚"

        # Append tool result and call LLM again to get final response
        msgs.append({
            "role": "assistant", 
            "content": text or "", 
            "tool_calls": tool_calls
        })
        msgs.append({
            "role": "tool",
            "tool_call_id": tool_call.get("id", ""),
            "name": func_name,
            "content": tool_result
        })
        
        final_text, _ = _call_openai_chat(msgs, model)
        return ChatResponse(content=final_text)

    # Return direct response
    return ChatResponse(content=text)


@app.get("/chat-ui", response_class=HTMLResponse)
def chat_ui() -> HTMLResponse:
    html = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>è¶³çƒé¢„æµ‹ç ”ç©¶å‘˜ Copilot</title>
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <style>
    body { font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin: 0; background-color: #f0f2f5; color: #333; }
    header { background: linear-gradient(135deg, #0b5fff, #0033a0); color: #fff; padding: 16px 20px; font-size: 1.2rem; font-weight: bold; box-shadow: 0 2px 4px rgba(0,0,0,0.1); display: flex; align-items: center; gap: 10px; }
    #chat-container { display: flex; flex-direction: column; height: calc(100vh - 60px); max-width: 900px; margin: 0 auto; background: #fff; box-shadow: 0 0 15px rgba(0,0,0,0.05); }
    #chat { flex: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 16px; scroll-behavior: smooth; }
    .msg { display: flex; width: 100%; }
    .msg.user { justify-content: flex-end; }
    .msg.assistant { justify-content: flex-start; }
    .bubble { max-width: 80%; padding: 12px 16px; border-radius: 12px; line-height: 1.5; font-size: 0.95rem; box-shadow: 0 1px 2px rgba(0,0,0,0.1); }
    .msg.user .bubble { background: #0b5fff; color: #fff; border-bottom-right-radius: 4px; }
    .msg.assistant .bubble { background: #f7f9fc; color: #333; border: 1px solid #e1e4e8; border-bottom-left-radius: 4px; }
    
    /* Markdown Styles */
    .bubble p { margin-top: 0; margin-bottom: 0.8em; }
    .bubble p:last-child { margin-bottom: 0; }
    .bubble a { color: #0b5fff; text-decoration: none; font-weight: 500; }
    .msg.user .bubble a { color: #eef3ff; text-decoration: underline; }
    .bubble code { background: rgba(0,0,0,0.06); padding: 2px 4px; border-radius: 4px; font-family: monospace; font-size: 0.9em; }
    .msg.user .bubble code { background: rgba(255,255,255,0.2); }
    .bubble pre { background: #2d3748; color: #f8f8f2; padding: 12px; border-radius: 8px; overflow-x: auto; margin: 10px 0; font-size: 0.9em; }
    .bubble pre code { background: transparent; color: inherit; padding: 0; }
    .bubble table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 0.9em; }
    .bubble th, .bubble td { border: 1px solid #e2e8f0; padding: 8px 12px; text-align: left; }
    .bubble th { background-color: #edf2f7; font-weight: 600; }
    .bubble ul, .bubble ol { margin-top: 0; margin-bottom: 0.8em; padding-left: 20px; }
    .bubble blockquote { border-left: 4px solid #cbd5e0; margin: 0; padding-left: 12px; color: #4a5568; }

    #box { display: flex; gap: 12px; padding: 16px; background: #fff; border-top: 1px solid #eaeaea; }
    textarea { flex: 1; padding: 12px; border-radius: 8px; border: 1px solid #d1d5db; resize: none; height: 48px; font-family: inherit; font-size: 0.95rem; outline: none; transition: border-color 0.2s; box-shadow: inset 0 1px 2px rgba(0,0,0,0.05); }
    textarea:focus { border-color: #0b5fff; }
    button { padding: 0 24px; border: 0; border-radius: 8px; background: #0b5fff; color: #fff; font-weight: 600; font-size: 0.95rem; cursor: pointer; transition: background-color 0.2s; display: flex; align-items: center; justify-content: center; }
    button:hover { background: #0046cc; }
    button[disabled] { opacity: 0.6; cursor: not-allowed; }
    
    /* Loading animation */
    .typing { display: flex; gap: 4px; padding: 4px 8px; }
    .typing .dot { width: 6px; height: 6px; background-color: #888; border-radius: 50%; animation: typing 1.4s infinite ease-in-out both; }
    .typing .dot:nth-child(1) { animation-delay: -0.32s; }
    .typing .dot:nth-child(2) { animation-delay: -0.16s; }
    @keyframes typing { 0%, 80%, 100% { transform: scale(0); } 40% { transform: scale(1); } }
  </style>
</head>
<body>
  <header>
    <span>âš½</span> è¶³çƒé¢„æµ‹ç ”ç©¶å‘˜ Copilot
  </header>
  <div id="chat-container">
    <div id="chat">
        <div class="msg assistant">
            <div class="bubble">ä½ å¥½ï¼æˆ‘æ˜¯ä½ çš„ AI è¶³çƒé¢„æµ‹åŠ©æ‰‹ ðŸ¤–ã€‚æˆ‘å¯ä»¥å¸®ä½ èŽ·å–ä»Šæ—¥èµ›ç¨‹ã€è¿è¡Œé¢„æµ‹æ¨¡åž‹ã€åˆ†æžå›žæµ‹æ•°æ®ã€‚æƒ³äº†è§£ç‚¹ä»€ä¹ˆï¼Ÿ</div>
        </div>
    </div>
    <div id="box">
      <textarea id="input" placeholder="è¾“å…¥ä½ çš„é—®é¢˜ï¼Œå¦‚ï¼šå¸®æˆ‘æŸ¥ä¸€ä¸‹ä»Šå¤©æœ‰ä»€ä¹ˆæ¯”èµ›ï¼Œå¹¶è·‘ä¸€ä¸‹é¢„æµ‹æŽ¨è..."></textarea>
      <button id="send">å‘é€ ðŸš€</button>
    </div>
  </div>
  <script>
    const chatDiv = document.getElementById('chat');
    const input = document.getElementById('input');
    const sendBtn = document.getElementById('send');
    const hist = [];
    
    // Configure marked to use breaks for newlines
    marked.setOptions({ breaks: true, gfm: true });

    function addMessage(role, text) {
      const wrapper = document.createElement('div');
      wrapper.className = `msg ${role}`;
      
      const bubble = document.createElement('div');
      bubble.className = 'bubble';
      
      if (role === 'assistant') {
          bubble.innerHTML = marked.parse(text);
      } else {
          bubble.textContent = text;
      }
      
      wrapper.appendChild(bubble);
      chatDiv.appendChild(wrapper);
      chatDiv.scrollTop = chatDiv.scrollHeight;
    }

    function addLoading() {
        const wrapper = document.createElement('div');
        wrapper.className = 'msg assistant';
        wrapper.id = 'loading-msg';
        
        const bubble = document.createElement('div');
        bubble.className = 'bubble';
        bubble.innerHTML = '<div class="typing"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>';
        
        wrapper.appendChild(bubble);
        chatDiv.appendChild(wrapper);
        chatDiv.scrollTop = chatDiv.scrollHeight;
    }

    function removeLoading() {
        const loading = document.getElementById('loading-msg');
        if (loading) {
            loading.remove();
        }
    }

    async function send() {
      const text = input.value.trim();
      if(!text) return;
      
      input.value = '';
      addMessage('user', text);
      hist.push({role:'user', content:text});
      
      sendBtn.disabled = true;
      input.disabled = true;
      addLoading();
      
      try {
        const r = await fetch('/chat', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({messages: hist})
        });
        const j = await r.json();
        removeLoading();
        
        const content = j.content || 'âš ï¸ [error] æ— å†…å®¹';
        addMessage('assistant', content);
        hist.push({role:'assistant', content});
      } catch(e) {
        removeLoading();
        addMessage('assistant', 'âŒ [error] ' + e);
      } finally {
        sendBtn.disabled = false;
        input.disabled = false;
        input.focus();
      }
    }
    
    sendBtn.addEventListener('click', send);
    input.addEventListener('keydown', e => {
      if (!e.shiftKey && e.key === 'Enter') {
          e.preventDefault();
          send();
      }
    });
  </script>
</body>
</html>
    """
    return HTMLResponse(content=html)


# ===== Research Copilot (Execution) =====
import json as _json
from typing import Optional
import pandas as _pd
from research_director.director import ResearchDirector
from config.settings import get_settings as _get_settings


def _safe_read_json(path: Path) -> dict:
    try:
        return _json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _safe_read_csv(path: Path) -> _pd.DataFrame:
    try:
        return _pd.read_csv(path)
    except Exception:
        return _pd.DataFrame()


def _default_artifacts() -> dict[str, object]:
    s = _get_settings()
    out: dict[str, object] = {}
    out["metrics_path"] = str(s.eval_metrics_path)
    out["results_path"] = str(s.eval_results_path)
    out["model_compare_path"] = str(s.eval_model_compare_path)
    out["reliability_table_path"] = str(s.eval_reliability_table_path)
    out["model_registry_path"] = str(s.research_model_registry_path)
    out["latest_execution_summary_path"] = str(s.research_latest_execution_summary_path)
    # upgrade_report åœ¨å…·ä½“ run_dir ä¸‹ï¼Œä¼˜å…ˆä»Ž latest_execution_summary çš„ run_dir æŽ¨æ–­
    latest = _safe_read_json(s.research_latest_execution_summary_path)
    up_path: Optional[Path] = None
    if isinstance(latest, dict) and latest.get("run_id"):
        rid = str(latest["run_id"])
        run_dir = s.research_director_runs_dir / rid
        cand = run_dir / "upgrade_report.json"
        if cand.exists():
            up_path = cand
    out["upgrade_report_path"] = str(up_path) if up_path else None
    return out


def _summarize_distribution(results: _pd.DataFrame) -> dict[str, object]:
    out: dict[str, object] = {"n": 0}
    if results.empty:
        return out
    n = int(len(results))
    out["n"] = n
    cols = ["p_home", "p_draw", "p_away"]
    if not set(cols) <= set(results.columns):
        return out
    P = results[cols].to_numpy(dtype=float, copy=False)
    avg = P.mean(axis=0).tolist()
    out["avg_p"] = {"home": float(avg[0]), "draw": float(avg[1]), "away": float(avg[2])}
    pred_idx = P.argmax(axis=1)
    pred_counts = {0: int((pred_idx == 0).sum()), 1: int((pred_idx == 1).sum()), 2: int((pred_idx == 2).sum())}
    out["pred_label_counts"] = {"H": pred_counts[0], "D": pred_counts[1], "A": pred_counts[2]}
    if "actual" in results.columns:
        y = results["actual"].astype(str).str.upper()
        out["actual_label_counts"] = {
            "H": int((y == "H").sum()),
            "D": int((y == "D").sum()),
            "A": int((y == "A").sum()),
        }
    # ç®€å•åç½®åˆ¤å®šï¼šå•ç±»é¢„æµ‹å æ¯” > 0.7 æˆ– avg_p æŸä¸€ç±» > 0.6
    bias_flags: list[str] = []
    total_pred = float(sum(out["pred_label_counts"].values()))
    if total_pred > 0:
        for k, v in out["pred_label_counts"].items():
            if float(v) / total_pred > 0.7:
                bias_flags.append(f"predicted_{k}_dominant")
                break
    ap = out.get("avg_p") or {}
    if any(float(x) > 0.6 for x in ap.values()):
        bias_flags.append("probability_mass_skewed")
    out["bias_flags"] = bias_flags
    return out


def analyze_latest_run() -> dict[str, object]:
    s = _get_settings()
    metrics = _safe_read_json(s.eval_metrics_path)
    results = _safe_read_csv(s.eval_results_path)
    dist = _summarize_distribution(results)
    suggestions: list[str] = []
    if metrics:
        if float(metrics.get("brier", 0.0)) > 0.5:
            suggestions.append("è€ƒè™‘å¼•å…¥æ ¡å‡†ï¼ˆsigmoidï¼‰å¹¶æ¯”è¾ƒ reliability gap")
        if float(metrics.get("logloss", 0.0)) > 1.0:
            suggestions.append("å°è¯•æ›´å¼ºæ¨¡åž‹ï¼ˆlightgbmï¼‰æˆ–å‡çº§åˆ° v2/v3 ç‰¹å¾")
    if "bias_flags" in dist and dist["bias_flags"]:
        suggestions.append("æ£€æµ‹ç±»åˆ«ä¸å¹³è¡¡æˆ–èµ”çŽ‡åˆ†å¸ƒå¼‚å¸¸ï¼Œæ£€æŸ¥è”èµ›/èµ›å­£æ··åˆä¸Žæ ‡ç­¾è´¨é‡")
    return {
        "n_samples": int(dist.get("n", 0)),
        "brier": float(metrics.get("brier", 0.0)) if metrics else None,
        "logloss": float(metrics.get("logloss", 0.0)) if metrics else None,
        "distribution": dist,
        "suggestions": suggestions,
    }


def explain_high_brier() -> dict[str, object]:
    s = _get_settings()
    metrics = _safe_read_json(s.eval_metrics_path)
    results = _safe_read_csv(s.eval_results_path)
    dist = _summarize_distribution(results)
    reasons: list[str] = []
    if dist.get("bias_flags"):
        reasons.append("ç±»åˆ«æˆ–æ¦‚çŽ‡åˆ†å¸ƒåç½®ï¼ˆbias_flags å‘½ä¸­ï¼‰")
    reasons.append("ç‰¹å¾ä¸è¶³ï¼šå½“å‰ v1 ä»…èµ”çŽ‡ï¼Œå»ºè®®é‡‡ç”¨ v2 åŠ å…¥ xg/injury/line_move")
    reasons.append("æ¨¡åž‹è¡¨è¾¾èƒ½åŠ›ï¼šlogit å¯èƒ½ä¸è¶³ï¼Œå¯è¯• lightgbm æˆ– stacking")
    if metrics and float(metrics.get("brier", 0.0)) > 0.5:
        reasons.append("æœªæ ¡å‡†ï¼šå°è¯• sigmoid æ ¡å‡†å¹¶è§‚å¯Ÿ reliability_table")
    if "actual_label_counts" in dist:
        alc = dist["actual_label_counts"]
        total = sum(alc.values()) or 1
        if max(alc.values()) / total > 0.6:
            reasons.append("ç±»åˆ«ä¸å¹³è¡¡ï¼šå®žé™…æ ‡ç­¾åˆ†å¸ƒå€¾æ–œï¼Œå»ºè®®åœ¨åˆ‡åˆ†/é‡‡æ ·ä¸Šåšçº¦æŸ")
    return {"brier": metrics.get("brier") if metrics else None, "reasons": reasons, "distribution": dist}


def _parse_run_experiment(text: str) -> dict[str, str]:
    t = text.lower()
    mt = "logit"
    fv = "v1"
    cal = "none"
    dm = "mock"
    for k in ("lightgbm", "lgbm"): 
        if k in t:
            mt = "lightgbm"
    if "stacking_oof" in t:
        mt = "stacking_oof"
    elif "stacking" in t:
        mt = "stacking"
    if "v3" in t:
        fv = "v3"
    elif "v2" in t:
        fv = "v2"
    if "sigmoid" in t:
        cal = "sigmoid"
    elif "isotonic" in t:
        cal = "isotonic"
    if "real" in t or "çœŸå®ž" in t or "ä»Šå¤©" in t or "ä»Šæ—¥" in t or "live" in t:
        dm = "real"
    return {"model_type": mt, "feature_version": fv, "calibration": cal, "data_mode": dm}


def run_experiment(command_text: str) -> dict[str, object]:
    cfg = _parse_run_experiment(command_text)
    director = ResearchDirector()
    wf = "candidate_model_upgrade" if ("upgrade" in command_text.lower() or "æ™‹å‡" in command_text) else "daily_prediction"
    ctx = {
        "model_type": cfg["model_type"],
        "feature_version": cfg["feature_version"],
        "calibration": cfg["calibration"],
        "data_mode": cfg["data_mode"],
        "use_verifier": False,
    }
    if cfg["data_mode"] == "real":
        from datetime import datetime, timezone
        from config.settings import get_settings
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        s = get_settings()
        schedule_path = s.project_root / "data" / "raw" / "schedules" / f"schedule_{today}.csv"
        if schedule_path.exists():
            ctx["raw_matches_csv"] = str(schedule_path)
            # mapping_path defaults to none, we don't strictly need it if we use standard columns, but the scout agent demands it.
            # We can create a dummy mapping.json
            mapping_path = schedule_path.parent / "mapping.json"
            if not mapping_path.exists():
                mapping_path.write_text("{}", encoding="utf-8")
            ctx["mapping_path"] = str(mapping_path)
    
    out = director.run(wf, context=ctx)
    metrics = out.get("metrics") if isinstance(out.get("metrics"), dict) else {}
    decision = out.get("decision") if isinstance(out.get("decision"), dict) else None
    return {
        "run_id": out.get("run_id"),
        "workflow": wf,
        "status": out.get("status"),
        "metrics_summary": metrics,
        "decision": decision,
    }


def show_system_status() -> dict[str, object]:
    s = _get_settings()
    reg = _safe_read_json(s.research_model_registry_path)
    latest = _safe_read_json(s.research_latest_execution_summary_path)
    metrics = _safe_read_json(s.eval_metrics_path)
    prod = None
    try:
        prod = reg.get("current_production_model")
    except Exception:
        prod = None
    return {
        "production_model": prod,
        "latest_run_id": latest.get("run_id") if isinstance(latest, dict) else None,
        "latest_metrics": {"brier": metrics.get("brier"), "logloss": metrics.get("logloss")} if metrics else None,
        "latest_decision": latest.get("decision_result") if isinstance(latest, dict) else None,
    }


def _read_backtest_status() -> dict[str, object]:
    s = _get_settings()
    base = s.project_root / "artifacts" / "backtest"
    summary_path = base / "summary.json"
    bets_path = base / "bets.csv"
    by_league_path = base / "by_league.csv"
    curve_path = base / "equity_curve.csv"
    summary = _safe_read_json(summary_path)
    out: dict[str, object] = {
        "paths": {
            "summary_path": str(summary_path),
            "bets_path": str(bets_path),
            "by_league_path": str(by_league_path),
            "equity_curve_path": str(curve_path),
        },
        "summary": summary if summary else None,
    }
    if by_league_path.exists():
        df = _safe_read_csv(by_league_path)
        if not df.empty:
            out["by_league_top"] = df.head(5).to_dict(orient="records")
    return out


def _fmt_float(x: object, *, digits: int = 4) -> str:
    try:
        v = float(x)  # type: ignore[arg-type]
    except Exception:
        return "NA"
    if v != v:
        return "NA"
    return f"{v:.{digits}f}"


def _format_latest_analysis_message() -> str:
    s = _get_settings()
    a = analyze_latest_run()
    bt = _read_backtest_status()
    dist = a.get("distribution") if isinstance(a.get("distribution"), dict) else {}
    avg_p = dist.get("avg_p") if isinstance(dist.get("avg_p"), dict) else {}
    bias = dist.get("bias_flags") if isinstance(dist.get("bias_flags"), list) else []
    suggestions = a.get("suggestions") if isinstance(a.get("suggestions"), list) else []
    lines = [
        f"- æ ·æœ¬é‡(n_samples): {a.get('n_samples')}",
        f"- brier: {_fmt_float(a.get('brier'))}",
        f"- logloss: {_fmt_float(a.get('logloss'))}",
        f"- æ¦‚çŽ‡å‡å€¼(avg_p): H={_fmt_float(avg_p.get('home'))}, D={_fmt_float(avg_p.get('draw'))}, A={_fmt_float(avg_p.get('away'))}",
        f"- åç½®(bias_flags): {', '.join(str(x) for x in bias) if bias else 'æ— æ˜Žæ˜¾åç½®'}",
        f"- äº§ç‰©: {s.eval_metrics_path} | {s.eval_results_path} | {s.eval_reliability_table_path}",
    ]
    if bt.get("summary"):
        sm = bt["summary"]  # type: ignore[assignment]
        lines.append(
            f"- å›žæµ‹: n_bets={sm.get('n_bets')} profit={_fmt_float(sm.get('profit'))} roi={_fmt_float(sm.get('roi'))} max_dd={_fmt_float(sm.get('max_drawdown'))} final={_fmt_float(sm.get('final_bankroll'))}"
        )
        lines.append(f"- å›žæµ‹äº§ç‰©: {bt['paths']['summary_path']} | {bt['paths']['bets_path']}")
    if suggestions:
        lines.append("- å»ºè®®: " + "ï¼›".join(str(x) for x in suggestions))
    return "\n".join(lines)


def _format_high_brier_message() -> str:
    s = _get_settings()
    x = explain_high_brier()
    rs = x.get("reasons") if isinstance(x.get("reasons"), list) else []
    return "\n".join(
        [
            f"- brier: {_fmt_float(x.get('brier'))}",
            f"- äº§ç‰©: {s.eval_metrics_path} | {s.eval_results_path} | {s.eval_reliability_table_path}",
            "- å¯èƒ½åŽŸå› :",
        ]
        + [f"  - {r}" for r in rs]
    )


def _format_backtest_message() -> str:
    bt = _read_backtest_status()
    sm = bt.get("summary")
    if not sm:
        return "\n".join(
            [
                "- æœªæ‰¾åˆ°å›žæµ‹äº§ç‰© summary.json",
                f"- æœŸæœ›è·¯å¾„: {bt['paths']['summary_path']}",
                "- å…ˆè¿è¡Œ: python scripts/run_backtest.py --pred-path artifacts/eval/results.csv --data-path data/processed/real_matches_standardized.csv --out-dir artifacts/backtest",
            ]
        )
    top = bt.get("by_league_top")
    lines = [
        f"- å›žæµ‹: n_bets={sm.get('n_bets')} profit={_fmt_float(sm.get('profit'))} roi={_fmt_float(sm.get('roi'))} hit_rate={_fmt_float(sm.get('hit_rate'))} max_dd={_fmt_float(sm.get('max_drawdown'))} final={_fmt_float(sm.get('final_bankroll'))}",
        f"- äº§ç‰©: {bt['paths']['summary_path']} | {bt['paths']['bets_path']} | {bt['paths']['by_league_path']} | {bt['paths']['equity_curve_path']}",
    ]
    if isinstance(top, list) and top:
        lines.append("- è”èµ›Top(æŒ‰ n_bets): " + "; ".join(f"{r.get('league')} n={r.get('n_bets')} roi={_fmt_float(r.get('roi'))}" for r in top))
    return "\n".join(lines)


def _format_status_message() -> str:
    s = show_system_status()
    prod = s.get("production_model")
    latest_run = s.get("latest_run_id")
    latest_metrics = s.get("latest_metrics") if isinstance(s.get("latest_metrics"), dict) else {}
    return "\n".join(
        [
            f"- production_model: {prod.get('model_id') if isinstance(prod, dict) else None}",
            f"- latest_run_id: {latest_run}",
            f"- latest_metrics: brier={_fmt_float(latest_metrics.get('brier'))}, logloss={_fmt_float(latest_metrics.get('logloss'))}",
            f"- latest_decision: {s.get('latest_decision')}",
        ]
    )


def _format_today_matches_message() -> str:
    from ingest.fetch_schedule import FootballDataClient
    from datetime import datetime, timezone
    
    try:
        client = FootballDataClient()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        df = client.fetch_today_matches(today)

        if (
            not df.empty
            and "is_predictable" in df.columns
            and not df["is_predictable"].fillna(False).any()
        ):
            lines = [f"**ä»Šæ—¥ ({today}) å…¬å¼€èµ›ç¨‹**ï¼š", f"å…±èŽ·å–åˆ° {len(df)} åœºæ¯”èµ›ã€‚"]
            for _, row in df.iterrows():
                lines.append(
                    f"- {row['league']}: {row['home_team']} vs {row['away_team']} ({row['date']})"
                )
            out_path = client.save_schedule(df, today)
            lines.append(f"\næ•°æ®å·²ä¿å­˜è‡³: `{out_path}`")
            lines.append("å½“å‰æ¥æºä¸å«çœŸå®žèµ”çŽ‡ï¼Œå·²æ ‡è®°ä¸º schedule_onlyï¼Œä¸ä¼šç”¨äºŽæ¨¡åž‹é¢„æµ‹ã€‚")
            return "\n".join(lines)
        
        if df.empty:
            return f"ä»Šå¤© ({today}) æ²¡æœ‰èŽ·å–åˆ°ä»»ä½•èµ›ç¨‹æ•°æ®ã€‚"
        
        lines = [f"**ä»Šæ—¥ ({today}) å®žæ—¶èµ›ç¨‹åŠé«˜çº§ç‰¹å¾**ï¼š", f"å…±èŽ·å–åˆ° {len(df)} åœºæ¯”èµ›ã€‚"]
        
        for _, row in df.iterrows():
            match_str = f"- {row['league']}: {row['home_team']} vs {row['away_team']} ({row['date']})"
            stats_str = f"  - èµ”çŽ‡: ä¸»èƒœ {row['odds_home']}, å¹³ {row['odds_draw']}, å®¢èƒœ {row['odds_away']}"
            adv_stats_str = f"  - é«˜çº§ç‰¹å¾: xGä¸» {row['xg_home']} / xGå®¢ {row['xg_away']}, èµ”çŽ‡å˜åŠ¨ {row['line_move']}, ä¼¤åœæ ‡è®° {row['injury_flag']}"
            lines.extend([match_str, stats_str, adv_stats_str])
            
        out_path = client.save_schedule(df, today)
        lines.append(f"\n*æ•°æ®å·²ä¿å­˜è‡³*: `{out_path}`")
        lines.append("*æç¤º*: ä½ å¯ä»¥å›žå¤â€œç”¨è¿™äº›æ•°æ®è·‘é¢„æµ‹â€æ¥è¿è¡Œ `daily_prediction` å·¥ä½œæµè¿›è¡Œä»Šæ—¥æŽ¨å•ï¼")
        return "\n".join(lines)
    except Exception as e:
        return f"[error] èŽ·å–ä»Šæ—¥èµ›ç¨‹å¤±è´¥: {e}"

def _try_handle_natural_language(text: str) -> str | None:
    t = text.strip().lower()
    if not t:
        return None

    if any(k in t for k in ("ä»Šå¤©", "ä»Šæ—¥", "çƒèµ›", "èµ›ç¨‹", "æ¯”èµ›", "live", "å®žæ—¶")) and not any(k in t for k in ("è·‘", "è®­ç»ƒ", "é¢„æµ‹", "è¯„ä¼°")):
        return _format_today_matches_message()

    if any(k in t for k in ("æ€»ç»“", "æ¦‚è§ˆ", "åˆ†æž", "æœ€æ–°ç»“æžœ", "è¡¨çŽ°", "æŒ‡æ ‡", "metrics", "logloss", "brier")):
        if any(k in t for k in ("ä¸ºä»€ä¹ˆ", "åŽŸå› ", "é«˜", "è§£é‡Š")) and ("brier" in t or "logloss" in t or "æ¦‚çŽ‡" in t):
            return _format_high_brier_message()
        return _format_latest_analysis_message()

    if any(k in t for k in ("å›žæµ‹", "roi", "æ”¶ç›Š", "äº", "å›žæ’¤", "ä¸‹æ³¨", "bets")):
        return _format_backtest_message()

    if any(k in t for k in ("è·‘", "è¯•éªŒ", "å®žéªŒ", "å¯¹æ¯”", "è®­ç»ƒ", "é¢„æµ‹", "upgrade", "æ™‹å‡", "æŽ¨å•")) and any(
        k in t for k in ("logit", "lightgbm", "lgbm", "stacking", "v1", "v2", "v3", "sigmoid", "isotonic", "real", "çœŸå®ž", "ä»Šå¤©", "ä»Šæ—¥", "è¿™äº›")
    ):
        out = run_experiment(text)
        return _json.dumps(out, ensure_ascii=False, indent=2)

    if any(k in t for k in ("çŠ¶æ€", "ç³»ç»ŸçŠ¶æ€", "production", "registry", "æ¨¡åž‹æ³¨å†Œ", "å½“å‰æ¨¡åž‹")):
        return _format_status_message()

    return None


@app.get("/copilot/artifacts")
def copilot_artifacts() -> dict[str, object]:
    return _default_artifacts()


@app.get("/copilot/analyze")
def copilot_analyze() -> dict[str, object]:
    return analyze_latest_run()


@app.get("/copilot/explain-high-brier")
def copilot_explain_high_brier() -> dict[str, object]:
    return explain_high_brier()


class RunExperimentRequest(BaseModel):
    command_text: str


@app.post("/copilot/run")
def copilot_run(req: RunExperimentRequest) -> dict[str, object]:
    return run_experiment(req.command_text)


@app.get("/copilot/status")
def copilot_status() -> dict[str, object]:
    return show_system_status()


# Command router in chat: support /analyze, /explain-brier, /run <text>, /status
@app.post("/chat2", response_model=ChatResponse)
def chat2(req: ChatRequest) -> ChatResponse:
    if not req.messages:
        return ChatResponse(content="no messages")
    last = req.messages[-1].content.strip()
    if last.startswith("/analyze"):
        x = analyze_latest_run()
        return ChatResponse(
            content=(
                f"- n_samples: {x.get('n_samples')}\n"
                f"- brier: {x.get('brier')}\n"
                f"- logloss: {x.get('logloss')}\n"
                f"- bias_flags: {', '.join(x.get('distribution', {}).get('bias_flags', []))}\n"
                f"- suggestions: {'; '.join(x.get('suggestions', []))}"
            )
        )
    if last.startswith("/explain-brier"):
        x = explain_high_brier()
        rs = x.get("reasons", [])
        return ChatResponse(content="- " + "\n- ".join(str(r) for r in rs))
    if last.startswith("/run"):
        cmd = last[len("/run"):].strip()
        x = run_experiment(cmd or "logit v1 none mock")
        return ChatResponse(content=_json.dumps(x, ensure_ascii=False, indent=2))
    if last.startswith("/status"):
        x = show_system_status()
        return ChatResponse(content=_json.dumps(x, ensure_ascii=False, indent=2))
    return chat(req)


@app.post("/api/ingest/football-data", response_model=P0IngestResponse)
def p0_ingest_football_data(date_from: str | None = None, date_to: str | None = None) -> P0IngestResponse:
    d0 = date_from or datetime.utcnow().strftime("%Y-%m-%d")
    d1 = date_to or d0
    try:
        rows = fetch_major_league_matches(d0, d1)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"ingest_failed: {e}. Please set FOOTBALL_DATA_API_KEY in football-predictor/.env",
        )
    conn = p0_db_connect()
    try:
        n = p0_upsert_fixtures(conn, rows)
    finally:
        conn.close()
    return P0IngestResponse(date_from=d0, date_to=d1, inserted_or_updated=n, db_path=str(p0_get_db_path()))


@app.get("/api/fixtures", response_model=P0FixturesResponse)
def p0_list_fixtures(date: str | None = None, date_from: str | None = None, date_to: str | None = None) -> P0FixturesResponse:
    if date:
        d0 = date
        d1 = date
    else:
        d0 = date_from or datetime.utcnow().strftime("%Y-%m-%d")
        d1 = date_to or d0
    conn = p0_db_connect()
    try:
        fixtures = p0_select_fixtures_by_date(conn, d0, d1)
    finally:
        conn.close()
    return P0FixturesResponse(date_from=d0, date_to=d1, count=len(fixtures), fixtures=[P0Fixture(**f) for f in fixtures])


def _p0_predict_fixture(conn, fixture_id: int) -> P0Prediction:
    fx = p0_get_fixture(conn, fixture_id)
    if not fx:
        raise HTTPException(status_code=404, detail=f"fixture not found: {fixture_id}")
    home_id = fx.get("home_team_id")
    away_id = fx.get("away_team_id")
    utc_date = fx.get("utc_date")
    if not home_id or not away_id or not utc_date:
        raise HTTPException(status_code=400, detail=f"fixture missing fields: {fixture_id}")
    home_matches = p0_select_recent_finished_matches(conn, int(home_id), str(utc_date), limit=12)
    away_matches = p0_select_recent_finished_matches(conn, int(away_id), str(utc_date), limit=12)
    home_avg = compute_team_averages(home_matches, int(home_id))
    away_avg = compute_team_averages(away_matches, int(away_id))
    lam_h, lam_a = compute_lambdas(home_avg, away_avg)
    p_home, p_draw, p_away = predict_1x2(lam_h, lam_a)
    conf = confidence_from_probs(p_home, p_draw, p_away)
    factors: list[str] = []
    factors.append(f"ä¸»é˜Ÿè¿‘{home_avg.matches or 0}åœºï¼šåœºå‡è¿›çƒ{home_avg.goals_for:.2f}ï¼Œåœºå‡å¤±çƒ{home_avg.goals_against:.2f}")
    factors.append(f"å®¢é˜Ÿè¿‘{away_avg.matches or 0}åœºï¼šåœºå‡è¿›çƒ{away_avg.goals_for:.2f}ï¼Œåœºå‡å¤±çƒ{away_avg.goals_against:.2f}")
    factors.append(f"æ³Šæ¾æœŸæœ›è¿›çƒï¼šä¸»{lam_h:.2f} vs å®¢{lam_a:.2f}")
    return P0Prediction(
        fixture_id=fixture_id,
        p_home=float(p_home),
        p_draw=float(p_draw),
        p_away=float(p_away),
        confidence=float(conf),
        lambda_home=float(lam_h),
        lambda_away=float(lam_a),
        factors=factors,
    )


@app.post("/api/predictions", response_model=P0PredictionsResponse)
def p0_predict(req: P0PredictionsRequest) -> P0PredictionsResponse:
    fixture_ids: list[int] = []
    if req.fixture_ids:
        fixture_ids = [int(x) for x in req.fixture_ids]
    elif req.date:
        conn0 = p0_db_connect()
        try:
            fs = p0_select_fixtures_by_date(conn0, req.date, req.date)
            fixture_ids = [int(f["fixture_id"]) for f in fs]
        finally:
            conn0.close()
    else:
        raise HTTPException(status_code=400, detail="provide fixture_ids or date")

    conn = p0_db_connect()
    try:
        preds = [_p0_predict_fixture(conn, fid) for fid in fixture_ids]
    finally:
        conn.close()
    return P0PredictionsResponse(count=len(preds), predictions=preds)


@app.post("/api/chat", response_model=ChatResponse)
def p0_chat(req: ChatRequest) -> ChatResponse:
    last_user = ""
    for m in reversed(req.messages or []):
        if m.role == "user":
            last_user = (m.content or "").strip()
            break

    today_utc = datetime.utcnow().strftime("%Y-%m-%d")

    def _extract_date(text: str) -> str | None:
        import re

        m = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
        return m.group(1) if m else None

    q = last_user.lower()
    q_date = _extract_date(last_user) or today_utc

    if any(k in q for k in ("èµ›ç¨‹", "æ¯”èµ›", "ä»Šå¤©", "ä»Šæ—¥", "fixtures", "matches", "schedule")) and not any(
        k in q for k in ("é¢„æµ‹", "prob", "æ¦‚çŽ‡", "èƒœå¹³è´Ÿ")
    ):
        conn = p0_db_connect()
        try:
            fs = p0_select_fixtures_by_date(conn, q_date, q_date)
        finally:
            conn.close()
        if not fs:
            return ChatResponse(
                content=(
                    f"# ä»Šæ—¥èµ›ç¨‹ï¼ˆ{q_date}ï¼‰\n\n"
                    "æ•°æ®åº“é‡Œè¿˜æ²¡æœ‰è¿™ä¸€å¤©çš„æ¯”èµ›æ•°æ®ã€‚\n\n"
                    "ä½ å¯ä»¥å…ˆå¯¼å…¥ï¼š\n\n"
                    f"- è°ƒç”¨åŽç«¯ï¼š`POST /api/ingest/football-data?date_from={q_date}&date_to={q_date}`\n"
                    "- æˆ–åœ¨å‰ç«¯ã€èµ›ç¨‹ã€‘é¡µç‚¹å‡»â€œå¯¼å…¥â€\n\n"
                    "å¯¼å…¥æˆåŠŸåŽï¼Œå†é—®æˆ‘â€œä»Šå¤©æœ‰ä»€ä¹ˆæ¯”èµ›ï¼Ÿâ€æˆ‘ä¼šç»™ä½ è¡¨æ ¼åˆ—è¡¨ã€‚"
                )
            )
        lines = [f"# ä»Šæ—¥èµ›ç¨‹ï¼ˆ{q_date}ï¼‰", "", "| å¼€èµ›(UTC) | è”èµ› | ä¸»é˜Ÿ | å®¢é˜Ÿ | çŠ¶æ€ | æ¯”åˆ† |", "|---|---|---|---|---|---|"]
        for r in fs:
            t = (r.get("utc_date") or "")[11:16] or "-"
            league = r.get("competition_name") or r.get("competition_code") or "-"
            home = r.get("home_team_name") or "-"
            away = r.get("away_team_name") or "-"
            st = r.get("status") or "-"
            sc = "-"
            if r.get("home_score") is not None and r.get("away_score") is not None:
                sc = f"{r.get('home_score')}-{r.get('away_score')}"
            lines.append(f"| {t} | {league} | {home} | {away} | {st} | {sc} |")
        return ChatResponse(content="\n".join(lines))

    if any(k in q for k in ("é¢„æµ‹", "prob", "æ¦‚çŽ‡", "èƒœå¹³è´Ÿ")):
        try:
            res = p0_predict(P0PredictionsRequest(date=q_date))
        except HTTPException as e:
            return ChatResponse(content=f"é¢„æµ‹å¤±è´¥ï¼š{e.detail}")
        if not res.predictions:
            return ChatResponse(
                content=(
                    f"# ä»Šæ—¥é¢„æµ‹ï¼ˆ{q_date}ï¼‰\n\n"
                    "æ•°æ®åº“é‡Œè¿˜æ²¡æœ‰è¿™ä¸€å¤©çš„æ¯”èµ›æ•°æ®ï¼Œå…ˆå¯¼å…¥åŽå†é¢„æµ‹ï¼š\n\n"
                    f"- `POST /api/ingest/football-data?date_from={q_date}&date_to={q_date}`"
                )
            )
        conn = p0_db_connect()
        try:
            fixtures = {f["fixture_id"]: f for f in p0_select_fixtures_by_date(conn, q_date, q_date)}
        finally:
            conn.close()
        lines = [f"# ä»Šæ—¥é¢„æµ‹ï¼ˆ{q_date}ï¼‰", "", "| å¯¹é˜µ | ä¸»èƒœ | å¹³ | å®¢èƒœ | ç½®ä¿¡ |", "|---|---:|---:|---:|---:|"]
        for p in res.predictions:
            fx = fixtures.get(p.fixture_id) or {}
            home = fx.get("home_team_name") or "ä¸»é˜Ÿ"
            away = fx.get("away_team_name") or "å®¢é˜Ÿ"
            lines.append(
                "| "
                + f"{home} vs {away}"
                + " | "
                + f"{p.p_home:.3f}"
                + " | "
                + f"{p.p_draw:.3f}"
                + " | "
                + f"{p.p_away:.3f}"
                + " | "
                + f"{p.confidence:.2f}"
                + " |"
            )
        lines.append("\n## è¯´æ˜Ž\n- é¢„æµ‹ä¸ºæ³Šæ¾åŸºçº¿ï¼›ç½®ä¿¡åº¦æ¥è‡ªæ¦‚çŽ‡åˆ†å¸ƒç†µï¼ˆè¶Šå°–é”è¶Šé«˜ï¼‰ã€‚")
        return ChatResponse(content="\n".join(lines))

    sys_prompt = (
        f"ä½ æ˜¯AIçƒèµ›é¢„æµ‹ç³»ç»Ÿçš„åŠ©æ‰‹ï¼ˆä»Šå¤©UTCæ—¥æœŸï¼š{today_utc}ï¼‰ã€‚"
        "ä½ å¿…é¡»åŸºäºŽå·¥å…·è¿”å›žçš„æ•°æ®å›žç­”ï¼Œä¸è¦ç¼–é€ æ¯”èµ›ã€èµ”çŽ‡æˆ–ä¼¤åœã€‚"
        "å½“ç”¨æˆ·è¯¢é—®èµ›ç¨‹/æ¯”èµ›/é¢„æµ‹æ—¶ï¼Œä½ å¿…é¡»å…ˆè°ƒç”¨å·¥å…·ï¼ˆget_fixtures/predict_by_date/predict_by_fixture_idsï¼‰ã€‚"
        "å¦‚æžœæ•°æ®åº“æ²¡æœ‰æ•°æ®ï¼Œä½ åº”è¯¥å»ºè®®ç”¨æˆ·å…ˆè°ƒç”¨ ingest_football_data å¯¼å…¥å¯¹åº”æ—¥æœŸèŒƒå›´ã€‚"
        "æœ€ç»ˆè¾“å‡ºä½¿ç”¨ Markdownï¼šå…ˆè¡¨æ ¼ï¼Œå†ç»™å‡º 3-5 æ¡å…³é”®å› ç´ ã€‚"
    )
    msgs = [{"role": "system", "content": sys_prompt}] + [{"role": m.role, "content": m.content} for m in req.messages]
    model = (
        req.model
        or os.getenv("CODING_PLAN_MODEL")
        or os.getenv("BAILIAN_MODEL")
        or os.getenv("DASHSCOPE_MODEL")
        or os.getenv("OPENROUTER_MODEL")
        or os.getenv("OPENAI_MODEL")
        or "qwen-plus"
    )
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_fixtures",
                "description": "ä»Žæ•°æ®åº“èŽ·å–æŒ‡å®šæ—¥æœŸèŒƒå›´çš„èµ›ç¨‹ï¼ˆå¦‚ä»Šå¤©çš„æ¯”èµ›ï¼‰ã€‚",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date_from": {"type": "string"},
                        "date_to": {"type": "string"}
                    },
                    "required": ["date_from", "date_to"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "predict_by_date",
                "description": "å¯¹æŒ‡å®šæ—¥æœŸçš„æ‰€æœ‰æ¯”èµ›ç”Ÿæˆæ³Šæ¾åŸºçº¿é¢„æµ‹ï¼ˆèƒœå¹³è´Ÿæ¦‚çŽ‡ï¼‰ã€‚",
                "parameters": {
                    "type": "object",
                    "properties": {"date": {"type": "string"}},
                    "required": ["date"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "predict_by_fixture_ids",
                "description": "å¯¹ç»™å®š fixture_id åˆ—è¡¨ç”Ÿæˆæ³Šæ¾åŸºçº¿é¢„æµ‹ã€‚",
                "parameters": {
                    "type": "object",
                    "properties": {"fixture_ids": {"type": "array", "items": {"type": "integer"}}},
                    "required": ["fixture_ids"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "ingest_football_data",
                "description": "ä»Ž football-data.org æŠ“å–æŒ‡å®šæ—¥æœŸèŒƒå›´çš„äº”å¤§è”èµ›æ¯”èµ›å¹¶å…¥åº“ã€‚",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date_from": {"type": "string"},
                        "date_to": {"type": "string"}
                    },
                    "required": ["date_from", "date_to"]
                }
            }
        },
    ]

    text, tool_calls = _call_openai_chat(msgs, model, tools)
    if not tool_calls:
        return ChatResponse(content=text)

    tool_call = tool_calls[0]
    func_name = tool_call.get("function", {}).get("name")
    import json
    try:
        args = json.loads(tool_call.get("function", {}).get("arguments", "{}"))
    except Exception:
        args = {}

    tool_result = ""
    if func_name == "get_fixtures":
        d0 = str(args.get("date_from"))
        d1 = str(args.get("date_to"))
        conn = p0_db_connect()
        try:
            fs = p0_select_fixtures_by_date(conn, d0, d1)
        finally:
            conn.close()
        tool_result = json.dumps({"date_from": d0, "date_to": d1, "fixtures": fs}, ensure_ascii=False)
    elif func_name == "predict_by_date":
        d = str(args.get("date"))
        res = p0_predict(P0PredictionsRequest(date=d))
        tool_result = res.model_dump_json(indent=2, ensure_ascii=False)
    elif func_name == "predict_by_fixture_ids":
        ids = args.get("fixture_ids") or []
        res = p0_predict(P0PredictionsRequest(fixture_ids=[int(x) for x in ids]))
        tool_result = res.model_dump_json(indent=2, ensure_ascii=False)
    elif func_name == "ingest_football_data":
        d0 = str(args.get("date_from"))
        d1 = str(args.get("date_to"))
        res = p0_ingest_football_data(date_from=d0, date_to=d1)
        tool_result = res.model_dump_json(indent=2, ensure_ascii=False)

    msgs.append({"role": "assistant", "content": text or "", "tool_calls": tool_calls})
    msgs.append({"role": "tool", "tool_call_id": tool_call.get("id", ""), "name": func_name, "content": tool_result})
    final_text, _ = _call_openai_chat(msgs, model)
    return ChatResponse(content=final_text)
