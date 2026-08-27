from __future__ import annotations

import pandas as pd

from world_cup.leisu_intelligence_adapter import import_leisu_intelligence_pages
from world_cup.leisu_intelligence_adapter import parse_leisu_intelligence_html


def test_parse_leisu_intelligence_html_extracts_structured_rows():
    html = """
    <html><body>
      <section>
        <p>德国 后卫 出现伤病，本场可能缺阵。</p>
        <p>厄瓜多尔 预计调整首发阵容，加强防守反击。</p>
        <p>双方都在争取出线，战意充足。</p>
      </section>
    </body></html>
    """

    out = parse_leisu_intelligence_html(
        html,
        match_id="760468",
        home_team="Ecuador",
        away_team="Germany",
        home_team_zh="厄瓜多尔",
        away_team_zh="德国",
        url="https://www.leisu.com/guide/swot-1",
        updated_at="2026-06-26T00:00:00+00:00",
    )

    assert set(out["category"]) >= {"injury", "lineup", "motivation"}
    injury = out[out["category"].eq("injury")].iloc[0]
    assert injury["team"] == "Germany"
    assert injury["severity"] == 2.0


def test_import_leisu_intelligence_pages_from_cache(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "4460956.html").write_text(
        "<html><body><p>新西兰 有主力受伤，伊朗 赛程体能不利。</p></body></html>",
        encoding="utf-8",
    )
    features_path = tmp_path / "features.csv"
    pd.DataFrame(
        [
            {
                "match_id": "760001",
                "home_team": "Iran",
                "away_team": "New Zealand",
                "leisu_public_match_linked": 1,
                "leisu_match_id": "4460956",
                "leisu_home_team_zh": "伊朗",
                "leisu_away_team_zh": "新西兰",
                "leisu_intelligence_url": "https://www.leisu.com/guide/swot-4460956",
            }
        ]
    ).to_csv(features_path, index=False)
    output_path = tmp_path / "out.csv"

    audit = import_leisu_intelligence_pages(
        leisu_features_path=features_path,
        output_path=output_path,
        cache_dir=cache_dir,
        download=False,
    )

    out = pd.read_csv(output_path)
    assert audit["candidate_pages"] == 1
    assert audit["parsed_rows"] >= 1
    assert "injury" in set(out["category"])
