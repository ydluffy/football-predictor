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
    html = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>足球预测研究员 Copilot</title>
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
    <span>⚽</span> 足球预测研究员 Copilot
  </header>
  <div id="chat-container">
    <div id="chat">
        <div class="msg assistant">
            <div class="bubble">你好！我是你的 AI 足球预测助手 🤖。我可以帮你获取今日赛程、运行预测模型、分析回测数据。想了解点什么？</div>
        </div>
    </div>
    <div id="box">
      <textarea id="input" placeholder="输入你的问题，如：帮我查一下今天有什么比赛，并跑一下预测推荐..."></textarea>
      <button id="send">发送 🚀</button>
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
        
        const content = j.content || '⚠️ [error] 无内容';
        addMessage('assistant', content);
        hist.push({role:'assistant', content});
      } catch(e) {
        removeLoading();
        addMessage('assistant', '❌ [error] ' + e);
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
    # upgrade_report 在具体 run_dir 下，优先从 latest_execution_summary 的 run_dir 推断
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
    # 简单偏置判定：单类预测占比 > 0.7 或 avg_p 某一类 > 0.6
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
            suggestions.append("考虑引入校准（sigmoid）并比较 reliability gap")
        if float(metrics.get("logloss", 0.0)) > 1.0:
            suggestions.append("尝试更强模型（lightgbm）或升级到 v2/v3 特征")
    if "bias_flags" in dist and dist["bias_flags"]:
        suggestions.append("检测类别不平衡或赔率分布异常，检查联赛/赛季混合与标签质量")
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
        reasons.append("类别或概率分布偏置（bias_flags 命中）")
    reasons.append("特征不足：当前 v1 仅赔率，建议采用 v2 加入 xg/injury/line_move")
    reasons.append("模型表达能力：logit 可能不足，可试 lightgbm 或 stacking")
    if metrics and float(metrics.get("brier", 0.0)) > 0.5:
        reasons.append("未校准：尝试 sigmoid 校准并观察 reliability_table")
    if "actual_label_counts" in dist:
        alc = dist["actual_label_counts"]
        total = sum(alc.values()) or 1
        if max(alc.values()) / total > 0.6:
            reasons.append("类别不平衡：实际标签分布倾斜，建议在切分/采样上做约束")
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
    if "real" in t or "真实" in t or "今天" in t or "今日" in t or "live" in t:
        dm = "real"
    return {"model_type": mt, "feature_version": fv, "calibration": cal, "data_mode": dm}


def run_experiment(command_text: str) -> dict[str, object]:
    cfg = _parse_run_experiment(command_text)
    director = ResearchDirector()
    wf = "candidate_model_upgrade" if ("upgrade" in command_text.lower() or "晋升" in command_text) else "daily_prediction"
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
        f"- 样本量(n_samples): {a.get('n_samples')}",
        f"- brier: {_fmt_float(a.get('brier'))}",
        f"- logloss: {_fmt_float(a.get('logloss'))}",
        f"- 概率均值(avg_p): H={_fmt_float(avg_p.get('home'))}, D={_fmt_float(avg_p.get('draw'))}, A={_fmt_float(avg_p.get('away'))}",
        f"- 偏置(bias_flags): {', '.join(str(x) for x in bias) if bias else '无明显偏置'}",
        f"- 产物: {s.eval_metrics_path} | {s.eval_results_path} | {s.eval_reliability_table_path}",
    ]
    if bt.get("summary"):
        sm = bt["summary"]  # type: ignore[assignment]
        lines.append(
            f"- 回测: n_bets={sm.get('n_bets')} profit={_fmt_float(sm.get('profit'))} roi={_fmt_float(sm.get('roi'))} max_dd={_fmt_float(sm.get('max_drawdown'))} final={_fmt_float(sm.get('final_bankroll'))}"
        )
        lines.append(f"- 回测产物: {bt['paths']['summary_path']} | {bt['paths']['bets_path']}")
    if suggestions:
        lines.append("- 建议: " + "；".join(str(x) for x in suggestions))
    return "\n".join(lines)


def _format_high_brier_message() -> str:
    s = _get_settings()
    x = explain_high_brier()
    rs = x.get("reasons") if isinstance(x.get("reasons"), list) else []
    return "\n".join(
        [
            f"- brier: {_fmt_float(x.get('brier'))}",
            f"- 产物: {s.eval_metrics_path} | {s.eval_results_path} | {s.eval_reliability_table_path}",
            "- 可能原因:",
        ]
        + [f"  - {r}" for r in rs]
    )


