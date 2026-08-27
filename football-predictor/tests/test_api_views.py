from __future__ import annotations

from pathlib import Path

from api import main as api_main
from api.views import CHAT_UI_HTML, SPORTTTERY_EDITOR_HTML


def test_sporttery_editor_view_preserves_dom_and_api_contract() -> None:
    response = api_main.world_cup_sporttery_editor()
    html = response.body.decode("utf-8")

    assert response.media_type == "text/html"
    assert html == SPORTTTERY_EDITOR_HTML
    for marker in (
        "体彩让球盘编辑器",
        'id="pasteBox"',
        'id="applyPaste"',
        "/world-cup/sporttery/handicap-markets",
        "/world-cup/sporttery/parse-paste",
    ):
        assert marker in html


def test_chat_view_preserves_dom_and_api_contract() -> None:
    response = api_main.chat_ui()
    html = response.body.decode("utf-8")

    assert response.media_type == "text/html"
    assert html == CHAT_UI_HTML
    for marker in (
        "足球预测研究员 Copilot",
        'id="chat"',
        'id="input"',
        'id="send"',
        "marked/marked.min.js",
        "fetch('/chat'",
    ):
        assert marker in html


def test_api_main_does_not_regain_inline_html_pages() -> None:
    source = Path(api_main.__file__).read_text(encoding="utf-8")

    assert "<!doctype html>" not in source.lower()
    assert len(source.splitlines()) < 1350
