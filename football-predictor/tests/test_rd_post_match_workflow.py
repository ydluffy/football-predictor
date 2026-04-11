from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from config.settings import get_settings
from research_director.director import ResearchDirector


def test_post_match_learning_workflow_writes_report_and_suggestions(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    s = get_settings()

    s.data_processed_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        {
            "match_id": ["m1", "m2", "m3", "m4", "m5"],
            "date": ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04", "2025-01-05"],
            "league": ["EPL", "EPL", "EPL", "LaLiga", "LaLiga"],
            "odds_home": [2.1, 1.9, 2.5, 2.0, 1.8],
            "odds_draw": [3.2, 3.4, 3.1, 3.3, 3.2],
            "odds_away": [3.5, 4.2, 2.9, 3.6, 4.1],
            "actual_result": ["H", "D", "A", "H", "A"],
        }
    )
    (s.data_processed_dir / "real_matches_standardized.csv").write_text(df.to_csv(index=False), encoding="utf-8")

    director = ResearchDirector()
    out = director.run("post_match_learning", context={"matches_path": str(s.data_processed_dir / "real_matches_standardized.csv")})
    run_dir = Path(out["run_dir"])
    assert (run_dir / "post_match_report.json").exists()
    assert (run_dir / "optimizer_suggestions.json").exists()
    assert out["status"] in {"completed", "failed", "retrying", "blocked"}
    assert {"status", "steps", "artifacts", "metrics", "decision"} <= set(out.keys())

    payload = json.loads((run_dir / "post_match_report.json").read_text(encoding="utf-8"))
    assert payload["report_type"] == "post_match_learning"
    assert "metrics" in payload
