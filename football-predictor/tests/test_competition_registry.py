from __future__ import annotations

from data.competition_registry import load_competition_registry, load_team_alias_registry


def test_competition_registry_resolves_codes_and_chinese_aliases() -> None:
    registry = load_competition_registry()

    assert registry.resolve("E0").competition_id == "ENG_PREMIER_LEAGUE"
    assert registry.resolve(" 英 超 ").competition_id == "ENG_PREMIER_LEAGUE"
    assert registry.resolve("J.League").competition_id == "JPN_J1_LEAGUE"
    assert registry.resolve("世界杯").competition_id == "FIFA_WORLD_CUP"


def test_competition_registry_returns_explicit_safe_fallback() -> None:
    metadata = load_competition_registry().annotate("未登记联赛")

    assert metadata["competition_id"] == "UNKNOWN"
    assert metadata["competition_known"] is False
    assert metadata["recommended_model_route"] == "market_anchor_fallback"
    assert metadata["model_route_status"] == "fallback_required"


def test_registry_does_not_claim_untrained_league_coverage() -> None:
    registry = load_competition_registry()

    la_liga = registry.annotate("西甲")
    assert la_liga["historical_model_coverage"] is False
    assert la_liga["recommended_model_route"] == "market_anchor_fallback"
    assert la_liga["model_route_status"] == "historical_training_data_required"


def test_team_alias_registry_normalizes_cross_source_names() -> None:
    registry = load_team_alias_registry()

    assert registry.resolve("曼联") == "Manchester United"
    assert registry.resolve("Man Utd") == "Manchester United"
    assert registry.resolve("横滨水手") == "Yokohama F. Marinos"
    assert registry.annotate("尚未登记球队")["team_alias_known"] is False
