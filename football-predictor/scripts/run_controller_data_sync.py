"""Stage-completion sync with a durable outbox. Never changes predictions or betting ledgers."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
TZ = timezone(timedelta(hours=8))
STEPS = {
    "snapshot": "/api/automation/sync-snapshot",
    "history": "/api/automation/persist-history",
    "controller": "/api/automation/sync",
    "market": "/api/automation/sync-market",
}
STAGES = {
    "confirm": ("snapshot", "market", "controller"),
    "analysis": ("snapshot", "history", "market", "controller"),
    "review": ("history", "controller"),
    "controller": ("controller",),
    "market": ("market",),
}
MOVEMENT_CSV = ROOT / "data/processed/handicap_market_movement_latest.csv"
ALIGNMENT_CSV = ROOT / "artifacts/data/inner_outer_market_alignment_latest.csv"


def save_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def admin_credentials(path: Path) -> dict:
    # Only these two values are needed. No shell expansion and no credential logging.
    values = {}
    allowed = {"WORKBENCH_ADMIN_USER", "WORKBENCH_ADMIN_PASSWORD"}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            key, separator, value = line.strip().removeprefix("export ").partition("=")
            key, value = key.strip(), value.strip()
            if separator and key in allowed:
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                else:
                    value = value.split(" #", 1)[0].rstrip()
                values[key] = value
    return {**values, **{k: os.environ[k] for k in allowed if k in os.environ}}


def enqueue(state: dict, days: list[str], stage: str, now: datetime) -> None:
    for day in sorted(set(days)):
        date.fromisoformat(day)
        for step in STAGES[stage]:
            key = f"{day}|{step}"
            previous = state["jobs"].get(key, {})
            state["jobs"][key] = {
                "sales_day": day, "step": step, "stage": stage,
                "status": "pending", "requested_at": now.isoformat(),
                "attempts": previous.get("attempts", 0), "next_retry_at": now.isoformat(),
            }


def frozen_review_export(day: str, root: Path = ROOT) -> dict:
    """Read existing ledger settlements; never settle, recalculate odds or modify source files."""
    groups, hashes = {}, {}
    for group, filename in (("real", "betting_plan_ledger.csv"), ("shadow", "fixed_odds_shadow_ledger.csv")):
        path = root / "data/manual" / filename
        if not path.exists():
            raise ValueError("missing_ledger")
        hashes[filename] = hashlib.sha256(path.read_bytes()).hexdigest()
        rows, ids = [], set()
        with path.open(encoding="utf-8-sig", newline="") as stream:
            for raw in csv.DictReader(stream, strict=True):
                if raw.get("date") != day:
                    continue
                if None in raw or any(value is None for value in raw.values()):
                    raise ValueError("malformed_ledger_row")
                if not raw.get("plan_id") or raw["plan_id"] in ids:
                    raise ValueError("duplicate_or_missing_plan_id")
                ids.add(raw["plan_id"])
                row = dict(raw)
                for key in ("stake", "payout", "net_profit", "roi"):
                    value = raw.get(key, "").strip()
                    row[key] = float(value) if value else None
                    if row[key] is not None and not math.isfinite(row[key]):
                        raise ValueError("invalid_ledger_number")
                row["legs"] = raw.get("selections", "")
                rows.append(row)
        groups[group] = rows
    settled = [r for r in groups["real"] if r["result"] in {"命中", "未中"}]
    if any(r[k] is None for r in settled for k in ("stake", "payout", "net_profit")):
        raise ValueError("incomplete_settlement")
    stake = sum(r["stake"] for r in settled)
    payout = sum(r["payout"] for r in settled)
    net = sum(r["net_profit"] for r in settled)
    return {"sales_day": day, "reviewed_at": None, "source": "frozen_local_ledgers",
            "source_sha256": hashes, "status": "no_records" if not groups["real"] and not groups["shadow"] else ("completed" if len(settled) == len(groups["real"]) else "partial"),
            "real_summary": {"plans": len(settled), "hits": sum(r["result"] == "命中" for r in settled),
                             "misses": sum(r["result"] == "未中" for r in settled), "stake": stake,
                             "payout": payout, "net_profit": net, "roi": net / stake if stake else None},
            "real_plans": groups["real"], "fixed_odds_shadow": {"plans": groups["shadow"]}}


def read_csv_rows(path: Path) -> list[dict]:
    """Read a latest-features CSV as plain string rows; missing files return an empty list."""
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return [dict(row) for row in csv.DictReader(stream)]


def market_payload(day: str) -> dict:
    """Movement/alignment rows are matched to fixtures server-side; empty files are not an error."""
    return {
        "sales_day": day,
        "movement_rows": read_csv_rows(MOVEMENT_CSV),
        "alignment_rows": read_csv_rows(ALIGNMENT_CSV),
        "source_note": "handicap_market_movement_latest.csv+inner_outer_market_alignment_latest.csv",
    }


def attempt(session, base_url: str, job: dict) -> dict:
    step, day = job["step"], job["sales_day"]
    if step == "snapshot":
        body = {"date": day}
    elif step == "market":
        body = market_payload(day)
    else:
        body = {"sales_days": [day]}
    if step == "history":
        try:
            body["review_export"] = frozen_review_export(day)
        except (OSError, ValueError, csv.Error):
            return {"ok": False, "http_status": None, "reason": "invalid_local_ledger_export", "request_attempts": 0}
    for number in range(2):
        try:
            response = session.post(base_url + STEPS[step], json=body, timeout=(3, 45), allow_redirects=False)
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            verified = response.ok and isinstance(payload, dict) and payload.get("verified") is True
            result = {"ok": verified, "http_status": response.status_code,
                      "reason": "verified" if verified else "write_or_readback_unverified",
                      "request_attempts": number + 1}
            # Preserve only our safe machine diagnostic; never store upstream response bodies.
            error = payload.get("error", "") if isinstance(payload, dict) else ""
            if isinstance(error, str) and error.startswith("readback_mismatch:"):
                result["reason"] = error
            if verified:
                result["counts"] = {key: payload[key] for key in (
                    "persisted_fixtures", "snapshotted", "persisted_review_summaries",
                    "persisted_review_plans", "persisted_analysis_runs", "persisted_market_intel",
                ) if isinstance(payload.get(key), int)}
                result["flags"] = {key: payload[key] for key in ("no_matches", "no_frozen_predictions") if key in payload}
            if verified or response.status_code not in {429, 500, 502, 503, 504}:
                return result
        except requests.RequestException:
            result = {"ok": False, "http_status": None, "reason": "connection_or_timeout",
                      "request_attempts": number + 1}
    return result


def run_pending(state: dict, session, base_url: str, now: datetime, persist, max_jobs: int = 6) -> list[dict]:
    results = []
    started = time.monotonic()
    for key, job in state["jobs"].items():
        if len(results) >= max_jobs or time.monotonic() - started >= 120:
            break
        if job["status"] == "completed" or datetime.fromisoformat(job["next_retry_at"]) > now:
            continue
        result = attempt(session, base_url, job)
        job["attempts"] += result["request_attempts"]
        job["status"] = "completed" if result["ok"] else "pending"
        job["last_attempt_at"] = now.isoformat()
        job["last_result"] = result
        delay = timedelta(days=1) if result["http_status"] in {401, 403} else timedelta(minutes=30)
        job["next_retry_at"] = (now + delay).isoformat()
        results.append({"key": key, **result})
        persist(state)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sales-day", action="append", default=[])
    parser.add_argument("--stage", choices=STAGES)
    parser.add_argument("--retry-pending", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-jobs", type=int, default=6)
    parser.add_argument("--base-url", default="http://127.0.0.1:3000")
    parser.add_argument("--state-dir", type=Path, default=ROOT / "artifacts/data/controller_sync")
    args = parser.parse_args()
    if bool(args.sales_day) != bool(args.stage) or not (args.stage or args.retry_pending):
        parser.error("use --stage with --sales-day, or --retry-pending")
    if not 1 <= args.max_jobs <= 20:
        parser.error("--max-jobs must be between 1 and 20")
    parsed = urlparse(args.base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        parser.error("only a local loopback Web service is allowed")
    for day in args.sales_day:
        try:
            if date.fromisoformat(day).isoformat() != day:
                raise ValueError(day)
        except ValueError:
            parser.error("sales-day must be YYYY-MM-DD")
    state_path = args.state_dir / "outbox.json"
    now = datetime.now(TZ)
    if args.dry_run:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"jobs": {}}
        if args.stage:
            enqueue(state, args.sales_day, args.stage, now)
        print(json.dumps({"dry_run": True, "pending_keys": [k for k, j in state["jobs"].items() if j["status"] != "completed"]}, ensure_ascii=False))
        return 0
    args.state_dir.mkdir(parents=True, exist_ok=True)
    lock = args.state_dir / "writer.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print("sync_writer_busy: retry this stage later; no work was acknowledged")
        return 2
    try:
        os.close(descriptor)
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"schema_version": 1, "jobs": {}}
        if args.stage:
            enqueue(state, args.sales_day, args.stage, now)
        save_json(state_path, state)  # Durable intent before the first request.
        session = requests.Session()
        session.trust_env = False  # Never send loopback credentials through an ambient proxy.
        credentials = admin_credentials(ROOT.parent / "web/.env.local")
        user, password = credentials.get("WORKBENCH_ADMIN_USER"), credentials.get("WORKBENCH_ADMIN_PASSWORD")
        if user and password:
            session.auth = (user, password)
        ledger_paths = [ROOT / "data/manual" / name for name in ("betting_plan_ledger.csv", "fixed_odds_shadow_ledger.csv")]
        def ledger_hashes():
            return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None for p in ledger_paths}
        before = ledger_hashes()
        results = run_pending(state, session, args.base_url.rstrip("/"), now,
                              lambda value: save_json(state_path, value), args.max_jobs)
        pending = [k for k, j in state["jobs"].items() if j["status"] != "completed"]
        audit = {"at": now.isoformat(), "results": results, "pending_keys": pending,
                 "ok": not pending, "production_ledger_unchanged": before == ledger_hashes(),
                 "source_ledger_sha256": before}
        save_json(args.state_dir / f"run_{now:%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}.json", audit)
        save_json(args.state_dir / "latest.json", audit)
        print(json.dumps(audit, ensure_ascii=False, indent=2))
        return 1 if pending else 0
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
