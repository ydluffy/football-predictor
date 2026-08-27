from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class DataSourceSpec:
    source_id: str
    display_name: str
    channel: str
    automated: bool
    browser_required: bool
    official: bool
    reliability: str
    dimensions: tuple[str, ...]
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    recommended_fallback: str = ""


DATA_SOURCE_REGISTRY: dict[str, DataSourceSpec] = {
    "espn_world_cup_live": DataSourceSpec(
        source_id="espn_world_cup_live",
        display_name="ESPN World Cup public data",
        channel="public_api",
        automated=True,
        browser_required=False,
        official=False,
        reliability="medium",
        dimensions=(
            "fixtures",
            "teams",
            "players",
            "completed_lineups",
            "national_appearances",
        ),
        required_fields=("match_id", "date", "home_team", "away_team"),
        optional_fields=("player_id", "role", "minutes", "status"),
        limitations=(
            "Availability and injury rows are often absent from public payloads.",
            "Confirmed lineups are more reliable after kickoff or after the match.",
        ),
        recommended_fallback="Use manual absence and realtime lineup inputs when ESPN has no availability rows.",
    ),
    "sporttery_lottery_gov": DataSourceSpec(
        source_id="sporttery_lottery_gov",
        display_name="China Sports Lottery SPF/RQSPF calculator",
        channel="browser_rendered_page",
        automated=True,
        browser_required=True,
        official=True,
        reliability="medium",
        dimensions=(
            "spf_odds",
            "handicap_odds",
            "handicap_line",
            "support_rate",
            "market_snapshot",
        ),
        required_fields=(
            "date",
            "match_number",
            "home_team",
            "away_team",
            "home_handicap",
            "rqspf_odds_home",
            "rqspf_odds_draw",
            "rqspf_odds_away",
        ),
        optional_fields=(
            "spf_odds_home",
            "spf_odds_draw",
            "spf_odds_away",
            "support_home_pct",
            "support_draw_pct",
            "support_away_pct",
        ),
        limitations=(
            "The page is dynamically rendered and has no stable public API contract.",
            "Historical opening lines cannot be recovered unless snapshots were already captured.",
        ),
        recommended_fallback="Keep rendered text, screenshot, and parsed CSV; use manual paste import if rendering changes.",
    ),
    "leisu_public": DataSourceSpec(
        source_id="leisu_public",
        display_name="Leisu public football pages",
        channel="http_or_browser_rendered_html",
        automated=True,
        browser_required=False,
        official=False,
        reliability="low",
        dimensions=(
            "match_links",
            "zh_team_names",
            "public_intelligence_count",
            "analysis_links",
        ),
        required_fields=(
            "leisu_match_id",
            "competition",
            "date_text",
            "time_text",
            "home_team_zh",
            "away_team_zh",
        ),
        optional_fields=(
            "intelligence_url",
            "intelligence_count",
            "analysis_url",
        ),
        limitations=(
            "Detail and intelligence pages may block automated access.",
            "Home-page coverage is not guaranteed for all World Cup fixtures.",
        ),
        recommended_fallback="Use browser-rendered capture and keep source HTML for parser repair.",
    ),
    "leisu_structured_intelligence": DataSourceSpec(
        source_id="leisu_structured_intelligence",
        display_name="Leisu intelligence detail pages",
        channel="http_or_cached_html",
        automated=True,
        browser_required=False,
        official=False,
        reliability="low",
        dimensions=(
            "structured_intelligence",
            "injury_mentions",
            "lineup_mentions",
            "tactical_mentions",
            "motivation_mentions",
        ),
        required_fields=("match_id", "category", "severity", "text", "source", "url"),
        optional_fields=("team", "updated_at"),
        limitations=(
            "Page access may be blocked or content may be marketing/editorial text.",
            "Keyword extraction is weak evidence until cross-checked or manually confirmed.",
        ),
        recommended_fallback="Keep raw HTML cache and route extracted rows through confidence scoring/manual review.",
    ),
    "public_absence_intelligence": DataSourceSpec(
        source_id="public_absence_intelligence",
        display_name="Public injury/suspension intelligence",
        channel="public_html_or_manual_verified_csv",
        automated=False,
        browser_required=False,
        official=False,
        reliability="source_dependent",
        dimensions=(
            "injuries",
            "suspensions",
            "doubtful",
            "availability_signal",
            "source_url",
            "confidence",
        ),
        required_fields=("date", "team", "player", "status", "source", "confidence"),
        optional_fields=("player_id", "impact", "reason", "source_url", "reported_at", "notes"),
        limitations=(
            "This is a normalized intelligence table, not a guaranteed official feed.",
            "Rows should retain source URLs and confidence before they affect predictions.",
        ),
        recommended_fallback="Use official/FIFA/team sources when available; keep low-confidence news out of model-ready absences.",
    ),
    "api_football": DataSourceSpec(
        source_id="api_football",
        display_name="API-Football/API-SPORTS professional feed",
        channel="authenticated_api",
        automated=True,
        browser_required=False,
        official=False,
        reliability="high",
        dimensions=(
            "fixtures",
            "injuries",
            "suspensions",
            "realtime_lineups",
            "venues",
        ),
        required_fields=("source_fixture_id", "date", "home_team", "away_team"),
        optional_fields=("venue", "city", "status"),
        limitations=(
            "Requires API_FOOTBALL_KEY.",
            "Coverage depends on provider plan and competition support.",
        ),
        recommended_fallback="If no token is configured, use manual verified absence/lineup CSVs.",
    ),
    "sportmonks": DataSourceSpec(
        source_id="sportmonks",
        display_name="SportMonks football realtime feed",
        channel="authenticated_api",
        automated=True,
        browser_required=False,
        official=False,
        reliability="high",
        dimensions=(
            "fixtures",
            "sidelined",
            "injuries",
            "suspensions",
            "expected_lineups",
            "realtime_lineups",
            "formations",
        ),
        required_fields=("source_fixture_id", "date", "home_team", "away_team"),
        optional_fields=("venue", "status"),
        limitations=(
            "Requires SPORTMONKS_API_TOKEN and the correct World Cup season id.",
            "Lineup and sidelined coverage depends on plan and match timing.",
            "Confirmed lineups are usually available only close to kickoff.",
        ),
        recommended_fallback="Use API-Football or manual verified absence/lineup CSVs when SportMonks has no rows.",
    ),
    "football_data_org": DataSourceSpec(
        source_id="football_data_org",
        display_name="football-data.org FIFA World Cup feed",
        channel="authenticated_api",
        automated=True,
        browser_required=False,
        official=False,
        reliability="high",
        dimensions=(
            "fixtures",
            "results",
            "teams",
            "squads",
            "coaches",
            "referees",
        ),
        required_fields=("match_id", "date", "home_team", "away_team", "status"),
        optional_fields=("home_score", "away_score", "stage", "group", "matchday"),
        limitations=(
            "Requires FOOTBALL_DATA_TOKEN.",
            "Does not provide injury, suspension, or confirmed lineup feeds.",
            "Odds require a separate paid odds package.",
        ),
        recommended_fallback="Use this as a stable fixtures/results/squads source; pair with API-Football or manual feeds for injuries and lineups.",
    ),
    "the_odds_api": DataSourceSpec(
        source_id="the_odds_api",
        display_name="The Odds API FIFA World Cup odds feed",
        channel="authenticated_api",
        automated=True,
        browser_required=False,
        official=False,
        reliability="high",
        dimensions=(
            "multi_bookmaker_odds",
            "moneyline_h2h",
            "spreads",
            "totals",
            "market_snapshot",
        ),
        required_fields=(
            "event_id",
            "date",
            "home_team",
            "away_team",
            "bookmaker_key",
            "market_key",
            "outcome_label",
            "price",
        ),
        optional_fields=(
            "point",
            "bookmaker_last_update",
            "market_last_update",
            "fetched_at",
        ),
        limitations=(
            "Requires THE_ODDS_API_KEY.",
            "Market and bookmaker coverage depends on the API plan and event availability.",
            "This is market odds, not official injury, suspension, or lineup data.",
        ),
        recommended_fallback="Use Sporttery as the China-market baseline and this feed for multi-bookmaker cross-checking.",
    ),
    "external_player_profiles": DataSourceSpec(
        source_id="external_player_profiles",
        display_name="External player profile normalized table",
        channel="csv_or_provider_export",
        automated=False,
        browser_required=False,
        official=False,
        reliability="source_dependent",
        dimensions=(
            "market_value",
            "player_profile",
            "position",
            "availability_signal",
            "source_url",
        ),
        required_fields=("source", "canonical_name", "national_team"),
        optional_fields=(
            "player_id",
            "source_player_id",
            "source_url",
            "market_value_eur",
            "height_cm",
            "preferred_foot",
            "availability_status",
            "confidence",
        ),
        limitations=(
            "This is a normalized landing table, not a direct website crawler.",
            "Quality depends on the original provider and player identity matching.",
        ),
        recommended_fallback="Use Transfermarkt first for market values; keep source URLs and confidence for manual review.",
    ),
    "transfermarkt_public": DataSourceSpec(
        source_id="transfermarkt_public",
        display_name="Transfermarkt public pages",
        channel="public_html_or_manual_export",
        automated=False,
        browser_required=True,
        official=False,
        reliability="medium",
        dimensions=("market_value", "profile", "injury_signal", "suspension_signal"),
        required_fields=("canonical_name", "national_team"),
        optional_fields=("market_value_eur", "source_url", "availability_status"),
        limitations=("Automated scraping may be blocked or violate usage constraints; prefer cached/manual exports.",),
        recommended_fallback="Normalize exported rows into external_player_profiles.csv.",
    ),
    "whoscored_public": DataSourceSpec(
        source_id="whoscored_public",
        display_name="WhoScored public pages",
        channel="browser_rendered_page",
        automated=False,
        browser_required=True,
        official=False,
        reliability="medium",
        dimensions=("ratings", "lineups", "formations", "match_stats"),
        required_fields=("match_id",),
        optional_fields=("player_rating", "formation", "starter"),
        limitations=("Direct access is commonly blocked by anti-bot protection.",),
        recommended_fallback="Use only as a manual verification or cached-browser source until a stable legal feed is available.",
    ),
    "squawka_public": DataSourceSpec(
        source_id="squawka_public",
        display_name="Squawka public stats and analysis",
        channel="public_html_or_article_feed",
        automated=False,
        browser_required=False,
        official=False,
        reliability="medium",
        dimensions=("team_stats", "player_stats", "tactical_text", "match_centre"),
        required_fields=("match_id",),
        optional_fields=("stat_name", "stat_value", "source_url"),
        limitations=("Best suited for stats/articles, not guaranteed realtime injuries or confirmed lineups.",),
        recommended_fallback="Use as structured-intelligence text, not as a primary realtime feed.",
    ),
    "champdas_public": DataSourceSpec(
        source_id="champdas_public",
        display_name="Champdas football data",
        channel="unverified_website_or_commercial_feed",
        automated=False,
        browser_required=True,
        official=False,
        reliability="unknown",
        dimensions=("domestic_data_candidate",),
        required_fields=("source_url",),
        optional_fields=("notes",),
        limitations=("Access method and data contract are not verified yet.",),
        recommended_fallback="Keep as candidate source; verify account/API options before model integration.",
    ),
    "tzuqiu_public": DataSourceSpec(
        source_id="tzuqiu_public",
        display_name="tzuqiu.cc football pages",
        channel="unverified_public_html",
        automated=False,
        browser_required=True,
        official=False,
        reliability="unknown",
        dimensions=("chinese_public_candidate",),
        required_fields=("source_url",),
        optional_fields=("notes",),
        limitations=("Access stability and field coverage are not verified yet.",),
        recommended_fallback="Keep as low-priority candidate until stable pages are identified.",
    ),
    "manual_realtime_inputs": DataSourceSpec(
        source_id="manual_realtime_inputs",
        display_name="Manual verified realtime inputs",
        channel="human_verified_csv",
        automated=False,
        browser_required=False,
        official=False,
        reliability="operator_dependent",
        dimensions=("absences", "suspensions", "realtime_lineups", "structured_intelligence"),
        required_fields=("date", "team"),
        optional_fields=("player_name", "status", "source_url", "confidence"),
        limitations=("Not automatic; quality depends on source URLs and human verification.",),
        recommended_fallback="Require source URL and confidence before allowing strong model impact.",
    ),
}


