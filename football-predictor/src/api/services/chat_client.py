from __future__ import annotations

import json
import os
import ssl
from urllib import error, request


def _chat_completions_url(base: str) -> str:
    normalized = str(base).rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return normalized + "/chat/completions"
    return normalized + "/v1/chat/completions"


def call_openai_chat(
    messages: list[dict[str, object]],
    model: str,
    tools: list[dict[str, object]] | None = None,
) -> tuple[str, list[dict]]:
    coding_key = os.getenv("CODING_PLAN_API_KEY")
    coding_base = (
        os.getenv("CODING_PLAN_BASE_URL")
        or "https://coding.dashscope.aliyuncs.com/v1"
    )
    bailian_key = os.getenv("BAILIAN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY") or os.getenv(
        "OPEN_ROUTER_API_KEY"
    )
    openai_key = os.getenv("OPENAI_API_KEY")
    if coding_key:
        base_url = _chat_completions_url(coding_base)
        token = coding_key
    elif bailian_key:
        base_url = _chat_completions_url(
            os.getenv("BAILIAN_BASE_URL")
            or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        token = bailian_key
    elif openrouter_key:
        base_url = _chat_completions_url(
            os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1"
        )
        token = openrouter_key
    elif openai_key:
        base_url = _chat_completions_url(
            os.getenv("OPENAI_BASE_URL") or "https://api.openai.com"
        )
        token = openai_key
    else:
        last_user_message = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                last_user_message = str(message.get("content") or "")
                break
        return f"[mock] 我已收到你的问题：{last_user_message[:120]} ...", []

    payload: dict[str, object] = {"model": model, "messages": messages}
    if tools:
        payload["tools"] = tools

    body = json.dumps(payload).encode("utf-8")
    http_request = request.Request(str(base_url), data=body)
    http_request.add_header("Content-Type", "application/json")
    http_request.add_header("Authorization", f"Bearer {token}")
    context = ssl.create_default_context()
    try:
        with request.urlopen(http_request, context=context, timeout=60) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        raw = (
            exc.read().decode("utf-8", errors="replace")
            if hasattr(exc, "read")
            else str(exc)
        )
        return (
            f"[error] llm_http_error status={getattr(exc, 'code', None)} "
            f"body={raw[:800]}",
            [],
        )
    except Exception as exc:
        return f"[error] llm_request_failed {type(exc).__name__}: {exc}", []

    message = response_payload.get("choices", [{}])[0].get("message", {})
    content = message.get("content") or ""
    tool_calls = message.get("tool_calls", [])
    return str(content), tool_calls
