from __future__ import annotations

from typing import Any


_RETRYABLE_ERROR_TYPES = {
    "file_unreadable",
    "temporary_missing_data",
    "provider_unavailable",
    "FileNotFoundError",
    "PermissionError",
    "TimeoutError",
    "ConnectionError",
}

_NON_RETRYABLE_ERROR_TYPES = {
    "missing_required_fields",
    "pytest_failed",
    "gate_blocked",
}


def should_retry(error_type: str) -> bool:
    t = str(error_type or "").strip()
    if not t:
        return False
    if t in _NON_RETRYABLE_ERROR_TYPES:
        return False
    if t in _RETRYABLE_ERROR_TYPES:
        return True
    return False


def get_retry_delay(attempt: int) -> int:
    a = int(attempt)
    if a <= 1:
        return 1
    delay = 2 ** (a - 1)
    if delay > 30:
        delay = 30
    return int(delay)


def classify_exception(exc: BaseException) -> str:
    name = type(exc).__name__
    msg = str(exc)

    if isinstance(exc, (FileNotFoundError, PermissionError)):
        return "file_unreadable"

    if isinstance(exc, TimeoutError):
        return "provider_unavailable"

    if isinstance(exc, ConnectionError):
        return "provider_unavailable"

    if name == "OSError":
        return "file_unreadable"

    if name == "ValueError":
        lowered = msg.lower()
        if "缺少字段" in msg or "缺少必需字段" in msg or "存在非法取值" in msg:
            return "missing_required_fields"
        if "空数据" in msg or "no such file" in lowered or "not found" in lowered:
            return "temporary_missing_data"

    if name == "RuntimeError":
        lowered = msg.lower()
        if "pytest" in lowered:
            return "pytest_failed"
        if "blocked" in lowered or "gate" in lowered:
            return "gate_blocked"
        if "provider" in lowered or "temporary" in lowered or "temporarily" in lowered:
            return "provider_unavailable"
        return "provider_unavailable"

    return name


def jsonable_error(exc: BaseException) -> dict[str, Any]:
    return {"type": type(exc).__name__, "message": str(exc)}
