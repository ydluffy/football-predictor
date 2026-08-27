from __future__ import annotations

from world_cup.public_absence_text_parser import parse_team_news_text
from world_cup.public_page_text import html_to_visible_text
from world_cup.public_page_text import read_html_or_text


def test_html_to_visible_text_removes_scripts_and_keeps_article_text():
    html = """
    <html><head><title>Team News</title><script>bad()</script></head>
    <body><article>
      <h1>Germany vs Argentina</h1>
      <p>Germany: Player A (hamstring injury)</p>
      <p>Argentina: Player B (suspended after red card)</p>
    </article></body></html>
    """

    text = html_to_visible_text(html)

    assert "bad()" not in text
    assert "Team News" in text
    assert "Germany: Player A" in text
    assert "Argentina: Player B" in text


def test_cached_html_text_can_feed_absence_parser(tmp_path):
    path = tmp_path / "team_news.html"
    path.write_text(
        """
        <html><body><article>
        <p>Germany: Player A (hamstring injury); Player C (late fitness test)</p>
        </article></body></html>
        """,
        encoding="utf-8",
    )

    _, text = read_html_or_text(path)
    rows = parse_team_news_text(
        text,
        date="2026-06-27",
        source="sports_mole",
    )

    assert len(rows) == 2
    assert set(rows["status"]) == {"injured", "doubtful"}
