"""Stage-completion sync with a durable outbox. Never changes predictions or betting ledgers."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT.parent / "web"
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
NOWSCORE_SNAPSHOT_ROOT = ROOT / "data/external/nowscore/snapshots"
# 两个 latest 别名由构建器单独刷新，同步链路本身不会重建它们；--rebuild-market 用这两个入口。
MARKET_ARTIFACT_BUILDERS = (
    "scripts/build_handicap_market_movement_features.py",
    "scripts/audit_inner_outer_market_alignment.py",
)
HEALTH_STEP = "/api/automation/sync-health"
# 只允许回环；用 node 直起 next 会得到一个单进程服务，结束时能精确回收，不留 npx 子进程。
NODE_BIN = shutil.which("node") or "node"
NEXT_BIN = WEB_ROOT / "node_modules/next/dist/bin/next"
# 自拉起必须用独立端口：本机 3000 的 IPv4 常被其它项目占用，而 3000 的 localhost 解析又取决于监听地址。
WEB_PORT = 3100
DEFAULT_BASE_URL = f"http://127.0.0.1:{WEB_PORT}"


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


def web_service_ready(base_url: str, timeout: float = 2.5) -> bool:
    """探活本地 Web：必须确认是本项目的 Next 应用，而不是同端口上的别的服务。

    只看状态码会把别的项目误判成"就绪"（本机 3000 的 IPv4 曾由另一项目的前端占用，
    其 404 响应满足了 status_code < 500），随后所有同步请求都会打到错误的服务上。
    /api/status 是本项目专用的环境自检接口，用它同时校验响应形状。
    """
    try:
        with requests.Session() as probe:
            probe.trust_env = False  # 与同步请求一致：回环不经过环境代理
            response = probe.get(base_url + "/api/status", timeout=timeout, allow_redirects=False)
        if not response.ok:
            return False
        payload = response.json()
    except (requests.RequestException, ValueError):
        return False
    return isinstance(payload, dict) and isinstance(payload.get("env"), dict) and "supabase" in payload


def spawn_web_service(port: int, log_path: Path, spawner=subprocess.Popen):
    """拉起本地写入服务。

    必须是开发模式：生产模式下 localArtifactsEnabled() 恒为 false，/api/automation/* 会全部 503，
    读写本地产物的步骤（snapshot/history/controller）根本无法工作。
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log:
        return spawner([NODE_BIN, str(NEXT_BIN), "dev", "-p", str(port)], cwd=str(WEB_ROOT),
                       stdout=log, stderr=subprocess.STDOUT)


def stop_web_service(process) -> None:
    """只回收本进程拉起的 Web；手动启动的实例绝不由脚本关闭。"""
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def ensure_web_service(base_url: str, port: int, log_path: Path, timeout: float = 180.0,
                       probe=web_service_ready, spawn=spawn_web_service,
                       sleeper=time.sleep) -> tuple[bool, object | None, list[str]]:
    """服务已在运行就复用（且绝不关闭）；未就绪才自拉起一个由本次同步负责回收的实例。

    超时即如实返回未就绪，队列保持待同步，不假装网页已更新。
    """
    actions: list[str] = []
    if probe(base_url):
        return True, None, actions
    try:
        process = spawn(port, log_path)
    except OSError as error:
        return False, None, [f"web_start_failed:{error}"]
    actions.append(f"started_web:{port}")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if probe(base_url):
            return True, process, actions
        sleeper(2)
    stop_web_service(process)
    return False, None, [*actions, "web_start_timeout"]


def health_snapshot(now: datetime, stage: str | None, days: list[str], results: list[dict],
                    pending: list[str], web_actions: list[str]) -> dict:
    """网页端只读展示所需的同步健康度；细节仍以本地 run_*.json 审计为准。"""
    return {
        "at": now.isoformat(),
        "ok": not pending,
        "stage": stage,
        "sales_days": sorted(set(days)),
        "pending_keys": pending,
        "pending_count": len(pending),
        "web_actions": web_actions,
        "web_started_by_sync": any(action.startswith("started_web:") for action in web_actions),
        "last_failure_reason": next((r["reason"] for r in reversed(results) if not r["ok"]), None),
        "steps": [{"key": r["key"], "step": r.get("step"), "ok": r["ok"], "reason": r.get("reason"),
                   "http_status": r.get("http_status")} for r in results],
    }


def report_health(session, base_url: str, run: dict) -> bool:
    """把本次同步结果写回网页端；失败只影响健康度展示，绝不改变同步结论。"""
    try:
        response = session.post(base_url + HEALTH_STEP, json={"run": run}, timeout=(3, 15), allow_redirects=False)
        return response.ok
    except requests.RequestException:
        return False


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


def price_change_rows(day: str) -> list[dict]:
    """Latest Nowscore price-change history for one sales day; no capture yet is not an error."""
    snapshots = sorted(NOWSCORE_SNAPSHOT_ROOT.glob(f"{day}_*/price_changes.csv"))
    if not snapshots:
        return []
    return [row for row in read_csv_rows(snapshots[-1]) if (row.get("odds_id") or "").strip()]


