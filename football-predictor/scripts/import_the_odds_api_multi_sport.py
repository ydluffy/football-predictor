from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from world_cup.the_odds_api_adapter import (  # noqa: E402
    TheOddsApiClient,
    fetch_odds,
    odds_payload_to_frame,
    summarize_odds_frame,
)


DEFAULT_SPORT_KEYS = [
    "soccer_fifa_world_cup",
    "soccer_sweden_allsvenskan",
    "soccer_norway_eliteserien",
    "soccer_brazil_campeonato",
    "soccer_usa_mls",
    "soccer_uefa_europa_league",
]


def _load_project_env() -> None:
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


def parse_sport_keys(value: str) -> list[str]:
    if not value.strip():
        return DEFAULT_SPORT_KEYS
    keys = [item.strip() for item in value.split(",") if item.strip()]
    return keys or DEFAULT_SPORT_KEYS


def _empty_odds() -> pd.DataFrame:
    return odds_payload_to_frame([])


def _empty_summary() -> pd.DataFrame:
    return summarize_odds_frame(pd.DataFrame())


def _safe_error_message(exc: Exception, api_key: str) -> str:
    message = str(exc)
    return message.replace(api_key, "***") if api_key else message


def import_multi_sport_odds(
    *,
    output_dir: Path,
    api_key: str,
    sport_keys: list[str],
    regions: str,
    markets: str,
    bookmakers: str,
    timeout: int,
    continue_on_error: bool = True,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    client = TheOddsApiClient(api_key=api_key, timeout=timeout)
    if not client.configured:
        _empty_odds().to_csv(output_dir / "odds.csv", index=False)
        _empty_summary().to_csv(output_dir / "match_market_summary.csv", index=False)
        return {
            "source": "the_odds_api",
            "configured": False,
            "status": "skipped",
            "reason": "THE_ODDS_API_KEY is not configured",
            "sport_keys": sport_keys,
            "output_dir": str(output_dir),
        }

    odds_frames: list[pd.DataFrame] = []
    sport_audits: list[dict[str, Any]] = []
    for sport_key in sport_keys:
        try:
            payload = fetch_odds(
                client,
                sport_key=sport_key,
                regions=regions,
                markets=markets,
                bookmakers=bookmakers,
            )
            odds = odds_payload_to_frame(payload)
            odds_frames.append(odds)
            sport_audits.append(
                {
                    "sport_key": sport_key,
                    "status": "ok",
                    "events": int(len(payload)),
                    "odds_rows": int(len(odds)),
                    "requests_remaining": client.last_headers.get("x-requests-remaining", ""),
                    "requests_used": client.last_headers.get("x-requests-used", ""),
                }
            )
        except Exception as exc:  # pragma: no cover - exercised through CLI/network conditions.
            sport_audits.append(
                {
                    "sport_key": sport_key,
                    "status": "error",
                    "error": _safe_error_message(exc, client.api_key),
                    "requests_remaining": client.last_headers.get("x-requests-remaining", ""),
                    "requests_used": client.last_headers.get("x-requests-used", ""),
                }
            )
            if not continue_on_error:
                raise

    odds_all = pd.concat(odds_frames, ignore_index=True, sort=False) if odds_frames else _empty_odds()
    summary_all = summarize_odds_frame(odds_all)
    odds_all.to_csv(output_dir / "odds.csv", index=False)
    summary_all.to_csv(output_dir / "match_market_summary.csv", index=False)

    return {
        "source": "the_odds_api",
        "configured": True,
        "status": "ok" if all(item["status"] == "ok" for item in sport_audits) else "partial",
        "sport_keys": sport_keys,
        "regions": regions,
        "markets": markets,
        "bookmakers": bookmakers,
        "sports": sport_audits,
        "events": int(sum(item.get("events", 0) for item in sport_audits)),
        "odds_rows": int(len(odds_all)),
        "summary_rows": int(len(summary_all)),
        "captured_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "output_dir": str(output_dir),
    }


def main() -> None:
    _load_project_env()
    parser = argparse.ArgumentParser(description="Import The Odds API odds for multiple football sport_keys.")
    parser.add_argument("--sport-keys", default=",".join(DEFAULT_SPORT_KEYS))
    parser.add_argument("--regions", default="eu,uk,us,au")
    parser.add_argument("--markets", default="h2h,spreads,totals")
    parser.add_argument("--bookmakers", default="")
    parser.add_argument("--api-key", default="", help="Defaults to THE_ODDS_API_KEY environment variable.")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--output-dir", default="data/external/the_odds_api_multi_sport")
    parser.add_argument("--audit-output", default="artifacts/data/the_odds_api_multi_sport_import.json")
    parser.add_argument("--fail-fast", action="store_true")
    args = parser.parse_args()

    audit = import_multi_sport_odds(
        output_dir=ROOT / args.output_dir,
        api_key=args.api_key or os.getenv("THE_ODDS_API_KEY", ""),
        sport_keys=parse_sport_keys(args.sport_keys),
        regions=args.regions,
        markets=args.markets,
        bookmakers=args.bookmakers,
        timeout=args.timeout,
        continue_on_error=not args.fail_fast,
    )
    audit_path = ROOT / args.audit_output
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
