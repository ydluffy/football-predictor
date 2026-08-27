from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd

from data.competition_registry import load_team_alias_registry, normalize_alias
from world_cup.the_odds_api_adapter import (
    TheOddsApiClient,
    fetch_odds,
    odds_payload_to_frame,
    summarize_odds_frame,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROUTING_PATH = PROJECT_ROOT / "config" / "the_odds_api_sport_keys.json"
ALIGNMENT_COLUMNS = [
    "match_id",
    "match_number",
    "competition",
    "competition_id",
    "sport_key",
    "home_team",
    "away_team",
    "kickoff",
    "mapping_status",
    "mapping_reason",
    "event_id",
    "external_home_team",
    "external_away_team",
    "external_commence_time",
    "kickoff_delta_minutes",
    "market_keys",
    "bookmaker_count",
    "odds_rows",
    "captured_at",
]


def load_project_env(path: str | Path = PROJECT_ROOT / ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_sport_key_routes(path: str | Path = DEFAULT_ROUTING_PATH) -> dict[str, str]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if int(payload.get("schema_version", 0)) != 1:
        raise ValueError("unsupported The Odds API routing schema_version")
    return {
        str(key): str(value)
        for key, value in payload.get("competition_sport_keys", {}).items()
        if str(key).strip() and str(value).strip()
    }


def route_sport_keys(
    fixtures: Iterable[dict[str, Any]],
    *,
    routes: dict[str, str] | None = None,
) -> tuple[list[str], list[dict[str, str]]]:
    mapping = routes or load_sport_key_routes()
    keys: set[str] = set()
    unrouted: list[dict[str, str]] = []
    seen_unrouted: set[tuple[str, str]] = set()
    for fixture in fixtures:
        competition_id = str(fixture.get("competition_id") or "UNKNOWN")
        sport_key = mapping.get(competition_id, "")
        if sport_key:
            keys.add(sport_key)
            continue
        marker = (competition_id, str(fixture.get("competition") or ""))
        if marker not in seen_unrouted:
            seen_unrouted.add(marker)
            unrouted.append({"competition_id": marker[0], "competition": marker[1]})
    return sorted(keys), unrouted


def _canonical_team(value: object) -> str:
    registry = load_team_alias_registry()
    return registry.resolve(value) or str(value or "").strip()


def align_fixtures_to_odds(
    fixtures: Iterable[dict[str, Any]],
    odds: pd.DataFrame,
    *,
    captured_at: str,
    kickoff_tolerance_minutes: int = 180,
) -> pd.DataFrame:
    fixture_list = list(fixtures)
    if odds.empty:
        events = pd.DataFrame()
    else:
        events = odds[
            ["event_id", "sport_key", "commence_time", "raw_home_team", "raw_away_team"]
        ].drop_duplicates().copy()
        events["commence_parsed"] = pd.to_datetime(
            events["commence_time"], errors="coerce", utc=True, format="mixed"
        )
        events["home_canonical"] = events["raw_home_team"].map(_canonical_team)
        events["away_canonical"] = events["raw_away_team"].map(_canonical_team)
        events["home_key"] = events["home_canonical"].map(normalize_alias)
        events["away_key"] = events["away_canonical"].map(normalize_alias)

    rows: list[dict[str, Any]] = []
    for fixture in fixture_list:
        kickoff = pd.to_datetime(fixture.get("kickoff"), errors="coerce", utc=True, format="mixed")
        home = fixture.get("home_team_canonical") or fixture.get("home_team")
        away = fixture.get("away_team_canonical") or fixture.get("away_team")
        home_key = normalize_alias(_canonical_team(home))
        away_key = normalize_alias(_canonical_team(away))
        candidates = events[
            events.get("home_key", pd.Series(dtype=str)).eq(home_key)
            & events.get("away_key", pd.Series(dtype=str)).eq(away_key)
        ].copy()
        if not candidates.empty and not pd.isna(kickoff):
            candidates["delta_minutes"] = (
                candidates["commence_parsed"].sub(kickoff).abs().dt.total_seconds() / 60.0
            )
            candidates = candidates[
                candidates["delta_minutes"].le(int(kickoff_tolerance_minutes))
            ].sort_values(["delta_minutes", "event_id"])

        status = "unmatched"
        reason = "team_and_kickoff_not_found"
        selected: dict[str, Any] = {}
        if len(candidates) == 1:
            status = "mapped"
            reason = "exact_canonical_teams_and_kickoff_tolerance"
            selected = candidates.iloc[0].to_dict()
        elif len(candidates) > 1:
            status = "ambiguous"
            reason = "multiple_external_events_match"

        event_id = str(selected.get("event_id") or "")
        event_odds = odds[odds["event_id"].astype(str).eq(event_id)] if event_id else odds.iloc[0:0]
        rows.append(
            {
                "match_id": fixture.get("match_id", ""),
                "match_number": fixture.get("match_number", ""),
                "competition": fixture.get("competition", ""),
                "competition_id": fixture.get("competition_id", "UNKNOWN"),
                "sport_key": selected.get("sport_key", ""),
                "home_team": fixture.get("home_team", ""),
                "away_team": fixture.get("away_team", ""),
                "kickoff": fixture.get("kickoff", ""),
                "mapping_status": status,
                "mapping_reason": reason,
                "event_id": event_id,
                "external_home_team": selected.get("raw_home_team", ""),
                "external_away_team": selected.get("raw_away_team", ""),
                "external_commence_time": selected.get("commence_time", ""),
                "kickoff_delta_minutes": (
                    round(float(selected["delta_minutes"]), 3)
                    if selected.get("delta_minutes") is not None
                    else ""
                ),
                "market_keys": ",".join(sorted(event_odds["market_key"].dropna().astype(str).unique())),
                "bookmaker_count": int(event_odds["bookmaker_key"].nunique()) if not event_odds.empty else 0,
                "odds_rows": int(len(event_odds)),
                "captured_at": captured_at,
            }
        )
    return pd.DataFrame(rows, columns=ALIGNMENT_COLUMNS)


def _safe_error_message(exc: Exception, api_key: str) -> str:
    message = str(exc)
    return message.replace(api_key, "***") if api_key else message


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _immutable_snapshot_dir(root: Path, *, captured_at: datetime, snapshot_type: str) -> Path:
    stem = f"{captured_at:%Y-%m-%d_%H%M%S}_{snapshot_type}"
    candidate = root / stem
    sequence = 0
    while candidate.exists():
        sequence += 1
        candidate = root / f"{stem}_{sequence:02d}"
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def capture_sporttery_the_odds_snapshot(
    *,
    scan: dict[str, Any],
    snapshot_root: str | Path,
    api_key: str,
    snapshot_type: str,
    regions: str = "eu,uk,us,au",
    markets: str = "h2h,spreads,totals",
    bookmakers: str = "",
    timeout: int = 60,
    kickoff_tolerance_minutes: int = 180,
    sport_keys: list[str] | None = None,
    fetcher: Callable[..., list[dict[str, Any]]] = fetch_odds,
) -> dict[str, Any]:
    if scan.get("scan_stage_valid") is False or str(scan.get("batch_status", "")).startswith("invalid_"):
        raise ValueError("invalid Sporttery scan cannot authorize an external odds snapshot")
    if scan.get("stage") not in {None, "confirm"}:
        raise ValueError("The Odds API Sporttery snapshots require a confirmation scan")
    captured_dt = datetime.now(timezone.utc).replace(microsecond=0)
    captured_at = captured_dt.isoformat()
    fixtures = [
        item for item in scan.get("fixtures", []) if item.get("sale_status") == "on_sale"
    ]
    routed_keys, unrouted = route_sport_keys(fixtures)
    selected_keys = sorted(set(sport_keys if sport_keys is not None else routed_keys))
    snapshot_dir = _immutable_snapshot_dir(
        Path(snapshot_root), captured_at=captured_dt, snapshot_type=snapshot_type
    )
    client = TheOddsApiClient(api_key=api_key, timeout=timeout)
    payload_by_sport: dict[str, list[dict[str, Any]]] = {}
    requests: list[dict[str, Any]] = []
    frames: list[pd.DataFrame] = []

    if client.configured:
        for sport_key in selected_keys:
            try:
                payload = fetcher(
                    client,
                    sport_key=sport_key,
                    regions=regions,
                    markets=markets,
                    bookmakers=bookmakers,
                )
                payload_by_sport[sport_key] = payload
                frame = odds_payload_to_frame(payload)
                frames.append(frame)
                requests.append(
                    {
                        "sport_key": sport_key,
                        "status": "ok",
                        "events": len(payload),
                        "odds_rows": len(frame),
                        "requests_remaining": client.last_headers.get("x-requests-remaining", ""),
                        "requests_used": client.last_headers.get("x-requests-used", ""),
                    }
                )
            except Exception as exc:
                requests.append(
                    {
                        "sport_key": sport_key,
                        "status": "error",
                        "error": _safe_error_message(exc, client.api_key),
                        "requests_remaining": client.last_headers.get("x-requests-remaining", ""),
                        "requests_used": client.last_headers.get("x-requests-used", ""),
                    }
                )

    odds = pd.concat(frames, ignore_index=True, sort=False) if frames else odds_payload_to_frame([])
    summary = summarize_odds_frame(odds)
    alignment = align_fixtures_to_odds(
        fixtures,
        odds,
        captured_at=captured_at,
        kickoff_tolerance_minutes=kickoff_tolerance_minutes,
    )
    raw_path = snapshot_dir / "raw_payload.json"
    odds_path = snapshot_dir / "odds.csv"
    summary_path = snapshot_dir / "match_market_summary.csv"
    alignment_path = snapshot_dir / "sporttery_alignment.csv"
    raw_path.write_text(json.dumps(payload_by_sport, ensure_ascii=False, indent=2), encoding="utf-8")
    odds.to_csv(odds_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    alignment.to_csv(alignment_path, index=False, encoding="utf-8-sig")

    mapped = int(alignment["mapping_status"].eq("mapped").sum()) if not alignment.empty else 0
    errors = sum(item["status"] == "error" for item in requests)
    if not fixtures:
        status = "no_on_sale_fixtures"
    elif not client.configured:
        status = "not_configured"
    elif not selected_keys:
        status = "no_routed_sports"
    elif errors == len(requests):
        status = "source_failed"
    elif mapped == len(fixtures):
        status = "complete"
    elif mapped:
        status = "partial"
    else:
        status = "unmatched"

    audit = {
        "schema_version": 1,
        "source": "the_odds_api",
        "snapshot_type": snapshot_type,
        "captured_at": captured_at,
        "sales_day": scan.get("sales_day", ""),
        "status": status,
        "configured": client.configured,
        "regions": regions,
        "markets": markets,
        "sport_keys": selected_keys,
        "unrouted_competitions": unrouted,
        "requests": requests,
        "on_sale_fixtures": len(fixtures),
        "mapped_fixtures": mapped,
        "ambiguous_fixtures": int(alignment["mapping_status"].eq("ambiguous").sum()) if not alignment.empty else 0,
        "unmatched_fixtures": int(alignment["mapping_status"].eq("unmatched").sum()) if not alignment.empty else 0,
        "events": int(odds["event_id"].nunique()) if not odds.empty else 0,
        "odds_rows": int(len(odds)),
        "summary_rows": int(len(summary)),
        "kickoff_tolerance_minutes": int(kickoff_tolerance_minutes),
        "snapshot_dir": str(snapshot_dir),
        "files": {
            path.name: {"path": str(path), "sha256": _sha256(path)}
            for path in (raw_path, odds_path, summary_path, alignment_path)
        },
        "ledger_write_performed": False,
    }
    audit_path = snapshot_dir / "audit.json"
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return audit
