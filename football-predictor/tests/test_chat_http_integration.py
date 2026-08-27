from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from fastapi.testclient import TestClient

from api import main as api_main
from api.routes import chat as chat_routes
from api.services import chat_client
from api.services.chat_client import ChatClientConfig, call_openai_chat


def _clear_chat_credentials(monkeypatch: Any) -> None:
    for name in (
        "CODING_PLAN_API_KEY",
        "ARK_CODING_PLAN_API_KEY",
        "BAILIAN_API_KEY",
        "DASHSCOPE_API_KEY",
        "OPENROUTER_API_KEY",
        "OPEN_ROUTER_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def test_chat_route_over_http(monkeypatch: Any) -> None:
    monkeypatch.setattr(chat_routes, "_call_openai_chat", lambda messages, model, tools: ("ok", []))

    with TestClient(api_main.app) as client:
        response = client.post(
            "/chat",
            json={"messages": [{"role": "user", "content": "hello"}], "model": "test-model"},
        )

    assert response.status_code == 200
    assert response.json() == {"content": "ok"}
    assert response.headers["X-Request-ID"]
    assert float(response.headers["X-Response-Time-Ms"]) >= 0.0


def test_health_exposes_runtime_versions_and_request_metrics() -> None:
    with TestClient(api_main.app) as client:
        health = client.get("/health")
        metrics = client.get("/metrics")

    assert health.status_code == 200
    payload = health.json()
    assert payload["service"]["name"] == "football-predictor"
    assert {"model_loaded", "model_version", "data_snapshot_version"} <= payload.keys()
    assert {"requests_total", "server_error_rate", "latency_ms"} <= payload["requests"].keys()
    assert metrics.status_code == 200
    assert metrics.json()["requests_total"] >= 1


def test_chat_client_config_validates_environment(monkeypatch: Any) -> None:
    monkeypatch.setenv("CHAT_HTTP_TIMEOUT_SECONDS", "999")
    monkeypatch.setenv("CHAT_HTTP_MAX_RETRIES", "invalid")
    monkeypatch.setenv("CHAT_HTTP_RETRY_BACKOFF_SECONDS", "-1")

    config = ChatClientConfig.from_env()

    assert config.timeout_seconds == 300.0
    assert config.max_retries == 2
    assert config.retry_backoff_seconds == 0.0


def test_chat_client_classifies_timeout_after_bounded_attempts(monkeypatch: Any) -> None:
    _clear_chat_credentials(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("CHAT_HTTP_MAX_RETRIES", "1")
    monkeypatch.setenv("CHAT_HTTP_RETRY_BACKOFF_SECONDS", "0")
    attempts = 0

    def raise_timeout(*args: object, **kwargs: object) -> None:
        nonlocal attempts
        attempts += 1
        raise TimeoutError("upstream timed out")

    monkeypatch.setattr(chat_client.request, "urlopen", raise_timeout)

    content, tool_calls = call_openai_chat(
        [{"role": "user", "content": "hello"}],
        "test-model",
    )

    assert "code=llm_timeout" in content
    assert "retryable=true" in content
    assert tool_calls == []
    assert attempts == 2


def test_chat_client_calls_compatible_http_endpoint_and_retries(monkeypatch: Any) -> None:
    received: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            content_length = int(self.headers.get("Content-Length", "0"))
            received.append(
                {
                    "path": self.path,
                    "authorization": self.headers.get("Authorization"),
                    "body": json.loads(self.rfile.read(content_length)),
                }
            )
            if len(received) == 1:
                self.send_response(503)
                self.end_headers()
                self.wfile.write(b"temporarily unavailable")
                return

            body = json.dumps(
                {"choices": [{"message": {"content": "completed", "tool_calls": []}}]}
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        _clear_chat_credentials(monkeypatch)
        monkeypatch.setenv("OPENAI_API_KEY", "integration-test-key")
        monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{server.server_port}")
        monkeypatch.setenv("CHAT_HTTP_TIMEOUT_SECONDS", "2.5")
        monkeypatch.setenv("CHAT_HTTP_MAX_RETRIES", "1")
        monkeypatch.setenv("CHAT_HTTP_RETRY_BACKOFF_SECONDS", "0")

        content, tool_calls = call_openai_chat(
            [{"role": "user", "content": "hello"}],
            "integration-model",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert content == "completed"
    assert tool_calls == []
    assert len(received) == 2
    assert received[-1]["path"] == "/v1/chat/completions"
    assert received[-1]["authorization"] == "Bearer integration-test-key"
    assert received[-1]["body"]["model"] == "integration-model"


def test_chat_client_classifies_non_retryable_http_error(monkeypatch: Any) -> None:
    calls = 0

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            nonlocal calls
            calls += 1
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"invalid token")

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        _clear_chat_credentials(monkeypatch)
        monkeypatch.setenv("OPENAI_API_KEY", "bad-key")
        monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{server.server_port}")
        monkeypatch.setenv("CHAT_HTTP_MAX_RETRIES", "3")

        content, tool_calls = call_openai_chat(
            [{"role": "user", "content": "hello"}],
            "integration-model",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert "code=llm_authentication_error" in content
    assert "status=401" in content
    assert "retryable=false" in content
    assert tool_calls == []
    assert calls == 1
