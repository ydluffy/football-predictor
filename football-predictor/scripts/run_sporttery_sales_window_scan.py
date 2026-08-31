from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from strategy.sporttery_sales_window import (  # noqa: E402
    CHINA_TZ,
    apply_task_status,
    build_scan_result,
    confirmation_open_at,
    load_registry,
    parse_china_datetime,
    read_csv_rows,
    render_scan_markdown,
    retryable_tasks,
    save_registry,
    upsert_registry_tasks,
)
from data.sporttery_snapshot_archive import archive_sporttery_scan_inputs  # noqa: E402
from data.the_odds_sporttery import (  # noqa: E402
    capture_sporttery_the_odds_snapshot,
    load_project_env,
)
from data.unified_outer_market_history import build_unified_histories  # noqa: E402
from world_cup.sporttery_markets import parse_lottery_gov_spf_text  # noqa: E402
from world_cup.sporttery_play_odds import (  # noqa: E402
    parse_lottery_gov_correct_score_text,
    parse_lottery_gov_half_full_time_text,
    parse_lottery_gov_total_goals_text,
)


OFFICIAL_URLS = {
    "spf_rqspf": "https://www.lottery.gov.cn/jc/jsq/zqspf/",
    "total_goals": "https://www.lottery.gov.cn/jc/jsq/zqzjq/",
    "correct_score": "https://www.lottery.gov.cn/jc/jsq/zqbf/",
    "half_full_time": "https://www.lottery.gov.cn/jc/jsq/zqbqc/",
}


