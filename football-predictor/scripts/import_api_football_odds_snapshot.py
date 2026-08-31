from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data.api_football_odds_snapshot import archive_api_football_odds_snapshots  # noqa: E402
from data.api_football_prematch import build_api_football_match_mapping  # noqa: E402
from data.unified_outer_market_history import build_unified_histories  # noqa: E402
from world_cup.api_football_adapter import (  # noqa: E402
    ApiFootballClient,
    api_fixture_rows_to_frame,
)


def project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def load_project_env() -> None:
    env_path = ROOT / ".env"
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


def build_mapping_from_scan(
    *,
    client: ApiFootballClient,
    scan_path: Path,
    league_id: int = 0,
    date: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    scan = json.loads(scan_path.read_text(encoding="utf-8"))
    local = pd.DataFrame(scan.get("fixtures", []))
    if local.empty:
        return pd.DataFrame(), {"mode": "automatic", "mapped_rows": 0, "reason": "scan_has_no_fixtures"}
    kickoff = pd.to_datetime(local.get("kickoff"), errors="coerce", utc=True)
    fixture_dates = sorted(
        {item.tz_convert("Asia/Shanghai").date().isoformat() for item in kickoff.dropna()}
    ) or [date]
    api_rows: list[dict[str, object]] = []
    provider_date_rows = 0
    for fixture_date in fixture_dates:
        payload = client.get("fixtures", {"date": fixture_date, "timezone": "Asia/Shanghai"})
        if payload.get("errors"):
            raise RuntimeError(f"API-Football fixture payload contains errors for {fixture_date}")
        api_rows.extend(payload.get("response") or [])
        provider_date_rows += int(payload.get("results", 0) or 0)
    api_fixtures = api_fixture_rows_to_frame(api_rows)
    if not api_fixtures.empty and int(league_id) > 0:
        api_fixtures = api_fixtures[
            pd.to_numeric(api_fixtures["league_id"], errors="coerce").eq(int(league_id))
        ].copy()
    if api_fixtures.empty:
        return pd.DataFrame(), {
            "mode": "automatic",
            "mapped_rows": 0,
            "fixture_dates": fixture_dates,
            "provider_date_rows": provider_date_rows,
            "provider_league_rows": 0,
            "reason": "no_provider_fixtures_for_requested_scope",
        }
    mapping, audit = build_api_football_match_mapping(local, api_fixtures)
    return mapping, {
        "mode": "automatic",
        "fixture_dates": fixture_dates,
        "league_filter": int(league_id) if int(league_id) > 0 else None,
        "provider_date_rows": provider_date_rows,
        "provider_league_rows": int(len(api_fixtures)),
        **audit,
    }


def main() -> None:
    load_project_env()
    parser = argparse.ArgumentParser(
        description="Archive immutable API-Football Asian-handicap odds snapshots."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--mapping", default="", help="Existing API-Football to Sporttery mapping CSV.")
    source.add_argument("--scan-json", default="", help="Sporttery scan JSON used to build a unique mapping.")
    parser.add_argument("--league-id", type=int, default=0, help="Optional provider league filter; omit to map all fixtures on the date.")
    parser.add_argument("--season", type=int, default=0, help="Optional audit metadata; date lookup avoids Free-plan season restrictions.")
    parser.add_argument("--date", default="", help="Required with --scan-json (YYYY-MM-DD).")
    parser.add_argument("--mapping-output", default="artifacts/data/api_football_odds_mapping_latest.csv")
    parser.add_argument("--captured-at", default="")
    parser.add_argument("--api-key", default="", help="Defaults to API_FOOTBALL_KEY from process/.env.")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--raw-root", default="data/external/api_football_odds/raw")
    parser.add_argument("--snapshot-root", default="data/external/api_football_odds/snapshots")
    parser.add_argument("--history", default="data/external/api_football_odds/history.csv")
    parser.add_argument("--audit-output", default="artifacts/data/api_football_odds_snapshot_latest.json")
    parser.add_argument("--fail-fast", action="store_true")
    args = parser.parse_args()

    key = args.api_key or os.getenv("API_FOOTBALL_KEY", "")
    client = ApiFootballClient(api_key=key, timeout=args.timeout)
    if not client.configured:
        raise SystemExit("API_FOOTBALL_KEY is not configured")

    if args.mapping:
        mapping = pd.read_csv(project_path(args.mapping), dtype=str).fillna("")
        mapping_audit: dict[str, object] = {"mode": "provided", "rows": int(len(mapping))}
    else:
        if not args.date:
            raise SystemExit("--scan-json requires --date")
        mapping, mapping_audit = build_mapping_from_scan(
            client=client,
            scan_path=project_path(args.scan_json),
            league_id=args.league_id,
            date=args.date,
        )
        if args.season:
            mapping_audit["requested_season"] = args.season
        mapping_path = project_path(args.mapping_output)
        mapping_path.parent.mkdir(parents=True, exist_ok=True)
        mapping.to_csv(mapping_path, index=False, encoding="utf-8-sig")
        mapping_audit["output"] = str(mapping_path.resolve())

    if mapping.empty:
        raise SystemExit("no uniquely mapped API-Football fixtures; no odds request performed")
    captured_at = args.captured_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    audit = archive_api_football_odds_snapshots(
        client=client,
        mapping=mapping,
        captured_at=captured_at,
        raw_root=project_path(args.raw_root),
        snapshot_root=project_path(args.snapshot_root),
        history_path=project_path(args.history),
        continue_on_error=not args.fail_fast,
    )
    audit["mapping"] = mapping_audit
    unified_outer, unified_model, unified_audit = build_unified_histories(
        api_football_history=project_path(args.history),
        the_odds_snapshot_root=ROOT / "data" / "external" / "the_odds_api_sporttery" / "snapshots",
    )
    unified_outer_path = ROOT / "data" / "external" / "outer_market_snapshots" / "history.csv"
    unified_model_path = ROOT / "data" / "manual" / "external_market_snapshot_history.csv"
    unified_audit_path = ROOT / "artifacts" / "data" / "unified_outer_market_history_latest.json"
    unified_outer_path.parent.mkdir(parents=True, exist_ok=True)
    unified_model_path.parent.mkdir(parents=True, exist_ok=True)
    unified_outer.to_csv(unified_outer_path, index=False, encoding="utf-8-sig")
    unified_model.to_csv(unified_model_path, index=False, encoding="utf-8-sig")
    unified_audit.update({"outer_output": str(unified_outer_path), "model_output": str(unified_model_path)})
    unified_audit_path.write_text(json.dumps(unified_audit, ensure_ascii=False, indent=2), encoding="utf-8")
    audit["unified_history"] = unified_audit
    audit_path = project_path(args.audit_output)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
