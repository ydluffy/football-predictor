from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from collections.abc import Callable
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from utils.logger import get_logger

_REQUEST_ID: ContextVar[str | None] = ContextVar("request_id", default=None)
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def get_request_id() -> str | None:
    return _REQUEST_ID.get()


class RequestMetricsRegistry:
    """Process-local request counters for health and diagnostics endpoints."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._started_at = datetime.now(UTC)
        self._started_monotonic = clock()
        self._lock = threading.Lock()
        self._requests = 0
        self._responses = 0
        self._in_flight = 0
        self._client_errors = 0
        self._server_errors = 0
        self._duration_total_ms = 0.0
        self._duration_max_ms = 0.0

    def request_started(self) -> None:
        with self._lock:
            self._requests += 1
            self._in_flight += 1

    def request_finished(self, status_code: int, duration_ms: float) -> None:
        with self._lock:
            self._responses += 1
            self._in_flight = max(0, self._in_flight - 1)
            if 400 <= status_code < 500:
                self._client_errors += 1
            elif status_code >= 500:
                self._server_errors += 1
            self._duration_total_ms += duration_ms
            self._duration_max_ms = max(self._duration_max_ms, duration_ms)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            responses = self._responses
            errors = self._client_errors + self._server_errors
            average = self._duration_total_ms / responses if responses else 0.0
            return {
                "started_at_utc": self._started_at.isoformat(),
                "uptime_seconds": round(max(0.0, self._clock() - self._started_monotonic), 3),
                "requests_total": self._requests,
                "responses_total": responses,
                "in_flight": self._in_flight,
                "client_errors_total": self._client_errors,
                "server_errors_total": self._server_errors,
                "error_rate": round(errors / responses, 6) if responses else 0.0,
                "server_error_rate": round(self._server_errors / responses, 6) if responses else 0.0,
                "latency_ms": {
                    "average": round(average, 3),
                    "maximum": round(self._duration_max_ms, 3),
                },
            }


def _request_id(scope: Scope) -> str:
    for key, value in scope.get("headers", []):
        if key.lower() != b"x-request-id":
            continue
        candidate = value.decode("latin-1").strip()
        if _SAFE_REQUEST_ID.fullmatch(candidate):
            return candidate
    return uuid.uuid4().hex


class ObservabilityMiddleware:
    def __init__(self, app: ASGIApp, *, registry: RequestMetricsRegistry) -> None:
        self.app = app
        self.registry = registry

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _request_id(scope)
        token = _REQUEST_ID.set(request_id)
        started = time.perf_counter()
        status_code = 500
        response_started = False
        self.registry.request_started()

        async def send_with_headers(message: Message) -> None:
            nonlocal response_started, status_code
            if message["type"] == "http.response.start":
                response_started = True
                status_code = int(message["status"])
                duration_ms = (time.perf_counter() - started) * 1000.0
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                headers["X-Response-Time-Ms"] = f"{duration_ms:.3f}"
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        except Exception:
            get_logger().exception(
                "api_request_unhandled_error",
                request_id=request_id,
                method=scope.get("method"),
                path=scope.get("path"),
            )
            if response_started:
                raise
            response = JSONResponse(
                {"detail": "internal server error", "request_id": request_id},
                status_code=500,
            )
            await response(scope, receive, send_with_headers)
        finally:
            duration_ms = (time.perf_counter() - started) * 1000.0
            self.registry.request_finished(status_code, duration_ms)
            get_logger().bind(
                request_id=request_id,
                method=scope.get("method"),
                path=scope.get("path"),
                status_code=status_code,
                duration_ms=round(duration_ms, 3),
            ).info("api_request_completed")
            _REQUEST_ID.reset(token)


def _safe_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def model_runtime_metadata(model_path: Path | None) -> dict[str, object]:
    if model_path is None:
        return {"loaded": False, "path": None, "version": None, "manifest_status": "missing"}
    manifest_path = model_path.with_suffix(".manifest.json")
    manifest = _safe_json(manifest_path)
    configured_version = os.getenv("MODEL_VERSION")
    digest = str(manifest.get("artifact_sha256") or "")
    version = configured_version or (digest[:12] if digest else None)
    return {
        "loaded": True,
        "path": str(model_path),
        "version": version,
        "model_type": manifest.get("model_type"),
        "feature_version": manifest.get("feature_version"),
        "created_at": manifest.get("created_at"),
        "artifact_sha256": digest or None,
        "manifest_status": "available" if manifest else "missing",
    }


def data_runtime_metadata(quality_report_path: Path) -> dict[str, object]:
    report = _safe_json(quality_report_path)
    configured_version = os.getenv("DATA_SNAPSHOT_VERSION")
    snapshot_version = configured_version or report.get("as_of_utc")
    return {
        "snapshot_version": snapshot_version,
        "quality_status": report.get("status") if report else "unknown",
        "quality_report_path": str(quality_report_path),
        "quality_report_available": bool(report),
        "quality_report_generated_at": report.get("generated_at_utc"),
    }