def market_payload(day: str) -> dict:
    """Only the requested sales day's rows are sent: the server matches rows against that day's fixtures.

    Both artifacts are append-only `latest` files; shipping every historical day would send megabytes
    per request and turn the unmatched counters into noise instead of a signal.
    """
    return {
        "sales_day": day,
        "movement_rows": [row for row in read_csv_rows(MOVEMENT_CSV)
                          if row.get("match_id", "").startswith(f"{day}|")],
        "alignment_rows": [row for row in read_csv_rows(ALIGNMENT_CSV) if row.get("sales_day") == day],
        "price_change_rows": price_change_rows(day),
        "source_note": "handicap_market_movement_latest.csv+inner_outer_market_alignment_latest.csv"
                       "+nowscore snapshots/<day>_*/price_changes.csv",
    }


def market_artifact_coverage(day: str) -> dict:
    """Report the newest sales day each market artifact actually covers.

    Both builders write fixed `latest` aliases that no sync step refreshes, so a stale
    artifact would match no fixture and still be acknowledged as a verified sync.
    """
    movement_days = {row["match_id"].split("|", 1)[0] for row in read_csv_rows(MOVEMENT_CSV)
                     if "|" in row.get("match_id", "")}
    alignment_days = {row["sales_day"] for row in read_csv_rows(ALIGNMENT_CSV) if row.get("sales_day")}
    newest = {"movement": max(movement_days, default=""), "alignment": max(alignment_days, default="")}
    return {"newest_day": newest, "stale": [name for name, value in newest.items() if value and value < day]}


def market_rows_unmatched(payload: dict) -> bool:
    """Artifacts that match no fixture of the day mean the day was not really published."""
    received = int(payload.get("movement_rows_received") or 0) + int(payload.get("alignment_rows_received") or 0)
    matched = int(payload.get("matched_movement") or 0) + int(payload.get("matched_alignment") or 0)
    return received > 0 and matched == 0


def rebuild_market_artifacts(runner=subprocess.run) -> list[str]:
    """Regenerate both latest aliases from the current local inputs before syncing."""
    for script in MARKET_ARTIFACT_BUILDERS:
        runner([sys.executable, str(ROOT / script)], check=True, cwd=str(ROOT))
    return list(MARKET_ARTIFACT_BUILDERS)


def step_timeout(step: str) -> tuple[float, float]:
    """market 步骤逐行做读回校验，滑点多的销售日单次请求实测可达 ~80s。

    统一用 45s 读超时会让这类大销售日永远停在待同步（数据其实还没写完就被判超时）。
    """
    return (3.0, 180.0 if step == "market" else 45.0)


