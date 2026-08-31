from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.routes.chat import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    _call_openai_chat,
    chat,
    chat2,
    chat_ui,
    p0_chat,
    router as chat_router,
)
from api.observability import (
    ObservabilityMiddleware,
    RequestMetricsRegistry,
    data_runtime_metadata,
    model_runtime_metadata,
)
from api.routes.operations import RunExperimentRequest, build_operations_router
from api.services.research_copilot import (
    _default_artifacts,
    _fmt_float,
    _format_backtest_message,
    _format_high_brier_message,
    _format_latest_analysis_message,
    _format_status_message,
    _format_today_matches_message,
    _parse_run_experiment,
    _read_backtest_status,
    _safe_read_csv,
    _safe_read_json,
    _summarize_distribution,
    _try_handle_natural_language,
    analyze_latest_run,
    explain_high_brier,
    run_experiment,
    show_system_status,
)
from api.routes.p0 import P0Fixture
from api.routes.p0 import P0FixturesResponse
from api.routes.p0 import P0IngestResponse
from api.routes.p0 import P0Prediction
from api.routes.p0 import P0PredictionsRequest
from api.routes.p0 import P0PredictionsResponse
from api.routes.p0 import p0_ingest_football_data
from api.routes.p0 import p0_list_fixtures
from api.routes.p0 import p0_predict
from api.routes.p0 import router as p0_router
from api.routes.sporttery import (
    SportteryMarketRow,
    SportteryMarketsResponse,
    SportteryMarketSaveRequest,
    SportteryMarketSaveResponse,
    SportteryMarketSaveRow,
    SportteryPasteParseRequest,
    SportteryPasteParseResponse,
    _project_root,
    _raw_sporttery_file,
    _sporttery_market_history_path,
    _sporttery_market_path,
    _sporttery_rows_to_frame,
    _sporttery_template_rows,
    parse_world_cup_sporttery_paste,
    router as sporttery_router,
    save_world_cup_sporttery_handicap_markets,
    world_cup_sporttery_editor,
    world_cup_sporttery_handicap_markets,
)
from config.settings import ensure_project_dirs, get_settings
from features.basic_features import build_basic_features
from ingest.load_data import load_matches
from models.baseline_logit import BaselineLogitModel, load_baseline_model
from utils.logger import configure_logger, get_logger

from p0.db import connect as p0_db_connect
from p0.db import get_db_path as p0_get_db_path
from p0.db import init_db as p0_init_db


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


_MODEL: Any | None = None
_MODEL_PATH: Path | None = None


def _resolve_data_path(path: str, settings) -> str:
    try:
        load_matches(path)
        return path
    except FileNotFoundError:
        fallback = settings.project_root / "data" / "templates" / "sample_matches.csv"
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


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
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
    yield


app = FastAPI(title="football-predictor", version="0.1.0", lifespan=lifespan)
request_metrics = RequestMetricsRegistry()

_origins = os.getenv("CORS_ALLOW_ORIGINS") or "http://localhost:3000,http://127.0.0.1:3000"
allow_origins = [o.strip() for o in _origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Response-Time-Ms"],
)
app.add_middleware(ObservabilityMiddleware, registry=request_metrics)


app.include_router(sporttery_router)


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


def _runtime_status() -> dict[str, object]:
    settings = get_settings()
    model = model_runtime_metadata(_MODEL_PATH if _MODEL is not None else None)
    data = data_runtime_metadata(settings.eval_data_model_quality_gate_path)
    return {
        "service": {"name": "football-predictor", "version": app.version},
        "model_loaded": bool(model["loaded"]),
        "model_path": model["path"],
        "model_version": model["version"],
        "data_snapshot_version": data["snapshot_version"],
        "model": model,
        "data": data,
    }


app.include_router(
    build_operations_router(
        model_status=lambda: _runtime_status(),
        artifacts=_default_artifacts,
        analyze=analyze_latest_run,
        explain_high_brier=explain_high_brier,
        run_experiment=run_experiment,
        system_status=show_system_status,
        runtime_metrics=request_metrics.snapshot,
    )
)


app.include_router(p0_router)
app.include_router(chat_router)
