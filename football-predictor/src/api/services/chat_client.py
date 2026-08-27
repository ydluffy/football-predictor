from __future__ import annotations

import json
import os
import ssl
import time
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib import error, request

from utils.logger import get_logger

_RETRYABLE_HTTP_STATUSES = frozenset({408, 429, 500, 502, 503, 504})


class ChatErrorCode(StrEnum):
    """Stable error categories exposed by the chat transport boundary."""

    AUTHENTICATION = "llm_authentication_error"
    BAD_REQUEST = "llm_bad_request"
    RATE_LIMITED = "llm_rate_limited"
    UPSTREAM = "llm_upstream_error"
    TIMEOUT = "llm_timeout"
    NETWORK = "llm_network_error"
    INVALID_RESPONSE = "llm_invalid_response"


@dataclass(frozen=True)
class ChatClientConfig:
    timeout_seconds: float = 60.0
    max_retries: int = 2
    retry_backoff_seconds: float = 0.25

    @classmethod
    def from_env(cls) -> ChatClientConfig:
        return cls(
            timeout_seconds=_env_float("CHAT_HTTP_TIMEOUT_SECONDS", 60.0, 0.1, 300.0),
            max_retries=_env_int("CHAT_HTTP_MAX_RETRIES", 2, 0, 5),
            retry_backoff_seconds=_env_float(
                "CHAT_HTTP_RETRY_BACKOFF_SECONDS", 0.25, 0.0, 10.0
            ),
        )


@dataclass(frozen=True)
class _Provider:
    name: str
    base_url: str
    api_key: str