def attempt(session, base_url: str, job: dict) -> dict:
    step, day = job["step"], job["sales_day"]
    if step == "snapshot":
        body = {"date": day}
    elif step == "market":
        coverage = market_artifact_coverage(day)
        if coverage["stale"]:
            return {"ok": False, "http_status": None, "reason": "stale_local_artifact",
                    "stale_artifacts": coverage["stale"], "newest_day": coverage["newest_day"],
                    "request_attempts": 0}
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
            response = session.post(base_url + STEPS[step], json=body, timeout=step_timeout(step), allow_redirects=False)
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
                    "persisted_price_changes", "movement_rows_received", "matched_movement",
                    "alignment_rows_received", "matched_alignment",
                ) if isinstance(payload.get(key), int)}
                result["flags"] = {key: payload[key] for key in ("no_matches", "no_frozen_predictions") if key in payload}
                if step == "market" and market_rows_unmatched(payload):
                    # 匹配不上任何 fixture 时上游仍会回 verified；这里必须降级，避免"假成功"。
                    result["ok"] = False
                    result["reason"] = "market_rows_unmatched"
                    verified = False
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
        results.append({"key": key, "step": job["step"], **result})
        persist(state)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sales-day", action="append", default=[])
    parser.add_argument("--stage", choices=STAGES)
    parser.add_argument("--retry-pending", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rebuild-market", action="store_true",
                        help="运行 movement/alignment 构建器刷新 latest 别名后再同步含 market 的阶段")
    parser.add_argument("--max-jobs", type=int, default=6)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--state-dir", type=Path, default=ROOT / "artifacts/data/controller_sync")
    parser.add_argument("--web-autostart", action=argparse.BooleanOptionalAction, default=True,
                        help="本地 Web 未就绪时由同步脚本自行拉起（--no-web-autostart 关闭）")
    parser.add_argument("--web-timeout", type=float, default=180.0,
                        help="自拉起后等待 Web 就绪的秒数；超时保持待同步，不谎报成功")
    args = parser.parse_args()
    if bool(args.sales_day) != bool(args.stage) or not (args.stage or args.retry_pending):
        parser.error("use --stage with --sales-day, or --retry-pending")
    if args.rebuild_market and (not args.stage or "market" not in STAGES[args.stage]):
        parser.error("--rebuild-market requires a stage that includes the market step")
    if not 1 <= args.max_jobs <= 20:
        parser.error("--max-jobs must be between 1 and 20")
    parsed = urlparse(args.base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        parser.error("only a local loopback Web service is allowed")
    if args.web_autostart and not parsed.port:
        parser.error("--base-url must include a port when autostart is enabled")
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
        print(json.dumps({"dry_run": True, "rebuild_market": args.rebuild_market,
                          "pending_keys": [k for k, j in state["jobs"].items() if j["status"] != "completed"]}, ensure_ascii=False))
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
        if args.rebuild_market:
            try:
                rebuilt = rebuild_market_artifacts()
            except (OSError, subprocess.CalledProcessError) as error:
                print(f"market_rebuild_failed: {error}; nothing was enqueued")
                return 3
        else:
            rebuilt = []
        save_json(state_path, state)  # Durable intent before the first request.
        ledger_paths = [ROOT / "data/manual" / name for name in ("betting_plan_ledger.csv", "fixed_odds_shadow_ledger.csv")]
        def ledger_hashes():
            return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None for p in ledger_paths}
        before = ledger_hashes()
        base_url = args.base_url.rstrip("/")
        web_process = None
        web_actions: list[str] = []
        web_ready = not args.web_autostart
        if args.web_autostart:
            # 页面只读 Supabase：Web 没起来就等于没同步。这里自己把写入服务拉起来，用完整链路代替人工确认。
            web_ready, web_process, web_actions = ensure_web_service(
                base_url, parsed.port, args.state_dir / "web_autostart.log", args.web_timeout)
        try:
            session = None
            results: list[dict] = []
            if web_ready:
                session = requests.Session()
                session.trust_env = False  # Never send loopback credentials through an ambient proxy.
                credentials = admin_credentials(ROOT.parent / "web/.env.local")
                user, password = credentials.get("WORKBENCH_ADMIN_USER"), credentials.get("WORKBENCH_ADMIN_PASSWORD")
                if user and password:
                    session.auth = (user, password)
                results = run_pending(state, session, base_url, now,
                                      lambda value: save_json(state_path, value), args.max_jobs)
            pending = [k for k, j in state["jobs"].items() if j["status"] != "completed"]
            audit = {"at": now.isoformat(), "results": results, "pending_keys": pending,
                     "ok": not pending, "rebuilt_market_artifacts": rebuilt,
                     "web_service_ready": web_ready, "web_autostart": web_actions, "health_reported": False,
                     "production_ledger_unchanged": before == ledger_hashes(),
                     "source_ledger_sha256": before}
            if web_ready and session is not None and results:
                # 空跑（无待同步步骤）不刷新健康度时间，否则页面会把“什么都没同步”显示成“刚刚同步过”。
                audit["health_reported"] = report_health(
                    session, base_url, health_snapshot(now, args.stage, args.sales_day, results, pending, web_actions))
            save_json(args.state_dir / f"run_{now:%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}.json", audit)
            save_json(args.state_dir / "latest.json", audit)
            print(json.dumps(audit, ensure_ascii=False, indent=2))
            return 1 if pending else 0
        finally:
            stop_web_service(web_process)
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
