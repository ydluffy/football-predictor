from __future__ import annotations

from api import main as api_main
from api.routes import chat as chat_routes
from api.services.chat_client import _chat_completions_url, call_openai_chat


def test_chat_client_uses_mock_response_without_credentials(monkeypatch) -> None:
    for name in (
        "CODING_PLAN_API_KEY",
        "BAILIAN_API_KEY",
        "DASHSCOPE_API_KEY",
        "OPENROUTER_API_KEY",
        "OPEN_ROUTER_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    content, tool_calls = call_openai_chat(
        [{"role": "user", "content": "分析今天的比赛"}],
        "test-model",
    )

    assert content == "[mock] 我已收到你的问题：分析今天的比赛 ..."
    assert tool_calls == []


def test_chat_client_normalizes_compatible_api_urls() -> None:
    assert _chat_completions_url("https://example.com") == (
        "https://example.com/v1/chat/completions"
    )
    assert _chat_completions_url("https://example.com/v1/") == (
        "https://example.com/v1/chat/completions"
    )
    assert _chat_completions_url("https://example.com/chat/completions") == (
        "https://example.com/chat/completions"
    )


def test_chat_route_uses_requested_model_and_system_prompt(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_call(messages, model, tools=None):
        captured.update(messages=messages, model=model, tools=tools)
        return "completed", []

    monkeypatch.setattr(chat_routes, "_call_openai_chat", fake_call)

    response = chat_routes.chat(
        chat_routes.ChatRequest(
            messages=[chat_routes.ChatMessage(role="user", content="hello")],
            model="explicit-model",
        )
    )

    assert response.content == "completed"
    assert captured["model"] == "explicit-model"
    assert captured["messages"][0]["role"] == "system"
    assert captured["messages"][-1] == {"role": "user", "content": "hello"}
    assert captured["tools"]


def test_chat2_command_delegates_to_copilot_service(monkeypatch) -> None:
    monkeypatch.setattr(
        chat_routes,
        "show_system_status",
        lambda: {"production_model": {"model_id": "model-9"}},
    )

    response = chat_routes.chat2(
        chat_routes.ChatRequest(
            messages=[chat_routes.ChatMessage(role="user", content="/status")]
        )
    )

    assert '"model_id": "model-9"' in response.content


def test_chat_routes_are_registered_once_and_main_exports_are_compatible() -> None:
    paths = [route.path for route in api_main.app.routes]

    for path in ("/chat", "/chat2", "/chat-ui", "/api/chat"):
        assert paths.count(path) == 1
    assert api_main.ChatRequest is chat_routes.ChatRequest
    assert api_main.chat is chat_routes.chat
    assert api_main.p0_chat is chat_routes.p0_chat