PREDICTION_DIMENSIONS: dict[str, tuple[str, ...]] = {
    "historical_team_model": ("base_p_home", "base_p_draw", "base_p_away"),
    "sporttery_handicap": ("sporttery_market_source",),
    "multi_bookmaker_odds": ("the_odds_api_market_source", "multi_bookmaker_h2h_count"),
    "line_movement": ("line_movement_snapshots",),
    "public_intelligence": ("leisu_public_match_linked", "leisu_intelligence_count"),
    "absences_suspensions": ("home_absence_count", "away_absence_count"),
    "realtime_lineups": ("home_realtime_lineup_confirmed", "away_realtime_lineup_confirmed"),
    "structured_intelligence": ("structured_intelligence_count",),
    "player_strength": ("home_player_strength_confidence", "away_player_strength_confidence"),
}


def registry_as_rows() -> list[dict[str, object]]:
    return [
        {
            "source_id": spec.source_id,
            "display_name": spec.display_name,
            "channel": spec.channel,
            "automated": spec.automated,
            "browser_required": spec.browser_required,
            "official": spec.official,
            "reliability": spec.reliability,
            "dimensions": list(spec.dimensions),
            "required_fields": list(spec.required_fields),
            "optional_fields": list(spec.optional_fields),
            "limitations": list(spec.limitations),
            "recommended_fallback": spec.recommended_fallback,
        }
        for spec in DATA_SOURCE_REGISTRY.values()
    ]


