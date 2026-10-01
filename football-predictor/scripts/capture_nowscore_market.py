"""Capture Nowscore pages and build source-specific shadow market history."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from data.api_football_odds_snapshot import SNAPSHOT_COLUMNS  # noqa: E402
from data.nowscore_market import align_cp_to_scan, parse_cp_page, parse_odds_page, to_outer_rows  # noqa: E402


def _read_html(path: Path | None, url: str, session: requests.Session) -> bytes:
    if path is not None:
        return path.read_bytes()
    response = session.get(url, timeout=(3, 10))
    response.raise_for_status()
    return response.content


def _archive(path: Path, content: bytes) -> str:
    digest = hashlib.sha256(content).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != content:
        raise RuntimeError(f"raw archive collision: {path}")
    if not path.exists():
        path.write_bytes(content)
    return digest


def _csv(path: Path, rows: list[dict], columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = columns or list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def capture(scan: Path | dict[str, Any], output_root: Path, cp_html: Path | None = None,
            odds_html_dir: Path | None = None, max_matches: int = 100,
            max_duration_seconds: int = 90) -> dict:
    source = scan if isinstance(scan, dict) else json.loads(scan.read_text(encoding="utf-8-sig"))
    sales_day = str(source["sales_day"])
    started = time.monotonic()
    captured = datetime.now(timezone.utc)
    stamp = captured.strftime("%Y%m%dT%H%M%S%fZ")
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; MatchResearch/1.0)",
                            "Accept-Language": "zh-CN,zh;q=0.9",
                            "Cache-Control": "no-cache", "Pragma": "no-cache"})
    cp_bytes = _read_html(cp_html, "https://cp.nowscore.com/", session)
    cp_day, cp_rows = parse_cp_page(cp_bytes.decode("utf-8-sig", errors="replace"))
    cp_days = sorted({str(row.get("sales_day") or "") for row in cp_rows if row.get("sales_day")})
    if sales_day not in cp_days:
        raise ValueError(
            f"sales day missing: scan={sales_day}, cp_days={','.join(cp_days) or cp_day}; no output written"
        )
    snapshot = output_root / "snapshots" / f"{sales_day}_{stamp}"
    _archive(snapshot / "raw" / "cp.html", cp_bytes)
    aligned = align_cp_to_scan(cp_rows, source.get("fixtures", []), sales_day)
    mapped = sorted(
        (item for item in aligned if item["mapping_status"] == "mapped"
         and item.get("sale_status") == "on_sale"
         and datetime.fromisoformat(str(item["kickoff"])) > datetime.now(timezone.utc)),
        key=lambda item: item["kickoff"],
    )[:max_matches]
    quotes, outer, failures = [], [], []
    for item in mapped:
        if time.monotonic() - started >= max_duration_seconds:
            failures.append({"match_id": item["match_id"], "reason": "time_budget_exceeded"})
            break
        match_id = item["nowscore_match_id"]
        local = odds_html_dir / f"{match_id}.html" if odds_html_dir else None
        try:
            raw = _read_html(local, item["nowscore_odds_url"], session)
            quote_captured_at = datetime.now(timezone.utc)
            raw_path = snapshot / "raw" / f"{match_id}.html"
            digest = _archive(raw_path, raw)
            parsed = parse_odds_page(raw.decode("utf-8-sig", errors="replace"), match_id)
            if not parsed:
                raise ValueError("no bookmaker quote rows")
            quotes.extend([{**item_quote, "match_id": item["match_id"],
                            "captured_at": quote_captured_at.isoformat(), "raw_sha256": digest} for item_quote in parsed])
            outer.extend(to_outer_rows(parsed, item, quote_captured_at, digest, str(raw_path.resolve()),
                                       source_time_verified=local is None))
        except (OSError, requests.RequestException, ValueError) as exc:
            failures.append({"match_id": item["match_id"], "nowscore_match_id": match_id,
                             "reason": type(exc).__name__, "detail": str(exc)[:180]})
    _csv(snapshot / "alignment.csv", aligned)
    _csv(snapshot / "quotes.csv", quotes)
    _csv(snapshot / "outer_market.csv", outer, SNAPSHOT_COLUMNS)
    audit = {"source": "nowscore", "sales_day": sales_day, "captured_at": captured.isoformat(),
             "snapshot_dir": str(snapshot.resolve()), "scan_path": str(scan.resolve()) if isinstance(scan, Path) else "inline_scan",
             "scan_fixture_count": len(source.get("fixtures", [])), "cp_fixture_count": len(cp_rows),
             "cp_sales_days": cp_days, "selected_sales_day": sales_day,
             "eligible_on_sale_matches": len(mapped),
             "mapped_count": sum(x["mapping_status"] == "mapped" for x in aligned),
             "captured_match_count": len({x["match_id"] for x in quotes}),
             "quote_rows": len(quotes), "asian_outer_rows": len(outer),
             "research_eligible_rows": sum(bool(x["eligible_for_research"]) for x in outer),
             "failures": failures, "status": "complete" if not failures and len({x["match_id"] for x in quotes}) == len(mapped) else ("no_eligible_fixtures" if not mapped else "partial")}
    (snapshot / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return audit


FALLBACK_STATUSES = {
    "quota_insufficient", "no_routed_sports", "not_configured",
    "source_failed", "unmatched", "partial",
}


def effective_external_status(primary_audit: dict[str, Any], fallback_audit: dict[str, Any]) -> dict[str, Any]:
    captured = int(fallback_audit.get("captured_match_count") or 0)
    eligible = int(fallback_audit.get("research_eligible_rows") or 0)
    available = fallback_audit.get("status") in {"complete", "partial"} and captured > 0 and eligible > 0
    return {
        "primary_status": str(primary_audit.get("status") or ""),
        "effective_status": "available_via_nowscore" if available else str(primary_audit.get("status") or ""),
        "effective_source": "nowscore" if available else "the_odds_api",
        "external_data_available": available,
        "captured_fixtures": captured,
        "research_eligible_rows": eligible,
        "production_model_feature_ready": False,
    }


def capture_on_external_failure(scan: dict[str, Any], external_audit: dict[str, Any],
                                output_root: Path = ROOT / "data/external/nowscore") -> dict[str, Any]:
    """Use the bounded fallback when the primary source cannot cover every confirmed fixture."""
    primary_status = str(external_audit.get("status") or "")
    if primary_status not in FALLBACK_STATUSES:
        return {"source": "nowscore", "status": "not_triggered",
                "reason": "the_odds_api_status_does_not_require_fallback",
                "trigger_status": primary_status}
    try:
        result = capture(scan, output_root)
        result["trigger_status"] = primary_status
        return result
    except Exception as exc:
        return {"source": "nowscore", "status": "source_failed", "reason": type(exc).__name__,
                "detail": str(exc)[:180], "sales_day": scan.get("sales_day", ""),
                "trigger_status": primary_status}


def capture_on_quota_failure(scan: dict[str, Any], external_audit: dict[str, Any],
                             output_root: Path = ROOT / "data/external/nowscore") -> dict[str, Any]:
    """Backward-compatible alias for callers created before broader fallback routing."""
    return capture_on_external_failure(scan, external_audit, output_root)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan-json", type=Path, default=ROOT / "artifacts/data/sporttery_sales_window_scan_latest_confirm.json")
    parser.add_argument("--output-root", type=Path, default=ROOT / "data/external/nowscore")
    parser.add_argument("--cp-html", type=Path, help="Use a saved HTML page instead of network")
    parser.add_argument("--odds-html-dir", type=Path, help="Directory of <nowscore_match_id>.html files")
    parser.add_argument("--max-matches", type=int, default=100)
    args = parser.parse_args()
    if args.max_matches < 1:
        parser.error("--max-matches must be positive")
    result = capture(args.scan_json, args.output_root, args.cp_html, args.odds_html_dir, args.max_matches)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
