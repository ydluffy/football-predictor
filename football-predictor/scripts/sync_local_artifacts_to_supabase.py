"""将本地 codex 产物批量同步到 Supabase。

用法示例：
  python scripts/sync_local_artifacts_to_supabase.py --days-back 40
  python scripts/sync_local_artifacts_to_supabase.py --sales-day 2026-09-05

说明：
1. 依赖本地 Web 服务已启动，并启用了 ALLOW_LOCAL_ARTIFACTS=true。
2. 脚本按步骤执行并单独核验：
   - /api/automation/sync-snapshot
   - /api/automation/sync
   - /api/automation/persist-history
3. 执行成功不等于真正入库；脚本会额外直连 Supabase 做回读核验。
4. 页面端最终统一从 Supabase 读取，不直接读取你本地 artifacts。
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

TZ = timezone(timedelta(hours=8))


@dataclass
class SyncResult:
    step: str
    ok: bool
    status_code: int | None
    payload: Any
    warning: bool = False
    verification: dict[str, Any] | None = None


def read_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


class SupabaseVerifier:
    def __init__(self, repo_root: Path):
        env = read_env_file(repo_root / "web" / ".env.local")
        self.base = (env.get("SUPABASE_URL") or "").rstrip("/")
        self.key = env.get("SUPABASE_SERVICE_ROLE_KEY") or ""
        self.enabled = bool(self.base and self.key)
        self.session = requests.Session()
        if self.enabled:
            self.session.headers.update({"apikey": self.key, "Authorization": f"Bearer {self.key}"})

    def _get(self, query: str) -> tuple[bool, Any, str]:
        if not self.enabled:
            return False, {"reason": "missing_supabase_env"}, ""
        url = f"{self.base}/rest/v1{query}"
        resp = self.session.get(url, timeout=60)
        try:
            payload = resp.json()
        except requests.exceptions.JSONDecodeError:
            payload = resp.text
        return resp.ok, payload, resp.headers.get("Content-Range", "")

    def verify_snapshot(self, sales_day: str, expected: dict[str, Any]) -> dict[str, Any]:
        ok_fx, fixtures, fixtures_range = self._get(
            f"/fixtures?select=fixture_id,sporttery_match_number&sporttery_sales_day=eq.{sales_day}"
        )
        ok_pred, predictions, predictions_range = self._get(
            f"/fixture_predictions?select=fixture_id&as_of_date=eq.{sales_day}"
        )
        fixture_count = len(fixtures) if ok_fx and isinstance(fixtures, list) else 0
        prediction_count = len(predictions) if ok_pred and isinstance(predictions, list) else 0
        persisted_fixtures = int(expected.get("persisted_fixtures") or 0)
        snapshotted = int(expected.get("snapshotted") or 0)
        no_matches = bool(expected.get("no_matches"))
        no_frozen_predictions = bool(expected.get("no_frozen_predictions"))
        verified = ok_fx and ok_pred
        if no_matches:
            verified = verified and fixture_count == 0 and prediction_count == 0
        else:
            if persisted_fixtures > 0:
                verified = verified and fixture_count >= persisted_fixtures
            if snapshotted > 0:
                verified = verified and prediction_count >= snapshotted
            if persisted_fixtures == 0 and snapshotted == 0 and not (no_matches or no_frozen_predictions):
                verified = False
        return {
            "verified": verified,
            "fixtures_in_db": fixture_count,
            "predictions_in_db": prediction_count,
            "expected_persisted_fixtures": persisted_fixtures,
            "expected_snapshotted": snapshotted,
            "no_matches": no_matches,
            "no_frozen_predictions": no_frozen_predictions,
            "fixtures_count_header": fixtures_range,
            "predictions_count_header": predictions_range,
        }

    def verify_controller(self, sales_days: list[str], expected: dict[str, Any]) -> dict[str, Any]:
        ok_controller, controller_rows, controller_range = self._get(
            "/automation_controller_state?select=id,controller_month,status,next_required_at&id=eq.default"
        )
        controller_present = ok_controller and isinstance(controller_rows, list) and len(controller_rows) == 1
        wanted = {
            item.get("sales_day"): item
            for item in (expected.get("synced_sales_days") or [])
            if isinstance(item, dict) and item.get("sales_day")
        }
        days_report: list[dict[str, Any]] = []
        verified = controller_present
        for sales_day in sales_days:
            ok_override, override_rows, _ = self._get(
                f"/automation_daily_overrides?select=sales_day&sales_day=eq.{sales_day}"
            )
            ok_registry, registry_rows, _ = self._get(
                f"/automation_task_registries?select=sales_day&sales_day=eq.{sales_day}"
            )
            override_present = ok_override and isinstance(override_rows, list) and len(override_rows) > 0
            registry_present = ok_registry and isinstance(registry_rows, list) and len(registry_rows) > 0
            expected_day = wanted.get(sales_day, {})
            override_expected = expected_day.get("override")
            registry_expected = expected_day.get("registry")
            day_verified = True
            if override_expected == "ok":
                day_verified = day_verified and override_present
            if registry_expected == "ok":
                day_verified = day_verified and registry_present
            verified = verified and day_verified
            days_report.append(
                {
                    "sales_day": sales_day,
                    "override_expected": override_expected,
                    "override_present": override_present,
                    "registry_expected": registry_expected,
                    "registry_present": registry_present,
                    "verified": day_verified,
                }
            )
        return {
            "verified": verified,
            "controller_state_present": controller_present,
            "controller_count_header": controller_range,
            "sales_days": days_report,
        }

    def verify_history(self, sales_days: list[str], expected: dict[str, Any]) -> dict[str, Any]:
        days_filter = ",".join(sales_days)
        ok_summary, summaries, summary_range = self._get(
            f"/sporttery_review_summaries?select=sales_day&sales_day=in.({days_filter})"
        )
        ok_plans, plans, plans_range = self._get(
            f"/sporttery_review_plans?select=sales_day,plan_id&sales_day=in.({days_filter})"
        )
        ok_analysis, analyses, analysis_range = self._get(
            f"/sporttery_analysis_runs?select=sales_day,stage,analysis_at&sales_day=in.({days_filter})"
        )
        summary_count = len(summaries) if ok_summary and isinstance(summaries, list) else 0
        plan_count = len(plans) if ok_plans and isinstance(plans, list) else 0
        analysis_count = len(analyses) if ok_analysis and isinstance(analyses, list) else 0
        expected_summary = int(expected.get("persisted_review_summaries") or 0)
        expected_plans = int(expected.get("persisted_review_plans") or 0)
        expected_analysis = int(expected.get("persisted_analysis_runs") or 0)
        verified = ok_summary and ok_plans and ok_analysis
        if expected_summary > 0:
            verified = verified and summary_count >= min(expected_summary, len(sales_days))
        if expected_plans > 0:
            verified = verified and plan_count >= expected_plans
        if expected_analysis > 0:
            verified = verified and analysis_count >= expected_analysis
        if expected_summary == 0 and expected_plans == 0 and expected_analysis == 0:
            verified = verified and True
        return {
            "verified": verified,
            "review_summaries_in_db": summary_count,
            "review_plans_in_db": plan_count,
            "analysis_runs_in_db": analysis_count,
            "expected_review_summaries": expected_summary,
            "expected_review_plans": expected_plans,
            "expected_analysis_runs": expected_analysis,
            "review_summary_count_header": summary_range,
            "review_plan_count_header": plans_range,
            "analysis_count_header": analysis_range,
        }


def shanghai_today() -> datetime:
    return datetime.now(TZ)


def build_sales_days(explicit_days: list[str], days_back: int) -> list[str]:
    if explicit_days:
        return explicit_days
    today = shanghai_today().date()
    return [(today - timedelta(days=i)).isoformat() for i in range(max(days_back, 1))]


def build_headers(username: str | None, password: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if username and password:
        token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
        headers["Authorization"] = f"Basic {token}"
    return headers


def try_json(resp: requests.Response) -> Any:
    try:
        return resp.json()
    except requests.exceptions.JSONDecodeError:
        return resp.text


def post_json(session: requests.Session, url: str, body: dict[str, Any], step: str) -> SyncResult:
    resp = session.post(url, json=body, timeout=120)
    payload = try_json(resp)
    return SyncResult(step=step, ok=resp.ok, status_code=resp.status_code, payload=payload)


def get_json(session: requests.Session, url: str, step: str) -> SyncResult:
    resp = session.get(url, timeout=60)
    payload = try_json(resp)
    return SyncResult(step=step, ok=resp.ok, status_code=resp.status_code, payload=payload)


def print_result(result: SyncResult) -> None:
    marker = "⚠️" if result.warning else ("✅" if result.ok else "❌")
    print(f"{marker} {result.step} (HTTP {result.status_code})")
    print(json.dumps(result.payload, ensure_ascii=False, indent=2))
    if result.verification is not None:
        print("---- 数据库核验 ----")
        print(json.dumps(result.verification, ensure_ascii=False, indent=2))


def chunked(items: list[str], size: int) -> Iterable[list[str]]:
    for idx in range(0, len(items), size):
        yield items[idx : idx + size]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="将本地 codex 产物同步到 Supabase")
    parser.add_argument("--base-url", default="http://127.0.0.1:3100", help="本地 Web 服务地址")
    parser.add_argument(
        "--sales-day", action="append", default=[], help="指定销售日，可重复传入多次"
    )
    parser.add_argument(
        "--days-back", type=int, default=1, help="默认仅今日；历史回填须显式指定天数"
    )
    parser.add_argument("--batch-size", type=int, default=10, help="批量同步历史时每批销售日数量")
    parser.add_argument("--username", default=None, help="可选：工作台管理员用户名")
    parser.add_argument("--password", default=None, help="可选：工作台管理员密码")
    parser.add_argument("--skip-snapshot", action="store_true", help="跳过赛程/预测快照同步")
    parser.add_argument(
        "--skip-controller", action="store_true", help="跳过 controller/override/registry 同步"
    )
    parser.add_argument("--skip-history", action="store_true", help="跳过复盘/方案历史同步")
    parser.add_argument(
        "--strict", action="store_true", help="兼容旧命令；现在任何接口错误默认返回非 0 退出码"
    )
    args = parser.parse_args()
    if args.batch_size < 1 or args.days_back < 1:
        parser.error("--batch-size 和 --days-back 必须大于 0")

    sales_days = build_sales_days(args.sales_day, args.days_back)
    headers = build_headers(args.username, args.password)
    session = requests.Session()
    session.headers.update(headers)
    repo_root = Path(__file__).resolve().parents[2]
    verifier = SupabaseVerifier(repo_root)

    status = get_json(session, f"{args.base_url.rstrip('/')}/api/status", "检测本地 Web 服务")
    print_result(status)
    if not status.ok:
        print(
            "\n本地 Web 服务不可用。请先启动：\n"
            "  node ..\\web\\node_modules\\next\\dist\\bin\\next dev -H 127.0.0.1 -p 3100\n",
            file=sys.stderr,
        )
        return 2

    failed = False

    if not args.skip_snapshot:
        for sales_day in sales_days:
            result = post_json(
                session,
                f"{args.base_url.rstrip('/')}/api/automation/sync-snapshot",
                {"date": sales_day},
                f"同步冻结赛程/预测快照 {sales_day}",
            )
            if result.ok:
                result.verification = verifier.verify_snapshot(sales_day, result.payload if isinstance(result.payload, dict) else {})
                if not result.verification.get("verified", False):
                    result.ok = False
                    result.warning = True
            else:
                result.warning = False
            print_result(result)
            failed = failed or not result.ok

    if not args.skip_controller:
        for batch in chunked(sales_days, args.batch_size):
            result = post_json(
                session,
                f"{args.base_url.rstrip('/')}/api/automation/sync",
                {"sales_days": batch},
                f"同步总控状态 {batch[0]} ~ {batch[-1]}",
            )
            if result.ok:
                payload = result.payload if isinstance(result.payload, dict) else {}
                result.verification = verifier.verify_controller(batch, payload)
                day_report = result.verification.get("sales_days", [])
                partial = any(not item.get("verified", False) for item in day_report if item.get("override_expected") == "ok" or item.get("registry_expected") == "ok")
                if not result.verification.get("verified", False):
                    result.ok = False
                    result.warning = True
                elif any(item.get("override_expected") == "missing" for item in day_report):
                    result.warning = True
            print_result(result)
            failed = failed or not result.ok

    if not args.skip_history:
        for batch in chunked(sales_days, args.batch_size):
            result = post_json(
                session,
                f"{args.base_url.rstrip('/')}/api/automation/persist-history",
                {"sales_days": batch},
                f"同步复盘/方案历史 {batch[0]} ~ {batch[-1]}",
            )
            if result.ok:
                payload = result.payload if isinstance(result.payload, dict) else {}
                result.verification = verifier.verify_history(batch, payload)
                if not result.verification.get("verified", False):
                    result.ok = False
                    result.warning = True
            print_result(result)
            failed = failed or not result.ok

    if failed:
        print("\n同步已执行，但存在失败或核验未通过的步骤，请按上方“数据库核验”信息排查。", file=sys.stderr)
        return 1

    print("\n全部同步完成，且数据库核验已通过。现在 Web 端应可从 Supabase 读取到最新内容。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