class _RequestFailure(Exception):
    def __init__(
        self,
        *,
        code: ChatErrorCode,
        retryable: bool,
        detail: str,
        status: int | None = None,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.retryable = retryable
        self.detail = detail
        self.status = status


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return min(maximum, max(minimum, value))


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return min(maximum, max(minimum, value))


def _chat_completions_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


def _provider_from_env() -> _Provider | None:
    coding_key = os.environ.get("CODING_PLAN_API_KEY") or os.environ.get(
        "ARK_CODING_PLAN_API_KEY"
    )
    if coding_key:
        return _Provider(
            name="coding_plan",
            base_url=os.environ.get("CODING_PLAN_BASE_URL")
            or os.environ.get("ARK_CODING_PLAN_BASE_URL")
            or "https://coding.dashscope.aliyuncs.com/v1",
            api_key=coding_key,
        )

    bailian_key = os.environ.get("BAILIAN_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")
    if bailian_key:
        return _Provider(
            name="bailian",
            base_url=os.environ.get("BAILIAN_BASE_URL")
            or os.environ.get("DASHSCOPE_BASE_URL")
            or "https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=bailian_key,
        )

    openrouter_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get(
        "OPEN_ROUTER_API_KEY"
    )
    if openrouter_key:
        return _Provider(
            name="openrouter",
            base_url=os.environ.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1",
            api_key=openrouter_key,
        )

    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        return _Provider(
            name="openai",
            base_url=os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1",
            api_key=openai_key,
        )
    return None


def _http_error_code(status: int) -> ChatErrorCode:
    if status in {401, 403}:
        return ChatErrorCode.AUTHENTICATION
    if status in {400, 404, 405, 409, 415, 422}:
        return ChatErrorCode.BAD_REQUEST
    if status == 429:
        return ChatErrorCode.RATE_LIMITED
    return ChatErrorCode.UPSTREAM


def _format_error(
    *,
    code: ChatErrorCode,
    provider: str,
    request_id: str,
    retryable: bool,
    detail: str,
    status: int | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    safe_detail = " ".join(detail.split())[:500]
    status_text = str(status) if status is not None else "none"
    return (
        "[error] "
        f"code={code.value} provider={provider} status={status_text} "
        f"retryable={str(retryable).lower()} request_id={request_id} detail={safe_detail}",
        [],
    )


def _decode_response(raw_response: bytes) -> tuple[str, list[dict[str, Any]]]:
    payload: Any = json.loads(raw_response.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("response payload is not an object")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError("response has no valid choices")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ValueError("response choice has no valid message")

    content_value = message.get("content")
    content = "" if content_value is None else str(content_value)
    raw_tool_calls = message.get("tool_calls")
    if not isinstance(raw_tool_calls, list):
        return content, []
    tool_calls = [dict(item) for item in raw_tool_calls if isinstance(item, dict)]
    return content, tool_calls


def _send_request(
    req: request.Request,
    *,
    timeout_seconds: float,
) -> tuple[str, list[dict[str, Any]]]:
    try:
        response_context: Any = request.urlopen(  # noqa: S310 - operator-configured endpoint
            req,
            timeout=timeout_seconds,
            context=ssl.create_default_context(),
        )
        with response_context as response:
            return _decode_response(response.read())
    except error.HTTPError as exc:
        status = int(exc.code)
        raise _RequestFailure(
            code=_http_error_code(status),
            retryable=status in _RETRYABLE_HTTP_STATUSES,
            detail=exc.read().decode("utf-8", errors="ignore"),
            status=status,
        ) from exc
    except TimeoutError as exc:
        raise _RequestFailure(
            code=ChatErrorCode.TIMEOUT,
            retryable=True,
            detail=str(exc),
        ) from exc
    except error.URLError as exc:
        raise _RequestFailure(
            code=ChatErrorCode.NETWORK,
            retryable=True,
            detail=str(exc.reason),
        ) from exc
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError, KeyError) as exc:
        raise _RequestFailure(
            code=ChatErrorCode.INVALID_RESPONSE,
            retryable=False,
            detail=str(exc),
        ) from exc


def _retry(
    *,
    logger: Any,
    code: ChatErrorCode,
    attempt: int,
    config: ChatClientConfig,
    status: int | None = None,
) -> bool:
    if attempt >= config.max_retries:
        return False
    delay_seconds = config.retry_backoff_seconds * (2**attempt)
    logger.warning(
        "chat_request_retry",
        error_code=code.value,
        status=status,
        attempt=attempt + 1,
        next_attempt=attempt + 2,
        delay_seconds=delay_seconds,
    )
    if delay_seconds:
        time.sleep(delay_seconds)
    return True


def call_openai_chat(
    messages: list[dict[str, object]],
    model: str,
    tools: list[dict[str, object]] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Call an OpenAI-compatible chat endpoint with bounded retries."""

    provider = _provider_from_env()
    if provider is None:
        last_user_message = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                last_user_message = str(message.get("content") or "")
                break
        return f"[mock] 我已收到你的问题：{last_user_message[:120]} ...", []

    config = ChatClientConfig.from_env()
    request_id = uuid.uuid4().hex
    logger = get_logger().bind(
        component="chat_client",
        provider=provider.name,
        model=model,
        request_id=request_id,
    )
    logger.info(
        "chat_request_started",
        timeout_seconds=config.timeout_seconds,
        max_retries=config.max_retries,
    )

    endpoint = _chat_completions_url(provider.base_url)
    payload: dict[str, object] = {"model": model, "messages": messages}
    if tools:
        payload["tools"] = tools

    req = request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {provider.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    for attempt in range(config.max_retries + 1):
        try:
            result = _send_request(req, timeout_seconds=config.timeout_seconds)
            logger.info("chat_request_succeeded", attempt=attempt + 1)
            return result
        except _RequestFailure as failure:
            if failure.retryable and _retry(
                logger=logger,
                code=failure.code,
                attempt=attempt,
                config=config,
                status=failure.status,
            ):
                continue
            logger.error(
                "chat_request_failed",
                error_code=failure.code.value,
                status=failure.status,
                retryable=failure.retryable,
                attempts=attempt + 1,
            )
            return _format_error(
                code=failure.code,
                provider=provider.name,
                request_id=request_id,
                retryable=failure.retryable,
                detail=failure.detail,
                status=failure.status,
            )

    raise RuntimeError("chat retry loop terminated unexpectedly")
