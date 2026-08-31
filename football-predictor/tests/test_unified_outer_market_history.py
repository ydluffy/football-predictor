from __future__ import annotations

import json

import pandas as pd

from data.unified_outer_market_history import build_unified_histories


def test_the_odds_snapshots_enter_unified_and_model_histories(tmp_path):
    root = tmp_path / "snapshots"; snapshot = root / "2026-08-17_1105_confirm"; snapshot.mkdir(parents=True)
    audit = {
        "source": "the_odds_api", "status": "complete", "snapshot_type": "confirm",
        "captured_at": "2026-08-17T03:05:00+00:00",
        "files": {"raw_payload.json": {"sha256": "abc"}},
    }
    (snapshot / "audit.json").write_text(json.dumps(audit), encoding="utf-8")
    pd.DataFrame([{
        "match_id": "2026-08-17|001", "match_number": "001", "competition": "英超",
        "competition_id": "ENG_PREMIER_LEAGUE", "sport_key": "soccer_epl",
        "home_team": "曼城", "away_team": "阿森纳", "kickoff": "2026-08-17T20:00:00+08:00",
        "mapping_status": "mapped", "event_id": "e1", "external_home_team": "Manchester City",
        "external_away_team": "Arsenal",
    }]).to_csv(snapshot / "sporttery_alignment.csv", index=False)
    odds = []
    for bookmaker in ("a", "b"):
        for label, name, price, point in (
            ("home_spread", "Manchester City", 1.9, -0.5),
            ("away_spread", "Arsenal", 1.95, 0.5),
        ):
            odds.append({
                "event_id": "e1", "bookmaker_key": bookmaker, "bookmaker_title": bookmaker,
                "market_key": "spreads", "outcome_label": label, "outcome_name": name,
                "price": price, "point": point, "market_last_update": "2026-08-17T03:04:00Z",
            })
    pd.DataFrame(odds).to_csv(snapshot / "odds.csv", index=False)
    pd.DataFrame([
        {"event_id": "e1", "market_key": "h2h", "point": "", "home_avg_odds": 1.8,
         "draw_avg_odds": 3.6, "away_avg_odds": 4.2},
        {"event_id": "e1", "market_key": "totals", "point": 2.5,
         "over_avg_odds": 1.9, "under_avg_odds": 1.95},
    ]).to_csv(snapshot / "match_market_summary.csv", index=False)
    pd.DataFrame(columns=[]).to_csv(snapshot / "raw_payload.json", index=False)
    api = tmp_path / "api.csv"; pd.DataFrame().to_csv(api, index=False)

    outer, model, audit_result = build_unified_histories(
        api_football_history=api, the_odds_snapshot_root=root,
    )

    assert outer["match_id"].eq("2026-08-17|001").all()
    assert outer["eligible_for_primary_research"].astype(bool).sum() == 2
    assert len(model) == 1
    assert bool(model.iloc[0]["complete_for_shadow_inference"])
    assert audit_result["the_odds_snapshots"] == 1