def _format_backtest_message() -> str:
    bt = _read_backtest_status()
    sm = bt.get("summary")
    if not sm:
        return "\n".join(
            [
                "- 未找到回测产物 summary.json",
                f"- 期望路径: {bt['paths']['summary_path']}",
                "- 先运行: python scripts/run_backtest.py --pred-path artifacts/eval/results.csv --data-path data/processed/real_matches_standardized.csv --out-dir artifacts/backtest",
            ]
        )
    top = bt.get("by_league_top")
    lines = [
        f"- 回测: n_bets={sm.get('n_bets')} profit={_fmt_float(sm.get('profit'))} roi={_fmt_float(sm.get('roi'))} hit_rate={_fmt_float(sm.get('hit_rate'))} max_dd={_fmt_float(sm.get('max_drawdown'))} final={_fmt_float(sm.get('final_bankroll'))}",
        f"- 产物: {bt['paths']['summary_path']} | {bt['paths']['bets_path']} | {bt['paths']['by_league_path']} | {bt['paths']['equity_curve_path']}",
    ]
    if isinstance(top, list) and top:
        lines.append("- 联赛Top(按 n_bets): " + "; ".join(f"{r.get('league')} n={r.get('n_bets')} roi={_fmt_float(r.get('roi'))}" for r in top))
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
        
        if df.empty:
            return f"今天 ({today}) 没有获取到任何赛程数据。"
        
        lines = [f"**今日 ({today}) 实时赛程及高级特征**：", f"共获取到 {len(df)} 场比赛。"]
        
        for _, row in df.iterrows():
            match_str = f"- {row['league']}: {row['home_team']} vs {row['away_team']} ({row['date']})"
            stats_str = f"  - 赔率: 主胜 {row['odds_home']}, 平 {row['odds_draw']}, 客胜 {row['odds_away']}"
            adv_stats_str = f"  - 高级特征: xG主 {row['xg_home']} / xG客 {row['xg_away']}, 赔率变动 {row['line_move']}, 伤停标记 {row['injury_flag']}"
            lines.extend([match_str, stats_str, adv_stats_str])
            
        out_path = client.save_schedule(df, today)
        lines.append(f"\n*数据已保存至*: `{out_path}`")
        lines.append("*提示*: 你可以回复“用这些数据跑预测”来运行 `daily_prediction` 工作流进行今日推单！")
        return "\n".join(lines)
    except Exception as e:
        return f"[error] 获取今日赛程失败: {e}"

def _try_handle_natural_language(text: str) -> str | None:
    t = text.strip().lower()
    if not t:
        return None

    if any(k in t for k in ("今天", "今日", "球赛", "赛程", "比赛", "live", "实时")) and not any(k in t for k in ("跑", "训练", "预测", "评估")):
        return _format_today_matches_message()

    if any(k in t for k in ("总结", "概览", "分析", "最新结果", "表现", "指标", "metrics", "logloss", "brier")):
        if any(k in t for k in ("为什么", "原因", "高", "解释")) and ("brier" in t or "logloss" in t or "概率" in t):
            return _format_high_brier_message()
        return _format_latest_analysis_message()

    if any(k in t for k in ("回测", "roi", "收益", "亏", "回撤", "下注", "bets")):
        return _format_backtest_message()

    if any(k in t for k in ("跑", "试验", "实验", "对比", "训练", "预测", "upgrade", "晋升", "推单")) and any(
        k in t for k in ("logit", "lightgbm", "lgbm", "stacking", "v1", "v2", "v3", "sigmoid", "isotonic", "real", "真实", "今天", "今日", "这些")
    ):
        out = run_experiment(text)
        return _json.dumps(out, ensure_ascii=False, indent=2)

    if any(k in t for k in ("状态", "系统状态", "production", "registry", "模型注册", "当前模型")):
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
    factors.append(f"主队近{home_avg.matches or 0}场：场均进球{home_avg.goals_for:.2f}，场均失球{home_avg.goals_against:.2f}")
    factors.append(f"客队近{away_avg.matches or 0}场：场均进球{away_avg.goals_for:.2f}，场均失球{away_avg.goals_against:.2f}")
    factors.append(f"泊松期望进球：主{lam_h:.2f} vs 客{lam_a:.2f}")
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
