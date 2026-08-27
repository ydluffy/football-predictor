from __future__ import annotations

import pandas as pd

from data.prematch_intelligence import build_prematch_intelligence_features, normalize_prematch_intelligence


def _row(**overrides):
    row = {
        "record_id": "r1",
        "match_id": "m1",
        "competition_id": "ENG_PREMIER_LEAGUE",
        "kickoff_at": "2026-08-15T14:00:00Z",
        "observed_at": "2026-08-15T10:00:00Z",
        "source": "manual_verified",
        "source_url": "https://example.test/evidence",
        "license_status": "manual_verified",
        "team": "Home FC",
        "signal_type": "absence",
        "subject": "Player A",
        "status": "injured",
        "numeric_value": 2.0,
        "confidence": 0.9,
        "confirmed": 1,
        "expires_at": "2026-08-15T14:00:00Z",
        "notes": "verified",
    }
    row.update(overrides)
    return row


def test_normalization_rejects_post_kickoff_and_permission_required() -> None:
    frame = pd.DataFrame(
        [
            _row(),
            _row(record_id="late", observed_at="2026-08-15T15:00:00Z"),
            _row(
                record_id="blocked",
                source="kleague_official_portal",
                license_status="permission_required",
            ),
        ]
    )
    normalized, audit = normalize_prematch_intelligence(frame)
    assert normalized["record_id"].tolist() == ["r1"]
    assert audit["post_kickoff_rows"] == 1
    assert audit["usable_rows"] == 1
    assert audit["unknown_competition_rows"] == 0


def test_feature_builder_enforces_analysis_cutoff_and_availability_flags() -> None:
    rows = [_row()]
    rows.extend(
        _row(
            record_id=f"starter-{side}-{index}",
            team=f"{side.title()} FC",
            signal_type="confirmed_starter",
            subject=f"Player {index}",
            status="starter",
            numeric_value=1,
            confidence=1.0,
        )
        for side in ("home", "away")
        for index in range(11)
    )
    rows.append(
        _row(
            record_id="future-xg",
            signal_type="prematch_xg",
            subject="team",
            numeric_value=1.7,
            observed_at="2026-08-15T13:30:00Z",
        )
    )
    fixtures = pd.DataFrame(
        [
            {
                "match_id": "m1",
                "kickoff_at": "2026-08-15T14:00:00Z",
                "analysis_at": "2026-08-15T13:00:00Z",
                "home_team": "Home FC",
                "away_team": "Away FC",
            }
        ]
    )
    features, audit = build_prematch_intelligence_features(fixtures, pd.DataFrame(rows))
    assert features.loc[0, "home_absence_impact"] == 1.8
    assert features.loc[0, "both_lineups_confirmed"] == 1.0
    assert features.loc[0, "prematch_xg_available"] == 0.0
    assert features.loc[0, "home_prematch_xg"] == 0.0
    assert audit["unmatched_or_after_cutoff_rows"] == 1


def test_missing_evidence_is_not_disguised_as_available_zero() -> None:
    fixtures = pd.DataFrame(
        [{"match_id": "m2", "kickoff_at": "2026-08-15T14:00:00Z", "home_team": "A", "away_team": "B"}]
    )
    empty = pd.DataFrame(columns=list(_row().keys()))
    features, _ = build_prematch_intelligence_features(fixtures, empty)
    assert features.loc[0, "prematch_intelligence_available"] == 0.0
    assert features.loc[0, "team_strength_available"] == 0.0
    assert features.loc[0, "home_team_strength"] == 0.0


def test_feature_builder_resolves_fixture_and_intelligence_team_aliases() -> None:
    row = _row(match_id="alias-match", competition_id="ESP_LA_LIGA", team="桑坦德",
               kickoff_at="2026-08-16T15:00:00Z", observed_at="2026-08-16T12:00:00Z",
               expires_at="2026-08-16T15:00:00Z")
    fixtures = pd.DataFrame([{"match_id":"alias-match","kickoff_at":"2026-08-16T15:00:00Z",
                              "analysis_at":"2026-08-16T14:00:00Z","home_team":"桑坦德","away_team":"比利亚雷"}])
    features, audit = build_prematch_intelligence_features(fixtures, pd.DataFrame([row]))
    assert features.loc[0,"home_absence_count"] == 1.0
    assert audit["fixtures_with_intelligence"] == 1
