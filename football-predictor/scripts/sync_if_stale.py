"""Idempotent guard: push a sales day only when its local artifacts are newer than the last verified push.

一天的数据是分批采集、分批预测的，所以"要不要同步"不能靠记忆，必须由命令自己判断。
批次收尾和每次唤醒各跑同一条命令即可：本批没有新产物时它不发任何请求，有新产物时才委托
run_controller_data_sync.py（该脚本按销售日全量重推，天然幂等，重复执行只会覆盖同样的行）。

判不准时宁可多同步一次（多一次幂等重推，无副作用）；漏同步则页面上永远看不到这批数据。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# 复用同步脚本的阶段定义与本地产物路径，避免两处口径漂移。
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_controller_data_sync import (  # noqa: E402  (需要先补 sys.path 才能导入同目录脚本)
    ALIGNMENT_CSV,
    DEFAULT_BASE_URL,
    MOVEMENT_CSV,
    STAGES,
)

STATE_DIR = ROOT / "artifacts/data/controller_sync"
SYNC_SCRIPT = ROOT / "scripts/run_controller_data_sync.py"
# 产物写入与同步落库可能落在同一秒，给一点容忍窗口，避免反复判定为"有更新"。
TOLERANCE_SECONDS = 1.0


def day_artifacts(day: str, root: Path) -> list[Path]:
    """本次同步会读取的、与该销售日相关的本地产物。

    宁可多列（多同步一次）也不能漏列（漏了页面上就永远缺这批数据）。两个 latest 别名是
    全量文件，任何一天刷新都会改动它们，因此会被判成"有更新"而多推一次，这是安全的方向。
    """
    data = root / "artifacts/data"
    groups = (
        sorted(data.glob(f"sporttery_*{day}*.json")),  # 在售窗口扫描、当日编排 override、任务注册表
        sorted(data.glob(f"sporttery_match_analysis_{day}_*.csv")),  # 冻结的体彩盘口锚定分析
        [data / "football_automation_controller_state.json"],
        [root / "data/manual/betting_plan_ledger.csv", root / "data/manual/fixed_odds_shadow_ledger.csv"],
        [MOVEMENT_CSV, ALIGNMENT_CSV],
        sorted((root / "data/external/nowscore/snapshots").glob(f"{day}_*/*.csv")),
    )
    return [path for group in groups for path in group if path.is_file()]


def last_verified_push(state: dict, day: str, stage: str) -> datetime | None:
    """该销售日这一阶段全部步骤都验证通过的落库时间。

    任一必需步骤从未成功过（缺失或仍在待同步）就返回 None：说明这一天还没被完整推上去。
    """
    stamps = []
    for step in STAGES[stage]:
        job = state["jobs"].get(f"{day}|{step}") or {}
        if job.get("status") != "completed" or not job.get("last_attempt_at"):
            return None
        stamps.append(datetime.fromisoformat(job["last_attempt_at"]))
    return max(stamps)


def decide(state: dict, days: list[str], stage: str, root: Path = ROOT) -> tuple[list[str], dict]:
    """返回需要同步的销售日与每天的判定原因。"""
    pending, reasons = [], {}
    for day in days:
        artifacts = day_artifacts(day, root)
        pushed = last_verified_push(state, day, stage)
        if not artifacts:
            # 本地没有这一天的产物，同步也没有数据可发；等产物出现后自然会被判为待同步。
            reasons[day] = "no_local_artifact"
        elif pushed is None:
            reasons[day] = "never_fully_synced"
            pending.append(day)
        elif max(path.stat().st_mtime for path in artifacts) > pushed.timestamp() + TOLERANCE_SECONDS:
            reasons[day] = "artifacts_newer"
            pending.append(day)
        else:
            reasons[day] = "up_to_date"
    return pending, reasons


def sync_command(days: list[str], stage: str, base_url: str, state_dir: Path) -> list[str]:
    command = [sys.executable, str(SYNC_SCRIPT), "--stage", stage, "--base-url", base_url]
    for day in days:
        command += ["--sales-day", day]
    if state_dir != STATE_DIR:
        command += ["--state-dir", str(state_dir)]
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sales-day", action="append", required=True, help="本次批次实际处理的销售日，可重复")
    parser.add_argument("--stage", choices=STAGES, required=True)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--state-dir", type=Path, default=STATE_DIR)
    parser.add_argument("--force", action="store_true", help="跳过自判，直接委托同步")
    args = parser.parse_args()
    for day in args.sales_day:
        try:
            if date.fromisoformat(day).isoformat() != day:
                raise ValueError(day)
        except ValueError:
            parser.error("sales-day must be YYYY-MM-DD")
    days = sorted(set(args.sales_day))
    state_path = args.state_dir / "outbox.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"jobs": {}}
    pending, reasons = decide(state, days, args.stage)
    if args.force:
        pending, reasons = days, {day: "forced" for day in days}
    if not pending:
        print(json.dumps({"decision": "up_to_date", "stage": args.stage, "days": reasons}, ensure_ascii=False))
        return 0
    command = sync_command(pending, args.stage, args.base_url, args.state_dir)
    print(json.dumps({"decision": "sync", "stage": args.stage, "days": reasons,
                      "delegated": command[1:]}, ensure_ascii=False), flush=True)
    return subprocess.run(command, cwd=str(ROOT)).returncode


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
