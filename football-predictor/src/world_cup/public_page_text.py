from __future__ import annotations

import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import requests

try:  # pragma: no cover - exercised only when optional dependency exists.
    from bs4 import BeautifulSoup
except ModuleNotFoundError:  # pragma: no cover - covered through fallback parser tests.
    BeautifulSoup = None


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)


def html_to_visible_text(html: str, *, title_prefix: bool = True) -> str:
    if BeautifulSoup is None:
        return _html_to_visible_text_stdlib(html, title_prefix=title_prefix)
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "form"]):
        tag.decompose()
    pieces: list[str] = []
    if title_prefix and soup.title and soup.title.get_text(strip=True):
        pieces.append(soup.title.get_text(" ", strip=True))
    main = soup.find("main") or soup.find("article") or soup.body or soup
    for element in main.find_all(["h1", "h2", "h3", "p", "li", "td", "th", "figcaption"]):
        text = re.sub(r"\s+", " ", element.get_text(" ", strip=True))
        if text and text not in pieces:
            pieces.append(text)
    if not pieces:
        raw = re.sub(r"\s+", " ", main.get_text(" ", strip=True))
        if raw:
            pieces.append(raw)
    return "\n".join(pieces).strip() + ("\n" if pieces else "")


class _VisibleTextParser(HTMLParser):
    def __init__(self, *, title_prefix: bool = True) -> None:
        super().__init__(convert_charrefs=True)
        self.title_prefix = title_prefix
        self.skip_depth = 0
        self.current_tag = ""
        self.title: list[str] = []
        self.pieces: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.current_tag = tag
        if tag in {"script", "style", "noscript", "svg", "iframe", "form"}:
            self.skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg", "iframe", "form"} and self.skip_depth:
            self.skip_depth -= 1
        self.current_tag = ""

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if not text:
            return
        if self.current_tag == "title":
            self.title.append(text)
        elif self.current_tag in {"h1", "h2", "h3", "p", "li", "td", "th", "figcaption"}:
            self.pieces.append(text)


def _html_to_visible_text_stdlib(html: str, *, title_prefix: bool = True) -> str:
    parser = _VisibleTextParser(title_prefix=title_prefix)
    parser.feed(html)
    pieces: list[str] = []
    if title_prefix and parser.title:
        pieces.append(" ".join(parser.title))
    for piece in parser.pieces:
        if piece not in pieces:
            pieces.append(piece)
    if not pieces:
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            pieces.append(text)
    return "\n".join(pieces).strip() + ("\n" if pieces else "")


def read_html_or_text(path: str | Path) -> tuple[str, str]:
    file_path = Path(path)
    content = file_path.read_text(encoding="utf-8")
    suffix = file_path.suffix.casefold()
    if suffix in {".html", ".htm"} or "<html" in content[:500].casefold():
        return content, html_to_visible_text(content)
    return content, content


def fetch_public_page(
    url: str,
    *,
    timeout: int = 45,
    user_agent: str = DEFAULT_USER_AGENT,
) -> tuple[str, dict[str, Any]]:
    response = requests.get(
        url,
        headers={"User-Agent": user_agent, "Accept-Language": "en-US,en;q=0.9"},
        timeout=timeout,
    )
    audit = {
        "url": url,
        "status_code": int(response.status_code),
        "content_type": response.headers.get("content-type", ""),
        "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    response.raise_for_status()
    response.encoding = response.encoding or "utf-8"
    return response.text, audit


def extract_public_page_text(
    *,
    input_path: str | Path | None = None,
    url: str = "",
    html_output: str | Path | None = None,
    text_output: str | Path,
    timeout: int = 45,
) -> dict[str, Any]:
    if not input_path and not url:
        raise ValueError("input_path or url is required")
    if input_path and url:
        raise ValueError("pass only one of input_path or url")
    if url:
        html, audit = fetch_public_page(url, timeout=timeout)
        source = url
    else:
        html, text = read_html_or_text(Path(input_path or ""))
        audit = {
            "url": "",
            "status_code": None,
            "content_type": "local_file",
            "fetched_at": "",
        }
        source = str(input_path)
        output_path = Path(text_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
        return {
            "source": source,
            "mode": "local",
            "text_output": str(output_path),
            "text_chars": len(text),
            **audit,
        }
    text = html_to_visible_text(html)
    if html_output:
        html_path = Path(html_output)
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(html, encoding="utf-8")
    output_path = Path(text_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    return {
        "source": source,
        "mode": "url",
        "html_output": str(html_output or ""),
        "text_output": str(output_path),
        "text_chars": len(text),
        **audit,
    }
