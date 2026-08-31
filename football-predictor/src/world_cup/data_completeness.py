from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompletenessComponent:
    name: str
    weight: float
    value: float

    @property
    def contribution(self) -> float:
        return max(0.0, min(1.0, float(self.value))) * float(self.weight)


def _has_value(value: object) -> bool:
    text = str(value or "").strip().lower()
    return bool(text) and text not in {"nan", "none", "null"}


def _probability(value: object) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _lineup_coverage(row: dict[str, object]) -> float:
    home = 1.0 if int(float(row.get("home_lineup_confirmed", 0) or 0)) > 0 else 0.0
    away = 1.0 if int(float(row.get("away_lineup_confirmed", 0) or 0)) > 0 else 0.0
    home_rt = 1.0 if int(float(row.get("home_realtime_lineup_confirmed", 0) or 0)) > 0 else 0.0
    away_rt = 1.0 if int(float(row.get("away_realtime_lineup_confirmed", 0) or 0)) > 0 else 0.0
    return max((home + away) / 2.0, (home_rt + away_rt) / 2.0)


def _player_strength_coverage(row: dict[str, object]) -> float:
    home = _probability(row.get("home_player_strength_confidence", 0))
    away = _probability(row.get("away_player_strength_confidence", 0))
    return (home + away) / 2.0


def _sporttery_handicap_coverage(row: dict[str, object]) -> float:
    return 1.0 if str(row.get("handicap_line_source", "")) == "sporttery" else 0.0


def _spf_odds_coverage(row: dict[str, object]) -> float:
    fields = [
        "spf_market_home_probability",
        "spf_market_draw_probability",
        "spf_market_away_probability",
    ]
    return sum(1 for field in fields if _has_value(row.get(field))) / len(fields)


def _handicap_odds_coverage(row: dict[str, object]) -> float:
    fields = [
        "handicap_market_home_probability",
        "handicap_market_draw_probability",
        "handicap_market_away_probability",
    ]
    return sum(1 for field in fields if _has_value(row.get(field))) / len(fields)


def _leisu_coverage(row: dict[str, object]) -> float:
    linked = int(float(row.get("leisu_public_match_linked", 0) or 0)) > 0
    has_intelligence = int(float(row.get("leisu_has_intelligence", 0) or 0)) > 0
    if has_intelligence:
        return 1.0
    if linked:
        return 0.5
    return 0.0


def _absence_coverage(row: dict[str, object]) -> float:
    has_absence_feed = (
        int(float(row.get("home_absence_count", 0) or 0)) > 0
        or int(float(row.get("away_absence_count", 0) or 0)) > 0
        or float(row.get("home_absence_weighted_impact", 0.0) or 0.0) > 0
        or float(row.get("away_absence_weighted_impact", 0.0) or 0.0) > 0
    )
    has_structured_absence_news = (
        int(float(row.get("structured_injury_count", 0) or 0)) > 0
        or int(float(row.get("structured_suspension_count", 0) or 0)) > 0
    )
    return 1.0 if has_absence_feed or has_structured_absence_news else 0.0


def _line_movement_coverage(row: dict[str, object]) -> float:
    try:
        snapshots = float(row.get("line_movement_snapshots", 0) or 0)
    except (TypeError, ValueError):
        snapshots = 0.0
    if snapshots >= 2:
        return 1.0
    if snapshots > 0:
        return 0.5
    return 0.0


def _structured_intelligence_coverage(row: dict[str, object]) -> float:
    count = int(float(row.get("structured_intelligence_count", 0) or 0))
    if count >= 3:
        return 1.0
    if count > 0:
        return 0.5
    return _leisu_coverage(row)


def data_completeness_components(row: dict[str, object]) -> list[CompletenessComponent]:
    return [
        CompletenessComponent("historical_team_model", 0.10, 1.0),
        CompletenessComponent("player_strength", 0.12, _player_strength_coverage(row)),
        CompletenessComponent("confirmed_lineups", 0.15, _lineup_coverage(row)),
        CompletenessComponent("absences_suspensions", 0.12, _absence_coverage(row)),
        CompletenessComponent("sporttery_handicap", 0.12, _sporttery_handicap_coverage(row)),
        CompletenessComponent("line_movement", 0.09, _line_movement_coverage(row)),
        CompletenessComponent("spf_market_odds", 0.10, _spf_odds_coverage(row)),
        CompletenessComponent("handicap_market_odds", 0.10, _handicap_odds_coverage(row)),
        CompletenessComponent("public_intelligence", 0.10, _structured_intelligence_coverage(row)),
    ]


def completeness_grade(score: float) -> str:
    value = float(score)
    if value >= 0.80:
        return "A"
    if value >= 0.65:
        return "B"
    if value >= 0.45:
        return "C"
    return "D"


def data_completeness_summary(row: dict[str, object]) -> dict[str, object]:
    components = data_completeness_components(row)
    score = sum(component.contribution for component in components)
    missing = [
        component.name
        for component in components
        if component.value < 0.5 and component.weight >= 0.10
    ]
    return {
        "data_completeness_score": score,
        "data_completeness_grade": completeness_grade(score),
        "data_completeness_missing": ";".join(missing),
        **{
            f"data_component_{component.name}": component.value
            for component in components
        },
    }
