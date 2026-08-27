from __future__ import annotations

import json as _json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

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
from api.views import CHAT_UI_HTML
from config.settings import ensure_project_dirs, get_settings
from features.basic_features import build_basic_features
from ingest.load_data import load_matches
from models.baseline_logit import BaselineLogitModel, load_baseline_model
from utils.logger import configure_logger, get_logger

from p0.db import connect as p0_db_connect
from p0.db import get_db_path as p0_get_db_path
from p0.db import init_db as p0_init_db
from p0.db import select_fixtures_by_date as p0_select_fixtures_by_date


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

_origins = os.getenv("CORS_ALLOW_ORIGINS") or "http://localhost:3000,http://127.0.0.1:3000"
allow_origins = [o.strip() for o in _origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
        return f"[mock] 我已收到你的问题：{last[:120]} ...", []

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
        "你是本仓库的足球预测研究员 Copilot。"
        "你需要帮助用户完成：获取今日赛程、运行预测和训练实验、训练评估、指标解读、数据流审计、下一步实验建议。"
        "回答要简洁、可执行，并尽量引用产物路径与关键数字。你可以使用提供的工具（函数调用）来执行实际操作并获取数据。"
        "为了提供更好的用户体验，请你在回复中广泛使用 Markdown 格式，包括：表格（如展示比赛列表和指标）、加粗、列表，并且合理使用相关的 Emoji 图标（如 ⚽, 📈, 📉, 💡, ⚠️ 等）来点缀你的回复，使其美观易读。"
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
                "description": "获取今天或近期的足球比赛赛程，包括对阵双方、赔率、高级特征等。",
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
                "description": "执行模型训练或预测实验。当用户要求'跑'、'预测'、'训练'或'推单'时调用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command_text": {
                            "type": "string",
                            "description": "用户原始的请求文本，包含如 'logit v1 real' 或 'lightgbm v3' 等指令"
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
                "description": "分析最近一次实验的结果，包括 Brier、Logloss 和模型建议。",
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
                "description": "解释为什么最近的实验 Brier 或 Logloss 分数很高，分析模型的偏差。",
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
                "description": "获取当前系统的模型注册状态、生产模型信息。",
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
                "description": "获取最新的回测结果（收益、ROI、回撤等）。",
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
            tool_result = "调用成功，但没有返回结果。"

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
    return HTMLResponse(content=CHAT_UI_HTML)


app.include_router(
    build_operations_router(
        model_status=lambda: {
            "model_loaded": _MODEL is not None,
            "model_path": str(_MODEL_PATH) if _MODEL_PATH else None,
        },
        artifacts=_default_artifacts,
        analyze=analyze_latest_run,
        explain_high_brier=explain_high_brier,
        run_experiment=run_experiment,
        system_status=show_system_status,
    )
)


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


app.include_router(p0_router)


@app.post("/api/chat", response_model=ChatResponse)
def p0_chat(req: ChatRequest) -> ChatResponse:
    last_user = ""
    for m in reversed(req.messages or []):
        if m.role == "user":
            last_user = (m.content or "").strip()
            break

    today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _extract_date(text: str) -> str | None:
        import re

        m = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
        return m.group(1) if m else None

    q = last_user.lower()
    q_date = _extract_date(last_user) or today_utc

    if any(k in q for k in ("赛程", "比赛", "今天", "今日", "fixtures", "matches", "schedule")) and not any(
        k in q for k in ("预测", "prob", "概率", "胜平负")
    ):
        conn = p0_db_connect()
        try:
            fs = p0_select_fixtures_by_date(conn, q_date, q_date)
        finally:
            conn.close()
        if not fs:
            return ChatResponse(
                content=(
                    f"# 今日赛程（{q_date}）\n\n"
                    "数据库里还没有这一天的比赛数据。\n\n"
                    "你可以先导入：\n\n"
                    f"- 调用后端：`POST /api/ingest/football-data?date_from={q_date}&date_to={q_date}`\n"
                    "- 或在前端【赛程】页点击“导入”\n\n"
                    "导入成功后，再问我“今天有什么比赛？”我会给你表格列表。"
                )
            )
        lines = [f"# 今日赛程（{q_date}）", "", "| 开赛(UTC) | 联赛 | 主队 | 客队 | 状态 | 比分 |", "|---|---|---|---|---|---|"]
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

    if any(k in q for k in ("预测", "prob", "概率", "胜平负")):
        try:
            res = p0_predict(P0PredictionsRequest(date=q_date))
        except HTTPException as e:
            return ChatResponse(content=f"预测失败：{e.detail}")
        if not res.predictions:
            return ChatResponse(
                content=(
                    f"# 今日预测（{q_date}）\n\n"
                    "数据库里还没有这一天的比赛数据，先导入后再预测：\n\n"
                    f"- `POST /api/ingest/football-data?date_from={q_date}&date_to={q_date}`"
                )
            )
        conn = p0_db_connect()
        try:
            fixtures = {f["fixture_id"]: f for f in p0_select_fixtures_by_date(conn, q_date, q_date)}
        finally:
            conn.close()
        lines = [f"# 今日预测（{q_date}）", "", "| 对阵 | 主胜 | 平 | 客胜 | 置信 |", "|---|---:|---:|---:|---:|"]
        for p in res.predictions:
            fx = fixtures.get(p.fixture_id) or {}
            home = fx.get("home_team_name") or "主队"
            away = fx.get("away_team_name") or "客队"
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
        lines.append("\n## 说明\n- 预测为泊松基线；置信度来自概率分布熵（越尖锐越高）。")
        return ChatResponse(content="\n".join(lines))

    sys_prompt = (
        f"你是AI球赛预测系统的助手（今天UTC日期：{today_utc}）。"
        "你必须基于工具返回的数据回答，不要编造比赛、赔率或伤停。"
        "当用户询问赛程/比赛/预测时，你必须先调用工具（get_fixtures/predict_by_date/predict_by_fixture_ids）。"
        "如果数据库没有数据，你应该建议用户先调用 ingest_football_data 导入对应日期范围。"
        "最终输出使用 Markdown：先表格，再给出 3-5 条关键因素。"
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
                "description": "从数据库获取指定日期范围的赛程（如今天的比赛）。",
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
                "description": "对指定日期的所有比赛生成泊松基线预测（胜平负概率）。",
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
                "description": "对给定 fixture_id 列表生成泊松基线预测。",
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
                "description": "从 football-data.org 抓取指定日期范围的五大联赛比赛并入库。",
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