def project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def load_json(path: str | Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    source = project_path(path)
    if not source.exists():
        return None
    return json.loads(source.read_text(encoding="utf-8"))


def fetch_official_sources(*, captured_at: datetime, stage: str, channel: str, timeout: int) -> dict[str, Any]:
    stamp = captured_at.strftime("%Y-%m-%d_%H%M")
    raw_dir = ROOT / "artifacts" / "data"
    manual_dir = ROOT / "data" / "manual"
    raw_dir.mkdir(parents=True, exist_ok=True)
    manual_dir.mkdir(parents=True, exist_ok=True)
    raw_paths: dict[str, Path] = {}
    fetches: dict[str, Any] = {}
    errors: list[str] = []
    for play, url in OFFICIAL_URLS.items():
        raw_path = raw_dir / f"lottery_gov_{play}_{stamp}.txt"
        raw_paths[play] = raw_path
        command = [
            "node",
            str(ROOT / "scripts" / "fetch_lottery_gov_spf.mjs"),
            "--url",
            url,
            "--output",
            str(raw_path),
            "--channel",
            channel,
            "--timeout",
            str(timeout),
            "--no-wait-text",
            "--expand-all",
        ]
        proc = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if proc.returncode:
            errors.append(f"{play}: {proc.stderr.strip() or proc.stdout.strip()}")
            fetches[play] = {"ok": False, "returncode": proc.returncode}
            continue
        try:
            fetches[play] = json.loads(proc.stdout)
        except json.JSONDecodeError:
            fetches[play] = {"ok": True, "stdout": proc.stdout.strip()}

    captured = captured_at.isoformat()
    official = pd.DataFrame()
    if raw_paths.get("spf_rqspf", Path()).exists():
        official = parse_lottery_gov_spf_text(
            raw_paths["spf_rqspf"].read_text(encoding="utf-8"),
            updated_at=captured,
        )
    official_path = manual_dir / f"sporttery_handicap_markets_{stamp}_{stage}.csv"
    official.to_csv(official_path, index=False, encoding="utf-8-sig")

    play_frames: list[pd.DataFrame] = []
    parsers = {
        "total_goals": parse_lottery_gov_total_goals_text,
        "correct_score": parse_lottery_gov_correct_score_text,
        "half_full_time": parse_lottery_gov_half_full_time_text,
    }
    for play, parser in parsers.items():
        raw_path = raw_paths.get(play)
        if raw_path and raw_path.exists():
            play_frames.append(
                parser(
                    raw_path.read_text(encoding="utf-8"),
                    snapshot_type=stage,
                    captured_at=captured,
                )
            )
    play_odds = pd.concat(play_frames, ignore_index=True) if play_frames else pd.DataFrame()
    play_path = manual_dir / f"sporttery_play_odds_{stamp}_{stage}.csv"
    play_odds.to_csv(play_path, index=False, encoding="utf-8-sig")
    return {
        "official_markets": official_path,
        "play_odds": play_path,
        "fetches": fetches,
        "errors": errors,
        "raw_paths": {key: str(value) for key, value in raw_paths.items()},
    }


def default_registry_path(sales_day: str) -> Path:
    return ROOT / "artifacts" / "data" / f"sporttery_task_registry_{sales_day}.json"


def write_scan_outputs(
    scan: dict[str, Any],
    *,
    queue: list[dict[str, Any]],
    registry_path: Path,
    sources: dict[str, Any],
) -> dict[str, str]:
    current = parse_china_datetime(scan["scanned_at"])
    stamp = current.strftime("%Y-%m-%d_%H%M")
    base = f"sporttery_sales_window_scan_{stamp}_{scan['stage']}"
    data_dir = ROOT / "artifacts" / "data"
    betting_dir = ROOT / "artifacts" / "betting"
    data_dir.mkdir(parents=True, exist_ok=True)
    betting_dir.mkdir(parents=True, exist_ok=True)
    json_path = data_dir / f"{base}.json"
    md_path = betting_dir / f"{base}.md"
    scan["task_registry"] = str(registry_path.relative_to(ROOT))
    scan["task_queue"] = queue
    scan["sources"] = sources
    json_path.write_text(json.dumps(scan, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_scan_markdown(scan, queue), encoding="utf-8")
    (data_dir / f"sporttery_sales_window_scan_latest_{scan['stage']}.json").write_text(
        json.dumps(scan, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (betting_dir / f"sporttery_sales_window_scan_latest_{scan['stage']}.md").write_text(
        render_scan_markdown(scan, queue), encoding="utf-8"
    )
    return {"json": str(json_path), "markdown": str(md_path), "registry": str(registry_path)}


def scan_command(args: argparse.Namespace) -> int:
    current = parse_china_datetime(args.as_of or datetime.now(CHINA_TZ))
    sales_day = args.sales_day or current.date().isoformat()
    if args.stage == "confirm" and current < confirmation_open_at(date.fromisoformat(sales_day)):
        raise SystemExit(
            f"confirm stage opens at {confirmation_open_at(date.fromisoformat(sales_day)).isoformat()}; "
            f"received {current.isoformat()}"
        )
    sources: dict[str, Any] = {}
    if args.fetch:
        fetched = fetch_official_sources(
            captured_at=current,
            stage=args.stage,
            channel=args.channel,
            timeout=args.timeout,
        )
        official_path = fetched["official_markets"]
        play_path = fetched["play_odds"]
        sources = {
            "mode": "live_fetch",
            "official_markets": str(official_path),
            "play_odds": str(play_path),
            "fetches": fetched["fetches"],
            "errors": fetched["errors"],
            "raw_paths": fetched["raw_paths"],
        }
        fetch_audit_path = ROOT / "artifacts" / "data" / (
            f"sporttery_official_fetch_audit_{current.strftime('%Y-%m-%d_%H%M')}_{args.stage}.json"
        )
        fetch_audit = {
            "schema_version": 1,
            "sales_day": sales_day,
            "stage": args.stage,
            "captured_at": current.isoformat(),
            "status": "source_failed" if fetched["errors"] else "fetched",
            "fetches": fetched["fetches"],
            "errors": fetched["errors"],
            "raw_paths": fetched["raw_paths"],
            "official_markets": str(official_path),
            "play_odds": str(play_path),
        }
        fetch_audit_path.write_text(
            json.dumps(fetch_audit, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        sources["fetch_audit"] = str(fetch_audit_path)
    else:
        if not args.official_markets or not args.play_odds:
            raise SystemExit("scan without --fetch requires --official-markets and --play-odds")
        official_path = project_path(args.official_markets)
        play_path = project_path(args.play_odds)
        sources = {
            "mode": "provided_files",
            "official_markets": str(official_path),
            "play_odds": str(play_path),
        }
    previous_scan = load_json(args.previous_scan)
    ledger_path = project_path(args.ledger)
    scan = build_scan_result(
        stage=args.stage,
        as_of=current,
        sales_day=sales_day,
        official_rows=read_csv_rows(official_path),
        play_rows=read_csv_rows(play_path),
        previous_scan=previous_scan,
        stopped_match_numbers={value.strip() for value in args.stopped_match_numbers.split(",") if value.strip()},
        ledger_path=ledger_path,
        source_ok=not bool(sources.get("errors")),
    )
    if args.stage == "confirm" and args.the_odds_mode != "off":
        load_project_env()
        external_audit = capture_sporttery_the_odds_snapshot(
            scan=scan,
            snapshot_root=ROOT / "data" / "external" / "the_odds_api_sporttery" / "snapshots",
            api_key=os.getenv("THE_ODDS_API_KEY", ""),
            snapshot_type="confirm",
            regions=args.the_odds_regions,
            markets=args.the_odds_markets,
            bookmakers=args.the_odds_bookmakers,
            timeout=args.the_odds_timeout,
            kickoff_tolerance_minutes=args.the_odds_kickoff_tolerance_minutes,
        )
        unified_outer, unified_model, unified_audit = build_unified_histories(
            api_football_history=ROOT / "data" / "external" / "api_football_odds" / "history.csv",
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
        external_audit["unified_history"] = unified_audit
        latest_external = ROOT / "artifacts" / "data" / "the_odds_api_sporttery_latest.json"
        latest_external.parent.mkdir(parents=True, exist_ok=True)
        latest_external.write_text(
            json.dumps(external_audit, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        scan["external_odds"] = {
            "source": "the_odds_api",
            "status": external_audit["status"],
            "snapshot_type": "confirm",
            "snapshot_dir": external_audit["snapshot_dir"],
            "on_sale_fixtures": external_audit["on_sale_fixtures"],
            "mapped_fixtures": external_audit["mapped_fixtures"],
            "unmatched_fixtures": external_audit["unmatched_fixtures"],
            "refresh_required_at_final": True,
            "ledger_authority": False,
        }
        sources["the_odds_api"] = external_audit
        for task in scan.get("planned_tasks", []):
            task["external_odds_policy"] = "refresh_at_final"
            task["confirm_snapshot_status"] = external_audit["status"]
        if args.the_odds_mode == "required" and external_audit["status"] != "complete":
            scan["external_odds"]["required_gate_passed"] = False
            scan["external_odds"]["required_gate_reason"] = (
                "The Odds API confirmation snapshot is incomplete; final analysis must retry or downgrade."
            )
    snapshot_archive = archive_sporttery_scan_inputs(
        official_markets_path=official_path,
        play_odds_path=play_path,
        scan=scan,
        archive_root=ROOT / "data" / "external" / "sporttery" / "snapshots",
        index_path=ROOT / "data" / "manual" / "sporttery_snapshot_index.csv",
    )
    sources["snapshot_archive"] = snapshot_archive
    registry_path = project_path(args.registry) if args.registry else default_registry_path(sales_day)
    registry = load_registry(registry_path, sales_day=date.fromisoformat(sales_day))
    queue: list[dict[str, Any]] = []
    if args.stage == "confirm":
        registry, queue = upsert_registry_tasks(registry, scan["planned_tasks"], as_of=current)
        save_registry(registry_path, registry)
    outputs = write_scan_outputs(scan, queue=queue, registry_path=registry_path, sources=sources)
    print(json.dumps({"scan": scan, "outputs": outputs}, ensure_ascii=False, indent=2))
    return 0


def task_status_command(args: argparse.Namespace) -> int:
    current = parse_china_datetime(args.as_of or datetime.now(CHINA_TZ))
    path = project_path(args.registry) if args.registry else default_registry_path(args.sales_day)
    registry = load_registry(path, sales_day=current.date())
    registry = apply_task_status(
        registry,
        key=args.key,
        status=args.status,
        as_of=current,
        automation_id=args.automation_id or None,
        error=args.error or None,
    )
    save_registry(path, registry)
    print(json.dumps(registry, ensure_ascii=False, indent=2))
    return 0


def retry_command(args: argparse.Namespace) -> int:
    current = parse_china_datetime(args.as_of or datetime.now(CHINA_TZ))
    path = project_path(args.registry) if args.registry else default_registry_path(args.sales_day)
    registry = load_registry(path, sales_day=date.fromisoformat(args.sales_day))
    queue = retryable_tasks(registry, as_of=current)
    print(json.dumps({"registry": str(path), "retry_queue": queue}, ensure_ascii=False, indent=2))
    return 0 if not queue else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified Sporttery pre-scan, on-sale confirmation, and task registry.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    scan = subparsers.add_parser("scan")
    scan.add_argument("--stage", choices=["preopen", "confirm"], required=True)
    scan.add_argument("--as-of", default="")
    scan.add_argument("--sales-day", default="")
    scan.add_argument("--fetch", action="store_true")
    scan.add_argument("--official-markets", default="")
    scan.add_argument("--play-odds", default="")
    scan.add_argument("--previous-scan", default="")
    scan.add_argument("--registry", default="")
    scan.add_argument("--stopped-match-numbers", default="")
    scan.add_argument("--ledger", default="data/manual/betting_plan_ledger.csv")
    scan.add_argument("--channel", default="chrome")
    scan.add_argument("--timeout", type=int, default=60000)
    scan.add_argument("--the-odds-mode", choices=["auto", "off", "required"], default="auto")
    scan.add_argument("--the-odds-regions", default="eu,uk,us,au")
    scan.add_argument("--the-odds-markets", default="h2h,spreads,totals")
    scan.add_argument("--the-odds-bookmakers", default="")
    scan.add_argument("--the-odds-timeout", type=int, default=60)
    scan.add_argument("--the-odds-kickoff-tolerance-minutes", type=int, default=180)
    scan.set_defaults(func=scan_command)

    task = subparsers.add_parser("task-status")
    task.add_argument("--sales-day", required=True)
    task.add_argument("--registry", default="")
    task.add_argument("--key", required=True)
    task.add_argument("--status", choices=sorted({"scheduled", "updated", "completed", "pending_schedule", "failed"}), required=True)
    task.add_argument("--automation-id", default="")
    task.add_argument("--error", default="")
    task.add_argument("--as-of", default="")
    task.set_defaults(func=task_status_command)

    retry = subparsers.add_parser("retry")
    retry.add_argument("--sales-day", required=True)
    retry.add_argument("--registry", default="")
    retry.add_argument("--as-of", default="")
    retry.set_defaults(func=retry_command)
    return parser


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