def _coverage_for_field(frame: pd.DataFrame, field: str) -> dict[str, object]:
    if field not in frame.columns:
        return {
            "field": field,
            "present": False,
            "non_null_rows": 0,
            "coverage": 0.0,
        }
    series = frame[field]
    non_null = int(series.astype(str).str.strip().replace({"nan": "", "None": ""}).ne("").sum())
    rows = int(len(frame))
    return {
        "field": field,
        "present": True,
        "non_null_rows": non_null,
        "coverage": non_null / rows if rows else 0.0,
    }


def audit_source_frame(
    source_id: str,
    frame: pd.DataFrame,
    *,
    expected_rows: int | None = None,
    fetched_at: str | None = None,
    output_path: str | Path | None = None,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    spec = DATA_SOURCE_REGISTRY[source_id]
    rows = int(len(frame))
    required = [_coverage_for_field(frame, field) for field in spec.required_fields]
    optional = [_coverage_for_field(frame, field) for field in spec.optional_fields]
    missing_required = [item["field"] for item in required if not item["present"]]
    empty_required = [
        item["field"]
        for item in required
        if item["present"] and rows > 0 and float(item["coverage"]) <= 0.0
    ]
    row_coverage = rows / expected_rows if expected_rows else None
    if rows <= 0:
        status = "empty"
    elif missing_required:
        status = "schema_error"
    elif row_coverage is not None and row_coverage < 0.5:
        status = "low_coverage"
    elif empty_required:
        status = "partial"
    else:
        status = "ok"

    issues: list[str] = []
    if missing_required:
        issues.append(f"missing required fields: {', '.join(missing_required)}")
    if empty_required:
        issues.append(f"required fields without values: {', '.join(empty_required)}")
    if row_coverage is not None and row_coverage < 0.5:
        issues.append(f"low row coverage: {rows}/{expected_rows}")
    if rows <= 0:
        issues.append("no rows parsed")

    return {
        "source_id": spec.source_id,
        "display_name": spec.display_name,
        "status": status,
        "fetched_at": fetched_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "rows": rows,
        "expected_rows": expected_rows,
        "row_coverage": row_coverage,
        "output": str(output_path) if output_path else "",
        "automated": spec.automated,
        "browser_required": spec.browser_required,
        "official": spec.official,
        "reliability": spec.reliability,
        "dimensions": list(spec.dimensions),
        "required_field_coverage": required,
        "optional_field_coverage": optional,
        "issues": issues,
        "limitations": list(spec.limitations),
        "recommended_fallback": spec.recommended_fallback,
        "extra": extra or {},
    }


def _dimension_has_data(frame: pd.DataFrame, fields: Iterable[str]) -> pd.Series:
    present = [field for field in fields if field in frame.columns]
    if not present:
        return pd.Series([False] * len(frame), index=frame.index)
    data = frame[present]
    if data.empty:
        return pd.Series([False] * len(frame), index=frame.index)
    field_masks = []
    for field in present:
        series = data[field]
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().any():
            field_masks.append(numeric.fillna(0).gt(0))
        else:
            normalized = series.astype("string").fillna("").str.strip().str.casefold()
            field_masks.append(~normalized.isin({"", "0", "0.0", "false", "nan", "none"}))
    return pd.concat(field_masks, axis=1).any(axis=1)


def audit_prediction_coverage(
    predictions: pd.DataFrame,
    *,
    dimensions: dict[str, tuple[str, ...]] | None = None,
) -> dict[str, object]:
    dims = dimensions or PREDICTION_DIMENSIONS
    rows = int(len(predictions))
    dimension_rows: dict[str, dict[str, object]] = {}
    for name, fields in dims.items():
        mask = _dimension_has_data(predictions, fields)
        count = int(mask.sum())
        dimension_rows[name] = {
            "fields": list(fields),
            "matches_with_data": count,
            "coverage": count / rows if rows else 0.0,
            "missing_matches": rows - count,
        }
    critical_missing = [
        name
        for name in ("sporttery_handicap", "line_movement", "absences_suspensions", "realtime_lineups")
        if dimension_rows.get(name, {}).get("coverage", 0.0) < 0.5
    ]
    if rows <= 0:
        status = "empty"
    elif critical_missing:
        status = "insufficient"
    else:
        status = "usable"
    return {
        "status": status,
        "matches": rows,
        "dimension_coverage": dimension_rows,
        "critical_missing_dimensions": critical_missing,
    }
