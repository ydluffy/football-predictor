"""将本地 codex 产物批量同步到 Supabase。

用法示例：
  python scripts/sync_local_artifacts_to_supabase.py --days-back 40
  python scripts/sync_local_artifacts_to_supabase.py --sales-day 2026-09-04 --sales-day 2026-09-03

说明：
1. 该脚本依赖本地 Web 服务已启动，并且启用了 ALLOW_LOCAL_ARTIFACTS=true。
2. 脚本会依次调用：
   - /api/predictions/snapshot
   - /api/automation/sync
   - /api/automation/persist-history
3. 页面端最终统一从 Supabase 读取，不直接读取你本地 artifacts。
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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


def chunked(items: list[str], size: int) -> Iterable[list[str]]:
    for idx in range(0, len(items), size):
        yield items[idx : idx + size]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="将本地 codex 产物同步到 Supabase")
    parser.add_argument("--base-url", default="http://127.0.0.1:3000", help="本地 Web 服务地址")
    parser.add_argument(
        "--sales-day", action="append", default=[], help="指定销售日，可重复传入多次"
    )
    parser.add_argument(
        "--days-back", type=int, default=40, help="未显式指定销售日时，默认回填最近 N 个销售日"
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

    status = get_json(session, f"{args.base_url.rstrip('/')}/api/status", "检测本地 Web 服务")
    print_result(status)
    if not status.ok:
        print(
            "\n本地 Web 服务不可用。请先启动：\n"
            "  ALLOW_LOCAL_ARTIFACTS=true npx next dev -H 0.0.0.0 -p 3000\n",
            file=sys.stderr,
        )
        return 2

    failed = False

    if not args.skip_snapshot:
        for sales_day in sales_days:
            result = post_json(
                session,
                f"{args.base_url.rstrip('/')}/api/predictions/snapshot",
                {"date": sales_day},
                f"同步赛程/预测快照 {sales_day}",
            )
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
            print_result(result)
            failed = failed or not result.ok

    if failed:
        print("\n同步已执行，但存在失败步骤，请按上方返回信息排查。", file=sys.stderr)
        return 1

    print("\n全部同步完成。现在 Web 端应可从 Supabase 读取到最新内容。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
